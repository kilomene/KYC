"""Document authenticity signals (Phase 2).

ONE check whose findings list four independent signals; the combination
decides. A single weak signal NEVER fails a document — strong failures
need combined evidence (points >= 60, and the largest single signal is
worth 50):

  ela          Error Level Analysis (JPEG only). The image is re-saved at
               a known quality; per-block error is measured. A region
               pasted in from a differently-compressed source recompresses
               differently and stands out from the block-error spread.
  metadata     EXIF/PNG text tags naming image editors or screen-capture
               tools ("Photoshop", "GIMP", "OBS", "Screenshot", ...).
  moire        Screen-recapture signal: photographing a screen lays a
               strong periodic high-frequency pattern over the image.
               Measured with an FFT: energy concentration of the strongest
               high-frequency peak relative to the band mean.
  pixel_grid   The display's pixel LATTICE: strong high-frequency FFT
               peaks on BOTH axes (print/text periodicity is one-axis;
               a pixel grid is two). A screen-evidence signal.
  gloss        Specular signature: blown-out highlight blobs on top of
               the scene (screen glare), measured among non-background
               pixels so a clean white document does not fire it.
               A screen-evidence signal.
  gamut        Emissive-display signature: lifted black floor
               (backlight bleed) together with pushed saturation.
               A screen-evidence signal.
  portrait     Portrait-region analysis (card layouts): the classic
               forgery is portrait substitution, so the portrait area
               gets its own manipulation evidence — grain inconsistency
               vs the rest of the card, and region ELA vs whole-image ELA.
  format       Template/format consistency for the DECLARED document:
               document-number pattern, MRZ presence for passports, and
               OCR keywords that should appear on that document type.

SCREEN RULE (owner's order, 2026-10-26): moire PLUS any other screen
signal at moderate or better = a document photographed off a screen:
authenticity FAILS with reason document_on_screen. That combined case
may fail on combined screen evidence alone; every other single weak
signal still never fails a document on its own.

Signals are evidence, not verdicts: pass | unclear | fail(suspected).
"""
import io, re

try:
    from PIL import Image
except Exception:
    Image = None
try:
    import numpy as np
except Exception:
    np = None

EDITOR_WORDS = ("photoshop", "gimp", "canva", "picsart", "snapseed", "pixelmator",
                "affinity photo", "paint.net", "obs studio", "obs", "screenshot",
                "snipping tool", "screen recorder", "sharex", "lightshot")
DOC_KEYWORDS = {
    "passport": ("passport",),
    "drivers_licence": ("driver", "licence", "license", "driving"),
    "national_id": ("identity", "national", "id card"),
}
DOC_NUMBER_PATTERNS = {
    # Generic-but-real shape rules for declared numbers; a mismatch is a
    # format signal only (numbers vary legitimately by issuer/year).
    "passport": re.compile(r"^[A-Z0-9]{6,12}$"),
    "drivers_licence": re.compile(r"^[A-Z0-9\-]{5,20}$"),
    "national_id": re.compile(r"^[A-Z0-9\-]{5,20}$"),
}

def ela_signal(path):
    """Block-wise ELA spread for a JPEG. Returns {name, strength, score}.

    The image is re-saved at quality 92 and the per-block (16x16) mean
    error distribution is measured. A uniformly-compressed photo has a
    tight distribution. A spliced region — pasted in after the photo's
    own compression, or taken from a differently-compressed source —
    sits on a different error floor, stretching one tail of the
    distribution: score = max(p95 - median, median - p5).
    Calibrated 2026-10-26 on synthetic structured photos stored at
    q88: clean 0.25, q40-source splice 0.65, smooth cover-up splice
    0.81. (A naive p95-median at resave q90 measured ~0 for everything:
    re-saving at the encoder's own quality is near-idempotent, which is
    why the resave here uses a different quality and both tails.)"""
    out = {"name": "ela", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        with Image.open(path) as im0:
            fmt = im0.format
            if fmt != "JPEG":
                out["detail"] = f"format_{fmt}_ela_is_jpeg_only"
                return out
            im = im0.copy()
        orig = im.convert("L")
        buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92)
        buf.seek(0)
        resaved = Image.open(buf).convert("L")
        a = np.asarray(orig, dtype=np.float64); b = np.asarray(resaved, dtype=np.float64)
        if a.shape != b.shape:
            out["strength"] = "unavailable"; return out
        err = np.abs(a - b)
        B = 16
        h, w = err.shape
        blocks = []
        for y in range(0, h - B + 1, B):
            for x in range(0, w - B + 1, B):
                blocks.append(float(err[y:y + B, x:x + B].mean()))
        if len(blocks) < 16:
            out["strength"] = "unavailable"; return out
        blocks = np.array(blocks)
        med = float(np.median(blocks))
        hi = float(np.percentile(blocks, 95)) - med
        lo = med - float(np.percentile(blocks, 5))
        score = max(hi, lo)
        out["score"] = round(score, 3)
        out["median_block_error"] = round(med, 3)
        out["tail_spread_hi"] = round(hi, 3); out["tail_spread_lo"] = round(lo, 3)
        out["strength"] = "strong" if score >= 0.7 else ("moderate" if score >= 0.45 else "none")
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def metadata_signal(path):
    """Editor / capture-tool fingerprints in EXIF or PNG text chunks."""
    out = {"name": "metadata", "strength": "none", "tags": {}}
    if Image is None:
        out["strength"] = "unavailable"; return out
    try:
        im = Image.open(path); im.load()
        tags = {}
        try:
            exif = im.getexif()
            for tag_id, val in exif.items():
                name = {271: "Make", 272: "Model", 305: "Software", 315: "Artist", 306: "DateTime"}.get(tag_id)
                if name and val:
                    tags[name] = str(val)[:80]
        except Exception:
            pass
        for k, v in (getattr(im, "text", None) or {}).items():
            tags[str(k)] = str(v)[:80]
        for k, v in (im.info or {}).items():
            if isinstance(v, str) and k.lower() in ("software", "comment", "description"):
                tags[k] = v[:80]
        out["tags"] = tags
        joined = " ".join(tags.values()).lower()
        hits = [w for w in EDITOR_WORDS if w in joined]
        if hits:
            out["strength"] = "strong"; out["editor_hits"] = hits
        out["has_camera_make_model"] = bool(tags.get("Make") or tags.get("Model"))
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def moire_signal(path):
    """FFT periodic-peak signal typical of photographing a screen."""
    out = {"name": "moire", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        with Image.open(path) as im0:
            im = im0.convert("L")
        im.thumbnail((512, 512))
        a = np.asarray(im, dtype=np.float64)
        if a.size < 64 * 64:
            out["strength"] = "unavailable"; return out
        a = a - a.mean()
        F = np.abs(np.fft.rfft2(a))
        h, w = F.shape
        yy, xx = np.mgrid[0:h, 0:w]
        # rfft2 is not fftshifted: row frequencies wrap, so the distance
        # of row i is min(i, h-i). Getting this wrong (measuring from the
        # array centre) lets low-frequency scene energy into the "high
        # frequency" band and the peak stops meaning moire at all.
        fy = np.minimum(yy, h - yy)
        radius = np.sqrt((fy ** 2) + (xx ** 2))
        band = F[(radius > 40)]
        if band.size == 0:
            out["strength"] = "unavailable"; return out
        # Score = the strongest peak's share of the band's total energy.
        # A plain peak/mean ratio is NOT used: it explodes on sparse
        # images. Energy share separates cleanly — measured 2026-10-26
        # (after the rfft wrap fix below): structured photo 0.05, text
        # document image 0.10, blurred texture 0.04, full-frame periodic
        # grating 0.59.
        peak_share = float(band.max()) / float(np.sqrt((band ** 2).sum()) or 1e-9)
        out["score"] = round(peak_share, 3)
        out["peak_to_mean"] = round(float(band.max()) / (float(band.mean()) or 1e-9), 1)
        out["strength"] = "strong" if peak_share >= 0.35 else ("moderate" if peak_share >= 0.20 else "none")
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def _gray_array(path, max_dim=512):
    with Image.open(path) as im0:
        im = im0.convert("L")
    im.thumbnail((max_dim, max_dim))
    return np.asarray(im, dtype=np.float64)

def pixel_grid_signal(path):
    """Display pixel-lattice periodicity: strong high-frequency FFT
    peaks on BOTH axes. Score = the weaker axis's peak energy share in
    its high-frequency band (a lattice must show on both)."""
    out = {"name": "pixel_grid", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        a = _gray_array(path)
        if a.size < 64 * 64:
            out["strength"] = "unavailable"; return out
        a = a - a.mean()
        F = np.abs(np.fft.rfft2(a))
        h, w = F.shape
        def axis_share(profile, dist):
            if dist.size == 0 or dist.max() == 0:
                return 0.0
            band = profile[dist > 0.22 * dist.max()]
            if band.size == 0:
                return 0.0
            return float(band.max()) / (float(np.sqrt((band ** 2).sum())) or 1e-9)
        col_profile = F.sum(axis=0)
        row_profile = F.sum(axis=1)
        row_dist = np.minimum(np.arange(h), h - np.arange(h))
        xs = axis_share(col_profile, np.arange(w))
        ys = axis_share(row_profile, row_dist)
        score = min(xs, ys)
        out["score"] = round(score, 3)
        out["x_share"] = round(xs, 3); out["y_share"] = round(ys, 3)
        out["strength"] = "strong" if score >= 0.30 else ("moderate" if score >= 0.18 else "none")
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def gloss_signal(path):
    """Specular/gloss signature: near-saturated highlight pixels among
    NON-background pixels (background = within 8 levels of the modal
    luminance — a white ID's paper is background, not glare)."""
    out = {"name": "gloss", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        a = _gray_array(path)
        if a.size < 64 * 64:
            out["strength"] = "unavailable"; return out
        vals, counts = np.unique(a.astype(np.int32), return_counts=True)
        modal = float(vals[int(counts.argmax())])
        nonbg = a[np.abs(a - modal) > 8]
        if nonbg.size < 500:
            out["detail"] = "flat_image_no_nonbackground_pixels"
            return out
        frac = float((nonbg > 248).mean())
        out["score"] = round(frac, 3)
        out["modal_luminance"] = modal
        out["strength"] = "strong" if frac >= 0.20 else ("moderate" if frac >= 0.08 else "none")
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def gamut_signal(path):
    """Emissive-display signature: lifted black floor (2nd-percentile
    luminance — backlight bleed means a photographed screen has no
    true blacks) TOGETHER with pushed mean saturation."""
    out = {"name": "gamut", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        with Image.open(path) as im0:
            im = im0.convert("RGB")
        im.thumbnail((512, 512))
        a = np.asarray(im, dtype=np.float64)
        if a.size < 64 * 64 * 3:
            out["strength"] = "unavailable"; return out
        lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
        mx = a.max(axis=2); mn = a.min(axis=2)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
        black_floor = float(np.percentile(lum, 2))
        mean_sat = float(sat.mean())
        out["score"] = round(black_floor, 1)
        out["black_floor_p2"] = round(black_floor, 1)
        out["mean_saturation"] = round(mean_sat, 3)
        out["strength"] = "moderate" if (black_floor >= 34 and mean_sat >= 0.30) else "none"
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def _ela_err(im_rgb):
    """|original - q92 resave| luminance error array, or None."""
    orig = im_rgb.convert("L")
    buf = io.BytesIO(); im_rgb.convert("RGB").save(buf, "JPEG", quality=92)
    buf.seek(0)
    resaved = Image.open(buf).convert("L")
    a = np.asarray(orig, dtype=np.float64); b = np.asarray(resaved, dtype=np.float64)
    if a.shape != b.shape:
        return None
    return np.abs(a - b)

def _block_spread(err, B=16):
    """(score, median) of per-block mean errors, or (None, None)."""
    h, w = err.shape
    blocks = []
    for y in range(0, h - B + 1, B):
        for x in range(0, w - B + 1, B):
            blocks.append(float(err[y:y + B, x:x + B].mean()))
    if len(blocks) < 16:
        return None, None
    blocks = np.array(blocks)
    med = float(np.median(blocks))
    score = max(float(np.percentile(blocks, 95)) - med, med - float(np.percentile(blocks, 5)))
    return score, med

def portrait_region_signal(path):
    """Portrait-substitution analysis. On card layouts the portrait
    sits in a predictable zone (left on landscape cards, upper area on
    portrait-orientation captures). Two sub-measures compare the region
    against the rest of the document:
      grain ratio — high-frequency energy in the region vs the rest; a
        pasted portrait (resized/smoothed/airbrushed) carries visibly
        different grain. Needs a grainy baseline: flat synthetic images
        are honestly not_applicable.
      region ELA — the region crop's block-error spread vs the whole
        image's (JPEG only); a splice recompresses differently.
    Strong on either sub-measure = strong; the caller turns a strong
    portrait signal into the named finding portrait_region_tamper."""
    out = {"name": "portrait", "strength": "not_applicable", "score": None}
    if Image is None or np is None:
        out["strength"] = "unavailable"; return out
    try:
        with Image.open(path) as im0:
            fmt = im0.format
            im = im0.convert("RGB")
        w, h = im.size
        if w >= h:
            box = (int(0.04 * w), int(0.16 * h), int(0.36 * w), int(0.80 * h))
        else:
            box = (int(0.06 * w), int(0.06 * h), int(0.46 * w), int(0.38 * h))
        out["region_box_frac"] = [round(box[0] / w, 2), round(box[1] / h, 2), round(box[2] / w, 2), round(box[3] / h, 2)]
        strengths = []
        # --- grain ratio (PIL blur difference, same trick as capture quality)
        from PIL import ImageChops, ImageFilter, ImageStat
        grey = im.convert("L")
        diff = ImageChops.difference(grey, grey.filter(ImageFilter.GaussianBlur(radius=2)))
        da = np.asarray(diff, dtype=np.float64)
        mask = np.zeros(da.shape, dtype=bool)
        mask[box[1]:box[3], box[0]:box[2]] = True
        rest = da[~mask]; region = da[mask]
        if rest.size and region.size:
            rest_mean = float(rest.mean()); region_mean = float(region.mean())
            out["grain_region"] = round(region_mean, 2); out["grain_rest"] = round(rest_mean, 2)
            if rest_mean >= 0.8:
                ratio = region_mean / rest_mean
                out["grain_ratio"] = round(ratio, 3)
                # Calibrated 2026-10-26: a blurred portrait splice reads
                # 0.02; a clean photo ~1.0; the drawn synthetic ID reads
                # 2.28 on the HIGH side because its portrait zone carries
                # the printed name text (more edges, not tampering) — so
                # the high-side bands sit well above that, and the
                # sensitive direction is the LOW side (smoothed paste).
                if ratio < 0.45 or ratio > 3.4:
                    strengths.append("strong")
                elif ratio < 0.65 or ratio > 2.6:
                    strengths.append("moderate")
                else:
                    strengths.append("none")
        # --- region ELA vs whole-image ELA (JPEG only)
        if fmt == "JPEG":
            whole_err = _ela_err(im)
            crop_err = _ela_err(im.crop(box))
            if whole_err is not None and crop_err is not None:
                whole_score, _ = _block_spread(whole_err)
                crop_score, _ = _block_spread(crop_err)
                if whole_score is not None and crop_score is not None:
                    out["ela_region"] = round(crop_score, 3); out["ela_whole"] = round(whole_score, 3)
                    if crop_score >= 0.7 and crop_score > 2.0 * max(whole_score, 0.05):
                        strengths.append("strong")
                    elif crop_score >= 0.5 and crop_score > 1.6 * max(whole_score, 0.05):
                        strengths.append("moderate")
                    else:
                        strengths.append("none")
        if not strengths:
            return out
        out["strength"] = "strong" if "strong" in strengths else ("moderate" if "moderate" in strengths else "none")
        out["score"] = out.get("grain_ratio")
        return out
    except Exception as e:
        out["strength"] = "unavailable"; out["detail"] = str(e)[:120]
        return out

def _portrait_box(w, h):
    if w >= h:
        return (int(0.04 * w), int(0.16 * h), int(0.36 * w), int(0.80 * h))
    return (int(0.06 * w), int(0.06 * h), int(0.46 * w), int(0.38 * h))

# ---------------- security-feature pack (Addition 10B) ----------------
# Four further signals, each calibrated, none failing alone except as
# combined evidence through the points total — the same doctrine as
# the rest of this module.

def font_consistency_signal(path, kind=None, country=None):
    """Glyph-height consistency inside the name zone and the document
    number zone (tesseract TSV word boxes). Genuine documents print a
    field in ONE font at ONE size; an altered digit/letter pasted or
    re-rendered shows up as a height outlier and inflates the zone's
    height variance. Named finding when strong: altered_text_suspect."""
    out = {"name": "font_consistency", "strength": "not_applicable", "score": None}
    try:
        from . import vision as V
        from . import templates as T
    except Exception:
        out["strength"] = "unavailable"; return out
    try:
        words = V.ocr_words(path)
    except Exception:
        words = []
    if len(words) < 3:
        return out
    tpl, _lvl = T.get_template(country or "", kind or "")
    zones = {"name_zone": (0.03, 0.08, 0.98, 0.45),
             "number_zone": (tpl or {}).get("number_zone") or (0.45, 0.05, 0.98, 0.35)}
    worst_cv, total_outliers, detail = 0.0, 0, {}
    for zname, (zx0, zy0, zx1, zy1) in zones.items():
        hs = [(wd["box"][3] - wd["box"][1]) for wd in words
              if zx0 <= (wd["box"][0] + wd["box"][2]) / 2 <= zx1
              and zy0 <= (wd["box"][1] + wd["box"][3]) / 2 <= zy1]
        if len(hs) < 3:
            continue
        hs = np.array(hs, dtype=float)
        med = float(np.median(hs))
        cv = float(hs.std() / hs.mean()) if hs.mean() else 0.0
        outliers = int(np.sum(np.abs(hs - med) > 0.45 * med)) if med else 0
        detail[zname] = {"words": len(hs), "cv": round(cv, 3), "outliers": outliers}
        worst_cv = max(worst_cv, cv)
        total_outliers += outliers
    if not detail:
        return out
    out["score"] = round(worst_cv, 3)
    out["zones"] = detail
    if worst_cv > 0.55 or total_outliers >= 2:
        out["strength"] = "strong"
    elif worst_cv > 0.35 or total_outliers == 1:
        out["strength"] = "moderate"
    else:
        out["strength"] = "none"
    return out

def compositing_edges_signal(path):
    """Paste-boundary (halo) analysis around the portrait region: the
    gradient magnitude ON the region's rectangular border vs inside
    it. A pasted portrait patch ends at a hard rectangular step; a
    genuine printed portrait has no such rectangle. Named finding
    when strong: compositing_suspect."""
    out = {"name": "compositing_edges", "strength": "not_applicable", "score": None}
    if np is None:
        out["strength"] = "unavailable"; return out
    try:
        g = _gray_array(path)
        if g is None:
            return out
        h, w = g.shape
        gy, gx = np.gradient(g.astype(float))
        mag = np.hypot(gx, gy)
        x0, y0, x1, y1 = _portrait_box(w, h)
        t = 3
        strips = [mag[max(0, y0 - t):y0 + t + 1, x0:x1], mag[y1 - t:y1 + t + 1, x0:x1],
                  mag[y0:y1, max(0, x0 - t):x0 + t + 1], mag[y0:y1, x1 - t:x1 + t + 1]]
        ring = float(np.mean([s.mean() for s in strips if s.size]))
        inner = mag[y0 + 12:y1 - 12, x0 + 12:x1 - 12]
        interior = float(inner.mean()) if inner.size else 0.0
        # Calibrated 2026-10-26: pasted-blur splice ring/interior =
        # 3.2, clean drawn card = 0.30, room photo = 0.96. The floor
        # only guards a pathologically flat interior.
        ratio = ring / max(interior, 0.25)
        out["score"] = round(ratio, 3)
        out["ring_gradient"] = round(ring, 2)
        out["interior_gradient"] = round(interior, 2)
        out["strength"] = "strong" if ratio > 2.6 else ("moderate" if ratio > 1.6 else "none")
        return out
    except Exception:
        out["strength"] = "unavailable"; return out

def border_edges_signal(path):
    """Document-border double-edge / ghosting detection: for each
    side band, the edge profile (mean gradient per row/column) should
    show ONE dominant border line. A second strong parallel peak a
    few pixels away = a ghosted/duplicated border — a compositing
    tell. Named finding when strong: suspicious_edges."""
    out = {"name": "border_edges", "strength": "not_applicable", "score": None}
    if np is None:
        out["strength"] = "unavailable"; return out
    try:
        g = _gray_array(path, max_dim=1024)
        if g is None:
            return out
        h, w = g.shape
        gy, gx = np.gradient(g.astype(float))
        # 60th-percentile profile: a genuine document border spans the
        # FULL side, so it survives a percentile across the axis;
        # partial scene edges (a room photo's shelves/windows) do not.
        row_prof = np.percentile(np.abs(gy), 60, axis=1)
        col_prof = np.percentile(np.abs(gx), 60, axis=0)

        def ghosted(profile, lo, hi):
            # Runs of above-half-max profile: ONE border line makes
            # ONE run (its two gradient edges sit ~3px apart); a
            # ghosted/duplicated border makes a SECOND run whose
            # centre is 6-24px away with a deep valley between.
            # Calibrated 2026-10-26 on the fixtures: clean card runs
            # are 3px apart (not ghosted); a border drawn twice 7px
            # apart produces runs 6px apart with a zero valley.
            band = profile[int(lo * len(profile)):int(hi * len(profile))]
            if band.size < 24:
                return False
            v1 = float(band.max())
            if v1 < 2.0:
                return False
            runs = []
            j = 0
            while j < band.size:
                if band[j] > 0.5 * v1:
                    k = j
                    while k + 1 < band.size and band[k + 1] > 0.5 * v1:
                        k += 1
                    runs.append((j, k))
                    j = k + 1
                else:
                    j += 1
            for a in range(len(runs) - 1):
                c1 = (runs[a][0] + runs[a][1]) / 2
                c2 = (runs[a + 1][0] + runs[a + 1][1]) / 2
                if 6 <= (c2 - c1) <= 24:
                    valley = float(band[runs[a][1]:runs[a + 1][0] + 1].min()) if runs[a + 1][0] > runs[a][1] else v1
                    if valley < 0.3 * v1:
                        return True
            return False

        sides = {"top": ghosted(row_prof, 0.0, 0.18), "bottom": ghosted(row_prof, 0.82, 1.0),
                 "left": ghosted(col_prof, 0.0, 0.15), "right": ghosted(col_prof, 0.85, 1.0)}
        n = sum(1 for v in sides.values() if v)
        out["score"] = n
        out["sides"] = sides
        out["strength"] = "strong" if n >= 2 else ("moderate" if n == 1 else "none")
        return out
    except Exception:
        out["strength"] = "unavailable"; return out

def pattern_presence_signal(path, kind=None, country=None):
    """Background pattern presence: real card/paper stock carries
    printed background texture (guilloche/print grain). In the
    non-text part of the lower document, flat synthetic fill (a
    rendered fake) has almost no texture energy. Only evaluated when
    the type's template expects a pattern (pattern_expected); named
    finding when strong: missing_pattern."""
    out = {"name": "pattern_presence", "strength": "not_applicable", "score": None}
    if np is None:
        out["strength"] = "unavailable"; return out
    try:
        from . import templates as T
        from . import vision as V
    except Exception:
        out["strength"] = "unavailable"; return out
    tpl, _lvl = T.get_template(country or "", kind or "")
    if not tpl or not tpl.get("pattern_expected"):
        return out
    try:
        g = _gray_array(path, max_dim=640)
        if g is None:
            return out
        h, w = g.shape
        region = g[int(0.66 * h):, :]
        rh = region.shape[0]
        mask = np.ones(region.shape, dtype=bool)
        try:
            for wd in V.ocr_words(path):
                bx0, by0, bx1, by1 = wd["box"]
                if (by0 + by1) / 2 >= 0.62:
                    x0 = max(0, int((bx0 - 0.02) * w)); x1 = min(w, int((bx1 + 0.02) * w))
                    y0 = max(0, int((by0 - 0.02) * h) - int(0.66 * h)); y1 = min(rh, int((by1 + 0.02) * h) - int(0.66 * h))
                    if y1 > y0:
                        mask[y0:y1, x0:x1] = False
        except Exception:
            pass
        if mask.sum() < 0.05 * mask.size:
            return out
        gf = region.astype(float)
        lap = -4 * gf[1:-1, 1:-1] + gf[:-2, 1:-1] + gf[2:, 1:-1] + gf[1:-1, :-2] + gf[1:-1, 2:]
        m = mask[1:-1, 1:-1]
        energy = float(np.var(lap[m])) if m.any() else 0.0
        out["score"] = round(energy, 2)
        out["strength"] = "strong" if energy < 1.5 else ("moderate" if energy < 6.0 else "none")
        return out
    except Exception:
        out["strength"] = "unavailable"; return out

def format_signal(kind, country, doc_number, ocr_text, mrz_found):
    """Declared-document format consistency."""
    out = {"name": "format", "strength": "none"}
    problems = []
    pat = DOC_NUMBER_PATTERNS.get(kind)
    if doc_number and pat:
        cleaned = re.sub(r"\s+", "", str(doc_number)).upper()
        if not pat.match(cleaned):
            problems.append("document_number_pattern")
        out["document_number_checked"] = cleaned
    text_up = (ocr_text or "").upper()
    kws = DOC_KEYWORDS.get(kind, ())
    if kws and text_up:
        if not any(k.upper() in text_up for k in kws):
            problems.append("expected_keyword_missing")
    if kind == "passport":
        out["mrz_found"] = bool(mrz_found)
        # A passport with no readable MRZ at all is a format signal, not
        # proof of forgery (MRZ has its own check) — counted once here.
        if not mrz_found:
            problems.append("passport_without_mrz")
    out["problems"] = problems
    if not problems:
        out["strength"] = "none"
    elif problems == ["passport_without_mrz"]:
        # Weak only: the MRZ absence is already scored by the MRZ check;
        # counting it at full weight here would double-punish one fact.
        out["strength"] = "weak"
    else:
        out["strength"] = "moderate"
    return out

POINTS = {("ela", "strong"): 50, ("ela", "moderate"): 25,
          ("metadata", "strong"): 30,
          ("moire", "strong"): 40, ("moire", "moderate"): 20,
          ("pixel_grid", "strong"): 30, ("pixel_grid", "moderate"): 15,
          ("gloss", "strong"): 20, ("gloss", "moderate"): 10,
          ("gamut", "moderate"): 10,
          ("portrait", "strong"): 30, ("portrait", "moderate"): 15,
          ("font_consistency", "strong"): 25, ("font_consistency", "moderate"): 12,
          ("compositing_edges", "strong"): 25, ("compositing_edges", "moderate"): 12,
          ("border_edges", "strong"): 15, ("border_edges", "moderate"): 8,
          ("pattern_presence", "strong"): 20, ("pattern_presence", "moderate"): 10,
          ("format", "moderate"): 30, ("format", "weak"): 10}

SCREEN_SIGNALS = ("moire", "pixel_grid", "gloss", "gamut")

# Signal families (2026-10-28 recalibration). The census over the
# owner's labelled corpus (14 genuine documents, 8 subjects) showed
# the ELA, font-consistency and compositing signals firing at full
# strength on GENUINE phone photos — 9 of 14 genuine documents scored
# in the old hard-fail zone (>= 60 points) on those signals alone.
# The three measure the same underlying artefact class (post-capture
# compression/editing inconsistency, which ordinary phone pipelines
# produce on real documents), so they count as ONE family: a points
# hard-fail now requires corroboration from at least two INDEPENDENT
# non-edit families at moderate or better. Fitted against the census:
# every genuine document lands pass/unclear; the labelled fake still
# fails (provenance + portrait families corroborate).
SIGNAL_FAMILIES = {"edit": ("ela", "font_consistency", "compositing_edges"),
                   "screen": ("moire", "pixel_grid", "gloss", "gamut"),
                   "provenance": ("metadata",),
                   "portrait": ("portrait",),
                   "structure": ("border_edges", "pattern_presence"),
                   "data": ("format",)}

def _signal_families(signals):
    """Map each family to the strongest member strength present."""
    rank = {"none": 0, "not_applicable": 0, "weak": 1, "moderate": 2, "strong": 3}
    by_name = {s["name"]: s["strength"] for s in signals}
    out = {}
    for family, members in SIGNAL_FAMILIES.items():
        best = "none"
        for m in members:
            if rank.get(by_name.get(m, "none"), 0) > rank[best]:
                best = by_name[m]
        out[family] = best
    return out

def _verdict_from_signals(signals):
    """Pure verdict over a computed signal list (split out of
    check_authenticity so the calibration rules are unit-testable
    without images)."""
    by_name = {s["name"]: s for s in signals}
    total = sum(POINTS.get((s["name"], s["strength"]), 0) for s in signals)
    # Screen rule: moire + ANY other screen signal at moderate or
    # better = photographed off a display -> document_on_screen.
    screen_evidence = [n for n in SCREEN_SIGNALS if by_name[n]["strength"] in ("moderate", "strong")]
    screen_detected = "moire" in screen_evidence and len(screen_evidence) >= 2
    portrait_tamper = by_name["portrait"]["strength"] == "strong"
    families = _signal_families(signals)
    corroborating = sorted(f for f, st in families.items()
                           if f != "edit" and st in ("moderate", "strong"))
    corroborated = len(corroborating) >= 2
    findings = {"signals": signals, "signal_points": total,
                "screen_detected": screen_detected, "screen_evidence": screen_evidence,
                "families": families, "corroborating_families": corroborating,
                "corroborated": corroborated,
                "note": "combined evidence decides; one weak signal alone never fails a document; "
                        "moire + another screen signal = document_on_screen; "
                        "a points hard-fail needs >= 60 points corroborated by >= 2 "
                        "independent non-edit signal families (2026-10-28 recalibration)"}
    extra = []
    if portrait_tamper:
        extra.append("portrait_region_tamper")
    # Security-feature pack (Addition 10B): strong signals become
    # named findings on the case alongside the points they carry.
    # altered_text_suspect is gated on provenance corroboration
    # (2026-10-28): font_consistency strong fired on 13 of 14 genuine
    # corpus documents, so uncorroborated it annotates noise, not
    # evidence; with a metadata trace present it names a real edit.
    for _sig_name, _reason in (("font_consistency", "altered_text_suspect"),
                               ("compositing_edges", "compositing_suspect"),
                               ("border_edges", "suspicious_edges"),
                               ("pattern_presence", "missing_pattern")):
        if by_name[_sig_name]["strength"] != "strong":
            continue
        if _reason == "altered_text_suspect" and \
                by_name["metadata"]["strength"] not in ("moderate", "strong"):
            continue
        extra.append(_reason)
    if screen_detected:
        return {"status": "fail", "findings": findings,
                "reason_codes": ["document_on_screen"] + extra}
    if total >= 60 and corroborated:
        strong_names = [s["name"] for s in signals if POINTS.get((s["name"], s["strength"]), 0) >= 20]
        return {"status": "fail", "findings": findings,
                "reason_codes": ["suspected_tamper" if "ela" in strong_names else "suspected_recapture_or_edit"] + extra}
    if total >= 25:
        return {"status": "unclear", "findings": findings, "reason_codes": ["authenticity_signals_present"] + extra}
    return {"status": "pass", "findings": findings, "reason_codes": extra}

def check_authenticity(path, kind=None, country=None, doc_number=None, ocr_text="", mrz_found=False):
    signals = [ela_signal(path), metadata_signal(path), moire_signal(path),
               pixel_grid_signal(path), gloss_signal(path), gamut_signal(path),
               portrait_region_signal(path),
               font_consistency_signal(path, kind, country),
               compositing_edges_signal(path), border_edges_signal(path),
               pattern_presence_signal(path, kind, country),
               format_signal(kind or "", country or "", doc_number, ocr_text, mrz_found)]
    return _verdict_from_signals(signals)
