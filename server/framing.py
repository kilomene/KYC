"""Document framing check (live-scanner build, 2026-10-26; paper
rectification, 2026-10-26).

Verifies, with OpenCV, that a captured document image actually
contains a document quadrilateral that roughly fills the frame — the
server-side counterpart of the live scanner's viewfinder. A random
photo, a blank image, or a document photographed from across the room
must not pass this; a document filling the frame must.

Rectification (2026-10-26): the original detector was a single Canny
pass tuned for rigid plastic cards. It returned
fail/document_not_detected (largest_contour_ratio 0.0142) on the
owner's REAL Nigerian NIN slip — a laminated paper printout, bowed,
folded, hand-held — because a curved paper outline does not survive
as one clean Canny contour. Detection is now multi-strategy:

  1. edges        Canny (50,150) contours, as before;
  2. edges_clahe  CLAHE-equalised Canny (30,90) — rescues outlines
                  whose contrast is eaten by glare/shadow;
  3. segmentation blurred-luminance segmentation (Otsu, both
                  polarities, + a high-percentile threshold) with
                  morphological closing — a bright paper sheet on a
                  darker background resolves as one filled region
                  even when its border is curved.

Every candidate contour is fitted to a quadrilateral (approxPolyDP
with an epsilon sweep, convex-hull fallback, minAreaRect last resort
for high-solidity blobs) and must be CONVEX and carry real interior
TEXTURE (print): local block variance + edge density inside the quad.
A bright window or wall can segment as a region, but it has no print
texture — segmentation alone can never hallucinate a document.

Decision contract (unchanged, fail-closed):
    area_ratio >= 0.25            -> pass
    wide document rule            -> pass when the quad spans >= 70%
                                     of the frame width and
                                     area_ratio >= 0.10 (a wide paper
                                     slip in a portrait phone frame
                                     can never reach 0.25 area — its
                                     height is capped by its aspect)
    0.10 <= ratio < 0.25          -> unclear (document present but
                                     small in frame)
    no quad / texture-less quad   -> fail / unclear per findings

Quad quality gate (Session-5 diagnosis, 2026-10-26): the two quad
families can DISAGREE about the document's shape. On the owner's real
NIN slip the segmentation quad measured aspect 1.401 against the
slip's true ~2.20 — the perspective warp then stretched the document
~1.57x vertically and every downstream check (classification,
extraction) consumed the distortion. analyse_image therefore keeps
the best ACCEPTED quad per family (edges vs segmentation) and, when
their aspects disagree by more than 25%, resolves the conflict
instead of silently taking the larger blob: the quad sitting
MID-RANGE in the claimed type's registry aspect range wins; with no
range (or no mid-range quad), the EDGE quad wins (segmentation is
the distortion-prone family — it fits filled luminance regions, edges
trace the physical border); when neither quad can be preferred
(both/neither inside the claimed range, or only a rejected
document-scale edge outline contradicts an accepted segmentation
quad), framing answers UNCLEAR (rescan) rather than passing a
distorted warp downstream. Findings record the conflict and its
resolution either way.

When a quad is found, the capture can be perspective-WARPED to a flat
rectangle (warp_document / warped_rendition): OCR and extraction run
on the warp, authenticity keeps the original. Framing findings record
the quad, the measured aspect and whether a warp was applied.

If OpenCV is unavailable the check returns 'error' — never a pass
(the fail-closed pattern used by every check in this codebase).
"""
import hashlib
import os
import tempfile
import threading

try:
    import cv2
    import numpy as np
except Exception:  # OpenCV missing -> framing check errors, never passes
    cv2 = None
    np = None

PASS_RATIO = 0.25
UNCLEAR_RATIO = 0.10
WIDE_MIN_WIDTH_FRAC = 0.70
WIDE_PASS_AREA = 0.10
WIDE_UNCLEAR_AREA = 0.06
_ANALYSIS_MAX_DIM = 1000
_WARP_WIDTH = 1240
# Edge-vs-segmentation aspect disagreement beyond this relative
# difference means the two families measured DIFFERENT shapes.
ASPECT_CONFLICT_REL = 0.25

def _resolve_aspect_conflict(edge_aspect, seg_aspect, expected_range):
    """Choose between two ACCEPTED quads whose aspects disagree.
    -> (group, resolution): group is "edges" | "segmentation" | None
    (None = ambiguous: neither quad may be preferred).

    With the claimed type's registry range: a quad whose aspect sits
    in the range's central band (mid-range) beats one in the outer
    band; failing that, a quad INSIDE the range beats one outside it;
    if both are equally placed (both mid-range, both merely in-range,
    or both out of range) the shapes are genuinely ambiguous at >25%
    disagreement and the caller answers unclear (rescan). Without a
    range, the EDGE quad wins outright: segmentation fits filled
    luminance blobs (the family that produced the 1.401-vs-2.20
    distortion), edges trace the document's physical border."""
    if expected_range:
        lo, hi = expected_range
        if hi and hi > lo:
            mid_lo = lo + 0.25 * (hi - lo)
            mid_hi = hi - 0.25 * (hi - lo)
            e_mid = mid_lo <= edge_aspect <= mid_hi
            s_mid = mid_lo <= seg_aspect <= mid_hi
            if e_mid != s_mid:
                return ("edges", "midrange_preferred") if e_mid else ("segmentation", "midrange_preferred")
            e_in = lo <= edge_aspect <= hi
            s_in = lo <= seg_aspect <= hi
            if e_in != s_in:
                return ("edges", "in_range_preferred") if e_in else ("segmentation", "in_range_preferred")
            return (None, "ambiguous_both_in_range" if e_in else "ambiguous_neither_in_range")
    return ("edges", "edge_preferred")

def expected_range_from_entry(entry):
    """The (lo, hi) registry aspect range for a docregistry entry, or
    None. Paper/booklet entries carry aspect_min/aspect_max directly;
    card entries carry a point aspect, whose range is the ±10%
    classification tolerance band around it."""
    if not entry:
        return None
    if entry.get("aspect_min") and entry.get("aspect_max"):
        return (float(entry["aspect_min"]), float(entry["aspect_max"]))
    a = entry.get("aspect")
    if a:
        return (round(float(a) * 0.90, 4), round(float(a) * 1.10, 4))
    return None

# ------------------------------------------------------------------
# quad fitting helpers
# ------------------------------------------------------------------

def _order_quad(pts):
    """Order 4 points TL, TR, BR, BL."""
    pts = np.array(pts, dtype="float32").reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(s)]   # TL: smallest x+y
    ordered[2] = pts[np.argmax(s)]   # BR: largest x+y
    ordered[1] = pts[np.argmin(d)]   # TR: smallest y-x
    ordered[3] = pts[np.argmax(d)]   # BL: largest y-x
    return ordered

def _quad_metrics(quad, w, h):
    """(area_ratio, width_frac, height_frac, measured aspect).
    The quad is ORDERED first — contour point order starts at an
    arbitrary corner and runs in an arbitrary direction, so assuming
    quad[0]->quad[1] is the top edge silently transposes the aspect
    (measured during the rectification build: a 1.58 card read back
    as 0.63)."""
    quad = _order_quad(quad)
    area = float(cv2.contourArea(quad.reshape(-1, 1, 2).astype("float32")))
    top = np.linalg.norm(quad[1] - quad[0]); bottom = np.linalg.norm(quad[2] - quad[3])
    left = np.linalg.norm(quad[3] - quad[0]); right = np.linalg.norm(quad[2] - quad[1])
    mw, mh = (top + bottom) / 2.0, (left + right) / 2.0
    xs, ys = quad[:, 0], quad[:, 1]
    return {
        "area_ratio": area / float(w * h) if w and h else 0.0,
        "width_frac": float(xs.max() - xs.min()) / w if w else 0.0,
        "height_frac": float(ys.max() - ys.min()) / h if h else 0.0,
        "aspect": float(mw / mh) if mh else 0.0,
    }

def _fit_quad(cnt):
    """Fit a convex quadrilateral to one contour, or None.
    approxPolyDP with an epsilon sweep on the contour, then on its
    convex hull (a bowed paper border oscillates around its hull);
    minAreaRect only for high-solidity blobs whose outline never
    resolves to 4 points."""
    peri = cv2.arcLength(cnt, True)
    if peri <= 0:
        return None
    for src in (cnt, cv2.convexHull(cnt)):
        for frac in (0.01, 0.02, 0.03, 0.045, 0.06):
            approx = cv2.approxPolyDP(src, frac * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                return _order_quad(approx.reshape(4, 2).astype("float32"))
    hull = cv2.convexHull(cnt)
    hull_area = cv2.contourArea(hull)
    if hull_area > 0 and cv2.contourArea(cnt) / hull_area >= 0.90:
        rect = cv2.boxPoints(cv2.minAreaRect(cnt))
        return _order_quad(rect.astype("float32"))
    return None

def _interior_texture(grey, edges, quad, w, h):
    """Print-texture evidence inside the quad: Canny edge density and
    the MEDIAN local block std (a smooth gradient/window has neither;
    global std alone would be fooled by a gradient)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [quad.astype(np.int32)], 1)
    er = max(3, int(min(w, h) * 0.02))
    inner = cv2.erode(mask, np.ones((er, er), np.uint8))
    ys, xs = np.where(inner > 0)
    if len(xs) < 200:
        return {"ok": False, "edge_density": 0.0, "block_std": 0.0}
    edge_density = float((edges[ys, xs] > 0).mean())
    vals = grey[ys, xs].astype("float32")
    # local block std over a coarse grid of the interior points
    gx = (xs // max(8, w // 12)).astype(int)
    gy = (ys // max(8, h // 12)).astype(int)
    blocks = {}
    for i in range(len(xs)):
        blocks.setdefault((gx[i], gy[i]), []).append(vals[i])
    stds = [float(np.std(v)) for v in blocks.values() if len(v) >= 12]
    block_std = float(np.median(stds)) if stds else 0.0
    return {"ok": bool(edge_density >= 0.006 or block_std >= 6.0),
            "edge_density": round(edge_density, 4), "block_std": round(block_std, 2)}

def _border_support(edges, quad):
    """Fraction of sampled points along the quad's perimeter that sit
    on (or within ~3px of) a real Canny edge. A document border IS an
    edge; a segmentation blob fitted around random scene shapes is
    not — this is what stops a bright region of a room photo from
    being promoted to a document."""
    quad = _order_quad(quad)
    hits = 0
    total = 0
    h, w = edges.shape[:2]
    for i in range(4):
        p0, p1 = quad[i], quad[(i + 1) % 4]
        for t in np.linspace(0.04, 0.96, 20):
            x, y = p0 + (p1 - p0) * t
            xi, yi = int(round(x)), int(round(y))
            x0, x1 = max(0, xi - 3), min(w, xi + 4)
            y0, y1 = max(0, yi - 3), min(h, yi + 4)
            total += 1
            if x1 > x0 and y1 > y0 and bool((edges[y0:y1, x0:x1] > 0).any()):
                hits += 1
    return round(hits / total, 3) if total else 0.0

def _ring_contrast(grey, quad):
    """|mean luminance inside the quad - mean in the ring just
    outside it|. A physical document contrasts with its background
    (bright paper on a darker room, or a dark card on a light desk);
    a fitted region inside one continuous surface does not. Returns
    None when the ring is too small to judge (near-full-frame quad)."""
    h, w = grey.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [_order_quad(quad).astype(np.int32)], 1)
    d = max(4, int(min(w, h) * 0.03))
    ring = cv2.dilate(mask, np.ones((d, d), np.uint8)) - mask
    inside = grey[mask > 0]
    outside = grey[ring > 0]
    if len(inside) < 200 or len(outside) < 120:
        return None
    return round(abs(float(inside.mean()) - float(outside.mean())), 2)

def _candidates(grey, edges, method):
    """Yield fitted quads from one edge/binary map's contours."""
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    out = []
    for cnt in contours[:6]:
        quad = _fit_quad(cnt)
        if quad is not None:
            out.append(quad)
    return out, (cv2.contourArea(contours[0]) if contours else 0.0)

def analyse_image(img, expected_aspect_range=None):
    """Full framing analysis of a BGR image. Returns a dict:
    {quad (4x2 float32, original coords) or None, method, area_ratio,
     width_frac, height_frac, aspect, texture{}, largest_contour_ratio,
     width, height}. Quad search runs on a downscaled copy.
    expected_aspect_range: the claimed document type's registry
    aspect range (lo, hi) when the caller knows it — used only by the
    quad quality gate to resolve edge-vs-segmentation aspect
    conflicts (see the module docstring); the gate works without it
    (edge quad preferred)."""
    if cv2 is None or img is None:
        return None
    h0, w0 = img.shape[:2]
    scale = min(1.0, _ANALYSIS_MAX_DIM / float(max(h0, w0)))
    if scale < 1.0:
        img_a = cv2.resize(img, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    else:
        img_a = img
    h, w = img_a.shape[:2]
    image_area = float(w * h)
    grey = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    grey_blur = cv2.GaussianBlur(grey, (5, 5), 0)
    edges_main = cv2.Canny(grey_blur, 50, 150)
    result = {"quad": None, "method": None, "area_ratio": 0.0, "width_frac": 0.0,
              "height_frac": 0.0, "aspect": 0.0, "texture": None,
              "border_support": None, "ring_contrast": None, "accepted": False,
              "candidate": None, "aspect_conflict": None, "ambiguous_aspect": False,
              "largest_contour_ratio": 0.0, "width": w0, "height": h0}

    strategies = []
    strategies.append(("edges", edges_main))
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        strategies.append(("edges_clahe", cv2.Canny(cv2.GaussianBlur(clahe.apply(grey), (5, 5), 0), 30, 90)))
    except Exception:
        pass
    # Luminance segmentation: wash the print out with a heavy blur so
    # the sheet becomes one filled region, then threshold. Otsu in
    # both polarities + a high-percentile cut for the classic case
    # (bright paper, darker room).
    seg_maps = []
    heavy = cv2.GaussianBlur(grey, (21, 21), 0)
    _, otsu = cv2.threshold(heavy, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    seg_maps.append(otsu)
    seg_maps.append(255 - otsu)
    pct = float(np.percentile(heavy, 62))
    seg_maps.append(np.where(heavy >= pct, 255, 0).astype(np.uint8))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    for m in seg_maps:
        closed = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        strategies.append(("segmentation", closed))

    best_ok = None    # accepted candidate: (score, area_ratio, quad, method, met, tex, border, ring)
    best_ok_edge = None   # best accepted EDGE-family candidate (quad quality gate)
    best_ok_seg = None    # best accepted SEGMENTATION candidate (quad quality gate)
    best_any = None   # strongest rejected EDGE candidate, for honest unclear findings
    for method, emap in strategies:
        quads, largest = _candidates(grey, emap, method)
        if method.startswith("edges"):
            # largest_contour_ratio keeps its original meaning (the
            # edge map's biggest contour) — segmentation maps always
            # have a giant blob (the background) and would poison it.
            result["largest_contour_ratio"] = max(result["largest_contour_ratio"], largest / image_area)
        for quad in quads:
            met = _quad_metrics(quad, w, h)
            # < 4% is a fragment, not a document; >= 97.5% is the
            # whole frame segmented as one blob (a blank image, a
            # wall) — a document the scanner accepts sits INSIDE the
            # frame with visible surroundings.
            if met["area_ratio"] < 0.04 or met["area_ratio"] >= 0.975:
                continue
            tex = _interior_texture(grey, edges_main, quad, w, h)
            border = _border_support(edges_main, quad)
            ring = _ring_contrast(grey, quad) if method == "segmentation" else None
            gates = bool(tex["ok"]) and border >= 0.30 and (ring is None or ring >= 10.0)
            pass_size = (met["area_ratio"] >= PASS_RATIO
                         or (met["width_frac"] >= WIDE_MIN_WIDTH_FRAC and met["area_ratio"] >= WIDE_PASS_AREA))
            # Segmentation is the hallucination-prone path (any bright
            # scene region — a window — fits a quad), so a
            # segmentation quad only counts when it ALSO meets the
            # pass size bars; below them it is dropped entirely rather
            # than promoted to an "unclear document". Edge-strategy
            # candidates keep the granular unclear semantics.
            accepted = gates and (method.startswith("edges") or pass_size)
            entry = (met["area_ratio"], quad, method, met, tex, border, ring)
            if accepted:
                # Rank by area x border support: the biggest blob is
                # NOT the best document (measured: a lamp-glare region
                # out-area'd the owner's slip 0.256 to 0.149 while its
                # border support was 0.30 against the slip's 0.89).
                score = met["area_ratio"] * border
                if best_ok is None or score > best_ok[0]:
                    best_ok = (score,) + entry
                if method.startswith("edges"):
                    if best_ok_edge is None or score > best_ok_edge[0]:
                        best_ok_edge = (score,) + entry
                else:
                    if best_ok_seg is None or score > best_ok_seg[0]:
                        best_ok_seg = (score,) + entry
            elif method.startswith("edges"):
                score = (bool(tex["ok"]), met["area_ratio"])
                if best_any is None or score > (bool(best_any[4]["ok"]), best_any[0]):
                    best_any = entry
    def _summarise(entry):
        area_ratio, quad, method, met, tex, border, ring = entry
        quad_orig = (quad / scale) if scale != 1.0 else quad
        return {"method": method,
                "area_ratio": round(met["area_ratio"], 4),
                "width_frac": round(met["width_frac"], 4),
                "height_frac": round(met["height_frac"], 4),
                "aspect": round(met["aspect"], 3), "texture": tex,
                "border_support": border, "ring_contrast": ring,
                "quad": [[round(float(x) / w0, 4), round(float(y) / h0, 4)] for x, y in _order_quad(quad_orig)]}

    # ---- quad quality gate: edge-vs-segmentation aspect conflict ----
    # Two accepted quads that disagree > 25% on aspect measured
    # DIFFERENT shapes; the larger-blob winner takes the warp either
    # way under the ranking above, which is how a segmentation blob
    # at aspect 1.401 warped (and stretched) a 2.20 slip. Resolve the
    # conflict explicitly; an unresolvable one marks the analysis
    # ambiguous and the check answers unclear (rescan) — no warp.
    ambiguous_entry = None
    if best_ok is not None:
        edge_e = best_ok_edge[1:] if best_ok_edge is not None else None
        seg_e = best_ok_seg[1:] if best_ok_seg is not None else None
        # A sub-document-scale edge quad (an inner feature — a photo
        # box, a text block) is not a competing document hypothesis:
        # the gate engages only when the edge quad is document-scale.
        # (seg_e is pass-size by construction — segmentation
        # candidates are only accepted at pass size.)
        if edge_e is not None and edge_e[0] < UNCLEAR_RATIO:
            edge_e = None
        if edge_e is not None and seg_e is not None:
            ea, sa = edge_e[3]["aspect"], seg_e[3]["aspect"]
            rel = abs(ea - sa) / max(ea, sa) if max(ea, sa) else 0.0
            if rel > ASPECT_CONFLICT_REL:
                group, resolution = _resolve_aspect_conflict(ea, sa, expected_aspect_range)
                result["aspect_conflict"] = {"edge_aspect": round(ea, 3),
                                             "segmentation_aspect": round(sa, 3),
                                             "rel_diff": round(rel, 3),
                                             "resolution": resolution}
                if group == "edges":
                    best_ok = best_ok_edge
                elif group == "segmentation":
                    best_ok = best_ok_seg
                else:
                    ambiguous_entry = seg_e
        elif seg_e is not None and best_any is not None:
            # Only segmentation was accepted, but a document-scale
            # edge outline (rejected on some other gate) traces a
            # fundamentally different shape: trust neither quad.
            wa, sa = best_any[3]["aspect"], seg_e[3]["aspect"]
            rel = abs(wa - sa) / max(wa, sa) if max(wa, sa) else 0.0
            if (best_any[0] >= UNCLEAR_RATIO and (best_any[5] or 0) >= 0.30
                    and rel > ASPECT_CONFLICT_REL):
                result["aspect_conflict"] = {"edge_aspect": round(wa, 3),
                                             "segmentation_aspect": round(sa, 3),
                                             "rel_diff": round(rel, 3),
                                             "resolution": "ambiguous_edge_witness"}
                ambiguous_entry = seg_e
    if ambiguous_entry is not None:
        result["ambiguous_aspect"] = True
        result["candidate"] = _summarise(ambiguous_entry)
        result["largest_contour_ratio"] = round(result["largest_contour_ratio"], 4)
        return result
    chosen = None
    if best_ok is not None:
        chosen = best_ok[1:]
    elif best_any is not None:
        chosen = best_any
    if chosen is not None:
        area_ratio, quad, method, met, tex, border, ring = chosen
        quad_orig = (quad / scale) if scale != 1.0 else quad
        summary = _summarise(chosen)
        if best_ok is not None:
            # summary carries a NORMALISED "quad" for findings
            # reporting; the analysis "quad" must stay in ORIGINAL
            # PIXELS for warp_image — so summary goes FIRST and the
            # pixel quad overwrites it, never the other way round
            # (that merge-order bug warped a 1x1 corner and read a
            # blank page on the owner's slip).
            result.update({**summary, "quad": _order_quad(quad_orig), "accepted": True})
        else:
            result["candidate"] = summary
    result["largest_contour_ratio"] = round(result["largest_contour_ratio"], 4)
    return result

def warp_image(img, quad, out_width=_WARP_WIDTH):
    """Perspective-warp the quad region to a flat rectangle whose
    aspect is the quad's measured aspect."""
    quad = _order_quad(quad)
    top = np.linalg.norm(quad[1] - quad[0]); bottom = np.linalg.norm(quad[2] - quad[3])
    left = np.linalg.norm(quad[3] - quad[0]); right = np.linalg.norm(quad[2] - quad[1])
    mw, mh = (top + bottom) / 2.0, (left + right) / 2.0
    if mh <= 0:
        return None
    out_h = max(2, int(round(out_width * mh / mw)))
    dst = np.array([[0, 0], [out_width - 1, 0], [out_width - 1, out_h - 1], [0, out_h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(quad.astype("float32"), dst)
    return cv2.warpPerspective(img, M, (out_width, out_h))

# ------------------------------------------------------------------
# warped-rendition cache (OCR/extraction read the warp; authenticity
# keeps the original — callers choose which path they open)
# ------------------------------------------------------------------

_rendition_cache = {}

def _cache_key(path):
    try:
        st = os.stat(path)
        return (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    except Exception:
        return None

def analyse_path(path):
    """analyse_image for a file, cached by (path, size, mtime)."""
    if cv2 is None or not path:
        return None
    key = _cache_key(path)
    if key is not None and key in _rendition_cache:
        return _rendition_cache[key]["analysis"]
    img = cv2.imread(path)
    if img is None:
        return None
    analysis = analyse_image(img)
    if key is not None:
        _rendition_cache[key] = {"analysis": analysis, "warp_path": None, "_img": img}
        if len(_rendition_cache) > 24:  # keep the cache small; entries hold an image
            _rendition_cache.pop(next(iter(_rendition_cache)))
    return analysis

_WARP_LOCK = threading.Lock()


def warped_rendition(path):
    """Serialised wrapper: the warp lands at a DETERMINISTIC temp
    path (kyc-warp-<digest>.png), so two threads computing it for
    the same source concurrently would interleave cv2.imwrite
    calls on one file and hand OCR a corrupted rendition (measured
    2026-10-27 once _read_document began reading text and words in
    parallel: a perfect slip read back as garbage). The lock makes
    the second caller reuse the finished warp from the cache."""
    with _WARP_LOCK:
        return _warped_rendition_impl(path)


def _warped_rendition_impl(path):
    """-> path of a perspective-warped rendition of the document in
    the image at `path`, or None when no usable quad exists or the
    quad is already the whole frame axis-aligned (warp would be a
    no-op copy). The rendition is a temp file owned by this module."""
    if cv2 is None or not path:
        return None
    key = _cache_key(path)
    analysis = analyse_path(path)
    if analysis is None or analysis.get("quad") is None:
        return None
    # Only a quad the framing CHECK would accept earns a warp. An
    # inner feature (a photo box, a text block) can fit a small quad
    # inside a flat document image; warping to it would make OCR and
    # classification read a fragment as if it were the document
    # (measured: a synthetic slip's photo box, area 0.073, was warped
    # and the slip then "measured" aspect 0.79 and classified fail).
    area = analysis.get("area_ratio") or 0.0
    width_frac = analysis.get("width_frac") or 0.0
    if not (area >= PASS_RATIO or (width_frac >= WIDE_MIN_WIDTH_FRAC and area >= WIDE_PASS_AREA)):
        return None
    if key is not None and _rendition_cache.get(key, {}).get("warp_path"):
        return _rendition_cache[key]["warp_path"]
    quad = analysis["quad"]
    w, h = analysis["width"], analysis["height"]
    # No-op check: quad ≈ the full frame, corners near the image
    # corners — OCR on the original is identical and cheaper.
    corners = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    if analysis["area_ratio"] >= 0.97 and float(np.max(np.abs(quad - corners))) <= max(w, h) * 0.015:
        return None
    img = None
    if key is not None and key in _rendition_cache:
        img = _rendition_cache[key].get("_img")
    if img is None:
        img = cv2.imread(path)
    if img is None:
        return None
    warped = warp_image(img, quad)
    if warped is None:
        return None
    digest = hashlib.sha1((str(key) if key else path).encode()).hexdigest()[:16]
    out = os.path.join(tempfile.gettempdir(), f"kyc-warp-{digest}.png")
    if not cv2.imwrite(out, warped):
        return None
    if key is not None and key in _rendition_cache:
        _rendition_cache[key]["warp_path"] = out
    return out

# ------------------------------------------------------------------
# the check
# ------------------------------------------------------------------

def check_document_framing(path=None, data=None, expected_aspect_range=None):
    if cv2 is None:
        return {"status": "error", "findings": {"error": "opencv_unavailable"}, "reason_codes": ["framing_unavailable"]}
    try:
        if data is not None:
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(path)
    except Exception as e:
        return {"status": "fail", "findings": {"error": f"image_unreadable: {e}"}, "reason_codes": ["invalid_image"]}
    if img is None:
        return {"status": "fail", "findings": {"error": "image_unreadable"}, "reason_codes": ["invalid_image"]}
    h, w = img.shape[:2]
    a = analyse_image(img, expected_aspect_range)
    findings = {"width": w, "height": h, "quad_found": False, "area_ratio": 0.0,
                "largest_contour_ratio": a["largest_contour_ratio"] if a else 0.0,
                "quad": None, "aspect": None, "method": None, "warp_applied": False,
                "fill_rule": None, "texture": None, "border_support": None,
                "ring_contrast": None,
                "aspect_conflict": a.get("aspect_conflict") if a else None}
    if a is None or a.get("quad") is None:
        cand = (a or {}).get("candidate")
        if (a or {}).get("ambiguous_aspect"):
            # The quad quality gate could not resolve WHICH shape is
            # the document (edge and segmentation aspects disagree
            # > 25% with no preference rule able to separate them).
            # Passing either warp downstream would risk deciding on a
            # geometrically distorted document — the honest verdict
            # is a rescan, with both measured aspects on the record.
            if cand:
                findings.update({"area_ratio": cand["area_ratio"], "aspect": cand["aspect"],
                                 "method": cand["method"], "texture": cand["texture"],
                                 "border_support": cand["border_support"],
                                 "ring_contrast": cand["ring_contrast"]})
            return {"status": "unclear", "findings": findings,
                    "reason_codes": ["document_aspect_ambiguous"]}
        # A rejected candidate only earns the "unclear" (rescan)
        # verdict when it carries SOME document evidence — print
        # texture, or an outline the edge map can see at all. A region
        # with neither (border support ~0 AND no texture: a blank
        # stretch of wall that happened to fit a quad) is not a
        # poorly-captured document; it is no document.
        if cand and ((cand["texture"] or {}).get("ok") or (cand["border_support"] or 0) >= 0.15):
            # A quad-shaped region WAS fitted but a gate rejected it
            # (no print texture, or its border is not a real edge /
            # luminance step) — that is a rescan-quality problem, not
            # proof no document is present.
            findings.update({"area_ratio": cand["area_ratio"], "aspect": cand["aspect"],
                             "method": cand["method"], "texture": cand["texture"],
                             "border_support": cand["border_support"],
                             "ring_contrast": cand["ring_contrast"]})
            if not (cand["texture"] or {}).get("ok"):
                return {"status": "unclear", "findings": findings, "reason_codes": ["document_texture_low"]}
            return {"status": "unclear", "findings": findings, "reason_codes": ["document_edges_unclear"]}
        if findings["largest_contour_ratio"] >= 0.5:
            # Something fills the frame but its edges do not resolve
            # to a quadrilateral — a human looks rather than a hard fail.
            return {"status": "unclear", "findings": findings, "reason_codes": ["document_edges_unclear"]}
        return {"status": "fail", "findings": findings, "reason_codes": ["document_not_detected"]}
    quad = a["quad"]
    findings.update({
        "quad_found": True,
        "area_ratio": a["area_ratio"],
        "quad": [[round(float(x) / w, 4), round(float(y) / h, 4)] for x, y in quad],
        "aspect": a["aspect"], "method": a["method"], "texture": a["texture"],
        "border_support": a["border_support"], "ring_contrast": a["ring_contrast"],
    })
    # A found quad is only useful if the warp succeeds — the pipeline
    # will read the document from the warped rendition.
    warped = warp_image(img, quad)
    findings["warp_applied"] = warped is not None
    # Decision-grade geometry gate (2026-10-26, owner session-5 lesson):
    # an accepted quad whose aspect sits in the OUTER QUARTILE of the
    # claimed type's range on WEAK border evidence is not a measured
    # document — it is a guess the warp will bake in as distortion
    # (the NIN-slip capture: segmentation aspect 1.401 in range
    # [1.2, 2.8], border support 0.375, true aspect ~2.20; the
    # distorted warp then failed classification and hid the portrait).
    # The honest verdict is a rescan, never a pass. A truly-measured
    # quad is mid-range or strongly bordered, so genuine captures are
    # unaffected.
    if expected_aspect_range is not None and a.get("aspect"):
        lo, hi = expected_aspect_range
        if hi > lo:
            pos = (a["aspect"] - lo) / (hi - lo)
            findings["aspect_range_position"] = round(pos, 3)
            if (pos <= 0.25 or pos >= 0.75) and (a.get("border_support") or 0) < 0.5:
                findings["geometry_grade"] = "weak"
                return {"status": "unclear", "findings": findings,
                        "reason_codes": ["document_geometry_weak"]}
    ratio = a["area_ratio"]
    if ratio >= PASS_RATIO:
        findings["fill_rule"] = "area"
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if a["width_frac"] >= WIDE_MIN_WIDTH_FRAC and ratio >= WIDE_PASS_AREA:
        findings["fill_rule"] = "wide"
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if ratio >= UNCLEAR_RATIO or (a["width_frac"] >= WIDE_MIN_WIDTH_FRAC and ratio >= WIDE_UNCLEAR_AREA):
        return {"status": "unclear", "findings": findings, "reason_codes": ["document_small_in_frame"]}
    return {"status": "fail", "findings": findings, "reason_codes": ["document_too_small_in_frame"]}

def combine_framing(front_res, back_res=None):
    """Combine per-side framing results into one document_framing check
    (worst status wins). Each side's own result stays in the findings."""
    order = {"pass": 0, "unclear": 1, "error": 2, "not_run": 2, "fail": 3}
    findings = {"front": {"status": front_res["status"], **front_res.get("findings", {})}}
    worst = front_res
    if back_res is not None:
        findings["back"] = {"status": back_res["status"], **back_res.get("findings", {})}
        if order.get(back_res["status"], 2) > order.get(worst["status"], 2):
            worst = back_res
    reasons = list(front_res.get("reason_codes", []))
    if back_res is not None:
        reasons += [r for r in back_res.get("reason_codes", []) if r not in reasons]
    return {"status": worst["status"], "findings": findings, "reason_codes": reasons}
