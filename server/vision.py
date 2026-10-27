"""Vision OCR layer (2026-10-26, "Fortified Vision" pass 1).

Three capabilities, all fail-closed, none trusted blindly:

1. MULTI-PASS OCR. Tesseract reads the document twice — the known-good
   plain pass (greyscale + 2x upscale, --psm 3) and an adaptive-
   threshold pass (OpenCV adaptiveThreshold, which rescues text on
   unevenly-lit plastic) — each with word confidences from TSV output.
   The better read wins: if exactly one pass yields a check-digit-VALID
   MRZ, that pass wins outright (a valid MRZ is the strongest field
   signal there is); otherwise the higher mean word confidence wins.

2. MRZ <-> VIZ CROSS-VALIDATION. When an MRZ parses valid, its fields
   are compared against the VISUAL zone (the non-MRZ OCR lines):
   label-anchored DOB / EXPIRY dates, the surname, and the document
   number. A material disagreement (a labelled VIZ date that differs
   from the MRZ date) is a fail with reason mrz_viz_mismatch — a forged
   or altered document must fool BOTH zones consistently. Fields the
   VIZ does not label are recorded as not compared, never guessed.

3. MACHINE-READABLE CODE DECODING. QR codes are decoded with OpenCV
   (NIN slip / PhilID / Aadhaar-style codes). PDF417 and other barcodes
   are decoded with zxing-cpp WHEN it is installed (it is an optional
   dependency — absence degrades to "unavailable", never an error);
   a US/CA licence-back PDF417 is parsed for AAMVA elements (DAQ number,
   DCS/DAC names, DBB dob, DBA expiry) and cross-checked against the
   document fields: disagreement is a fail with reason
   code_decode_mismatch. Decoded content is evidence, never truth —
   it must AGREE with the rest of the document or it counts against it.

Phase 4 WS1 (2026-10-26) added the surrounding layers: per-document
field-extraction templates live in server/fieldtemplates.py, payload
semantics (full AAMVA parse, NIN-slip QR, Aadhaar secure QR, PhilID
QR) in server/payloads.py, and the labelled accuracy benchmark in
scripts/benchmark_vision.py (results in benchmarks/RESULTS.md).

Paper rectification (2026-10-26): OCR reads the document from its
perspective-WARPED rendition when server/framing.py finds a quad —
a hand-held, bowed paper document (the Nigerian NIN slip) is read
flat, not at an angle. The warp is a rendition FOR READING ONLY:
authenticity / screen / forgery analysis always runs on the original
capture (callers pass the original path there, and nothing in this
module changes what they see).
"""
import io, os, re, shutil, subprocess, tempfile
from datetime import date

try:
    from PIL import Image
except Exception:
    Image = None
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None
try:
    import zxingcpp
except Exception:
    zxingcpp = None

from . import checks as C

# ---------------- 1. multi-pass OCR ----------------

def _tesseract_tsv(exe, img_path, psm="3"):
    """Run tesseract with TSV output. Returns (text, mean_word_conf).
    Lines are reconstructed from block/par/line groups so the MRZ
    finder still sees real lines. Raises on hard failure."""
    out = subprocess.run([exe, img_path, "stdout", "--psm", psm, "tsv"],
                         capture_output=True, text=True, timeout=60)
    rows = (out.stdout or "").splitlines()
    if not rows:
        return "", -1.0
    lines = {}
    order = []
    confs = []
    for row in rows[1:]:
        parts = row.split("\t")
        if len(parts) != 12 or parts[0] != "5":
            continue
        try:
            conf = float(parts[10])
        except Exception:
            conf = -1.0
        word = parts[11]
        if not word:
            continue
        key = (parts[2], parts[3], parts[4])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
        if conf >= 0:
            confs.append(conf)
    text = "\n".join(" ".join(lines[k]) for k in order).strip()
    mean_conf = (sum(confs) / len(confs)) if confs else -1.0
    return text, mean_conf

def _prep_variants(path):
    """Yield (name, temp_png_path) OCR inputs. Caller deletes temps."""
    variants = []
    if Image is None:
        return variants
    im = Image.open(path).convert("L")
    im2 = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
    im2.save(tmp, format="PNG")
    variants.append(("plain", tmp))
    if cv2 is not None:
        try:
            import numpy as _np
            arr = _np.array(im2)
            thr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 31, 12)
            fd, tmp2 = tempfile.mkstemp(suffix=".png"); os.close(fd)
            cv2.imwrite(tmp2, thr)
            variants.append(("adaptive", tmp2))
        except Exception:
            pass
    return variants

def _mrz_band_text(path, exe):
    """Dedicated MRZ-zone pass. Full-page segmentation consistently
    skips the MRZ lines on bordered documents (measured 2026-10-26:
    psm 3/4/6 full-page read 53-110 chars and NO MRZ; a band containing
    ONLY the MRZ zone at psm 6 read it cleanly — while a tall band
    including the busy region below the MRZ read as gibberish). So the
    pass tries focused horizontal strips in order — mid-page (where
    test/specimen layouts put it), bottom (real TD3 data pages), then
    the whole lower half — and keeps the first strip that yields MRZ
    lines. Returns raw text ('' when unavailable)."""
    if Image is None:
        return ""
    try:
        im = Image.open(path).convert("L")
    except Exception:
        return ""
    last = ""
    for y0f, y1f in ((0.40, 0.72), (0.68, 1.0), (0.45, 1.0)):
        tmp = None
        try:
            band = im.crop((0, int(im.height * y0f), im.width, int(im.height * y1f)))
            band = band.resize((band.width * 2, band.height * 2), Image.LANCZOS)
            fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
            band.save(tmp, format="PNG")
            out = subprocess.run([exe, tmp, "stdout", "--psm", "6"],
                                 capture_output=True, text=True, timeout=60)
            last = (out.stdout or "").strip()
        except Exception:
            last = ""
        finally:
            if tmp:
                try: os.unlink(tmp)
                except Exception: pass
        if last and C.find_mrz_lines(last)[1]:
            return last
    return last

def _portrait_orientation(im0, expected_aspect_range=None):
    """Orientation from the document's printed portrait — the third
    decider, for the case the text deciders cannot see. Tesseract's
    page segmentation auto-rotates text internally, which can erase
    the OCR-score evidence entirely (measured on a sideways slip
    photographed on a table: 27.9k as-is vs 27.8k corrected — a
    tie), and OSD is blind on noisy photos. A printed face is not
    ambiguous: YuNet detects faces upright and essentially never
    sideways or upside-down, and the landmark order (eyes above
    nose above mouth) confirms the direction. Returns the CW angle
    whose rotation puts a qualifying face upright, or None when no
    rotation qualifies decisively."""
    try:
        if cv2 is None:
            return None
        from . import face as FACE
        if not FACE.models_present():
            return None
        import numpy as _np
        img = cv2.cvtColor(_np.array(im0), cv2.COLOR_RGB2BGR)
        try:
            from . import framing as FRAMING
            a = FRAMING.analyse_image(img, expected_aspect_range)
            if a and a.get("quad") is not None:
                q = _np.array(a["quad"], dtype="float64")
                H, W = img.shape[:2]
                x0 = int(max(0, q[:, 0].min())); x1 = int(min(W, q[:, 0].max()))
                y0 = int(max(0, q[:, 1].min())); y1 = int(min(H, q[:, 1].max()))
                if x1 - x0 > 80 and y1 - y0 > 80:
                    img = img[y0:y1, x0:x1]
        except Exception:
            pass
        results = {}
        for angle in (0, 90, 180, 270):
            try:
                rot = img if angle == 0 else _np.rot90(img, k=(4 - angle // 90) % 4)
                for f in FACE.detect_faces(rot):
                    score = float(f[14]) if len(f) > 14 else 0.0
                    if score < 0.75:
                        continue
                    eye_y = max(float(f[5]), float(f[7]))
                    nose_y = float(f[9])
                    mouth_y = min(float(f[11]), float(f[13]))
                    fh = float(f[3]) or 1.0
                    if eye_y < nose_y - 0.02 * fh and nose_y < mouth_y - 0.02 * fh:
                        if score > results.get(angle, 0.0):
                            results[angle] = score
                        break
            except Exception:
                continue
        if not results:
            return None
        ranked = sorted(results.items(), key=lambda kv: -kv[1])
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.10:
            return None  # two orientations claim a face — not decisive
        return ranked[0][0]
    except Exception:
        return None


def normalize_orientation_bytes(data, expected_aspect_range=None, portrait_expected=False):
    """Orientation normalization for UPLOADED document images
    (owner's order 2026-10-26, after his own upload proved the gap):
    a slip photographed sideways — portrait photo, landscape document
    — must read exactly as well as one photographed straight. "It can
    be portrait, it can be landscape, no matter how."

    Tries the image at 0/90/180/270 degrees and keeps the rotation
    whose read is decisively best: OCR score (mean word confidence x
    text length on a downscaled pass), with a bonus when framing
    finds the document quad at an aspect inside the type's expected
    range. A rotation is applied ONLY when it beats the as-is read by
    >= 1.5x — an upright image is never gratuitously rotated. When
    the text deciders (OSD, then this score) cannot decide and the
    document type carries a printed portrait, the portrait itself
    decides (_portrait_orientation): a face is only detectable
    upright, which no amount of text auto-rotation can fake. Returns
    (bytes, info); on any doubt the original bytes come back with
    applied=False. The stored artifact IS the corrected image, so
    every downstream read (framing, OCR, zones, classification,
    portrait) consumes the document upright."""
    info = {"applied": False, "angle": 0, "scores": {}}
    if Image is None or not data:
        return data, info
    exe = shutil.which("tesseract")
    if not exe:
        return data, info
    try:
        im0 = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return data, info
    from . import framing as FRAMING
    best = None  # (score, angle, image)
    for angle in (0, 90, 180, 270):
        im = im0 if angle == 0 else im0.rotate(-angle, expand=True)  # PIL rotate is CCW; angle means CW here
        try:
            small = im.copy()
            small.thumbnail((1000, 1000))
            fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
            small.save(tmp, format="PNG")
            try:
                text, conf = _tesseract_tsv(exe, tmp)
            finally:
                try: os.unlink(tmp)
                except Exception: pass
            score = max(0.0, conf) * len(text)
            if expected_aspect_range and cv2 is not None:
                try:
                    import numpy as _np
                    a = FRAMING.analyse_image(cv2.cvtColor(_np.array(im), cv2.COLOR_RGB2BGR),
                                              expected_aspect_range)
                    if a and a.get("quad") is not None and expected_aspect_range[0] <= (a.get("aspect") or 0) <= expected_aspect_range[1]:
                        score *= 1.25
                except Exception:
                    pass
            info["scores"][str(angle)] = round(score, 1)
            if best is None or score > best[0]:
                best = (score, angle, im)
        except Exception:
            continue
    if best is None:
        return data, info
    base = info["scores"].get("0", 0)
    # Orientation detection (tesseract OSD) decides FIRST when it is
    # confident: on clean rendered documents the plain OCR score can
    # TIE between the as-is and corrected reads (the sideways page's
    # columns harvest the same real words — measured on the synthetic
    # slip at -90 degrees, 34.7k vs 27.8k for the WRONG winner),
    # while OSD names the rotation outright (confidence ~5-7). On
    # noisy real photos OSD is blind (the owner's laminated slip:
    # confidence 0.15) — there the score competition below is the
    # decider, exactly as proven on his upload. OSD's degrees are the
    # counter-clockwise correction; this function's angle is CW.
    chosen = None
    try:
        small0 = im0.copy(); small0.thumbnail((1000, 1000))
        fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
        small0.save(tmp, format="PNG")
        try:
            out_osd = subprocess.run([exe, tmp, "stdout", "--psm", "0"],
                                     capture_output=True, text=True, timeout=60)
            fields = {}
            for line in (out_osd.stdout or "").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1); fields[k.strip()] = v.strip()
            osd_deg = float(fields.get("Orientation in degrees", "0"))
            osd_conf = float(fields.get("Orientation confidence", "0"))
            if osd_conf >= 2.5 and osd_deg % 360 != 0:
                angle_cw = int((360 - osd_deg) % 360)
                if info["scores"].get(str(angle_cw), 0) >= 0.5 * max(base, 1.0):
                    chosen = angle_cw
                    info["via"] = "osd"
        finally:
            try: os.unlink(tmp)
            except Exception: pass
    except Exception:
        chosen = None
    if chosen is None:
        score, angle, _im = best
        if not (angle == 0 or score < 1.5 * max(base, 1.0) or score < 200):
            chosen = angle
            info["via"] = "score"
    if chosen is None and portrait_expected:
        face_angle = _portrait_orientation(im0, expected_aspect_range)
        if face_angle:
            chosen = face_angle
            info["via"] = "portrait"
    if chosen is None:
        return data, info
    im = im0 if chosen == 0 else im0.rotate(-chosen, expand=True)
    out = io.BytesIO()
    # PNG, lossless: the source has usually already survived one
    # lossy encode on its way in (the client's tunnel-cap downscale);
    # the stored artifact must not bleed a second generation of
    # detail — at the margin, those pixels are the difference
    # between a digit that reads and one that does not.
    im.save(out, format="PNG")
    info.update({"applied": True, "angle": chosen})
    return out.getvalue(), info


def _reading_path(path):
    """The image OCR should READ: the perspective-warped rendition
    when framing finds a document quad in the capture, else the
    original. Returns (effective_path, warp_findings_or_None)."""
    try:
        from . import framing as FRAMING
        analysis = FRAMING.analyse_path(path)
        if analysis and analysis.get("quad") is not None:
            warped = FRAMING.warped_rendition(path)
            if warped:
                return warped, {"applied": True, "method": analysis.get("method"),
                                "aspect": analysis.get("aspect"),
                                "area_ratio": analysis.get("area_ratio")}
    except Exception:
        pass
    return path, {"applied": False}

def read_document_text(path, expect_mrz=True):
    """Multi-pass OCR. Returns {"status", "findings", "reason_codes",
    "text", "pass_texts"} with the same contract as the old
    single-pass check_ocr; "text" is the winning pass, "pass_texts"
    carries every pass's text for union consumers (field extraction).
    `expect_mrz=False` (card-type documents, per the registry) skips
    the dedicated MRZ-band pass entirely — up to three tesseract runs
    that cannot find an MRZ the document type does not carry. When the
    capture contains a detectable document quad, the passes read the
    perspective-warped rendition (findings["warp"] records it)."""
    exe = shutil.which("tesseract")
    if not exe:
        return {"status": "error", "findings": {"error": "tesseract_not_installed"}, "reason_codes": ["ocr_unavailable"], "text": ""}
    path, warp_info = _reading_path(path)
    variants = _prep_variants(path)
    if not variants:
        variants = [("raw", path)]
    passes = []
    try:
        for name, vpath in variants:
            try:
                text, conf = _tesseract_tsv(exe, vpath)
            except Exception:
                # Fall back to the plain-text run for this pass.
                out = subprocess.run([exe, vpath, "stdout", "--psm", "3"],
                                     capture_output=True, text=True, timeout=60)
                text, conf = (out.stdout or "").strip(), -1.0
            parsed = C.parse_mrz(text)
            passes.append({"name": name, "text": text, "confidence": round(conf, 1),
                           "chars": len(text), "mrz_valid": bool(parsed and parsed.get("valid"))})
            # Early exit (2026-10-26 perf fix): a check-digit-VALID MRZ
            # with substantial text is mathematically verified — later
            # passes cannot improve on it, and on noisy photos each
            # extra tesseract run costs seconds. Non-MRZ documents are
            # unaffected: all passes still run for field extraction.
            if parsed and parsed.get("valid") and len(text) >= 40:
                break
    finally:
        for name, vpath in variants:
            if vpath != path:
                try: os.unlink(vpath)
                except Exception: pass
    if not passes:
        return {"status": "error", "findings": {"error": "ocr_passes_failed"}, "reason_codes": ["ocr_error"], "text": "", "pass_texts": []}
    valids = [p for p in passes if p["mrz_valid"]]
    if len(valids) == 1:
        winner, why = valids[0], "only pass with a check-digit-valid MRZ"
    elif valids:
        winner, why = max(valids, key=lambda p: p["confidence"]), "valid MRZ, highest confidence"
    else:
        winner, why = max(passes, key=lambda p: (p["confidence"], p["chars"])), "highest word confidence"
    text = winner["text"]
    # MRZ band merge: if the full-page winner carries no MRZ but the
    # dedicated band pass found MRZ lines, append those lines (only
    # them) so the MRZ check downstream can judge them — pass OR fail;
    # a corrupted MRZ must stay visible, never silently dropped.
    band_text = _mrz_band_text(path, exe) if expect_mrz else ""
    band_l1, band_l2 = C.find_mrz_lines(band_text) if band_text else (None, None)
    merged_band = False
    if band_l2 and not C.parse_mrz(text):
        lines = [l for l in (band_l1, band_l2) if l]
        text = text + "\n" + "\n".join(lines)
        merged_band = True
    band_parsed = C.parse_mrz(band_text) if band_text else None
    findings = {"chars": len(text), "engine": "vision-multipass", "warp": warp_info,
                "passes": [{"name": p["name"], "confidence": p["confidence"], "chars": p["chars"], "mrz_valid": p["mrz_valid"]} for p in passes]
                          + [{"name": "mrz_band", "confidence": None, "chars": len(band_text),
                              "mrz_valid": bool(band_parsed and band_parsed.get("valid"))}],
                "chosen": winner["name"], "choice_reason": why, "mrz_band_merged": merged_band}
    # pass_texts: EVERY pass's text, not only the winner's. Field
    # extraction searches their union (the winning pass is chosen for
    # MRZ/confidence, and is not necessarily the pass that read each
    # printed field). Kept out of `findings` — the texts are bulky and
    # the findings record is stored per check.
    pass_texts = [p["text"] for p in passes]
    if len(text) >= 10:
        return {"status": "pass", "findings": findings, "reason_codes": [], "text": text,
                "pass_texts": pass_texts}
    return {"status": "unclear", "findings": findings, "reason_codes": ["ocr_low_text"], "text": text,
            "pass_texts": pass_texts}

# ---------------- OCR word boxes (for classification) ----------------

def ocr_words(path):
    """Tesseract TSV on the plain pass, as word boxes in NORMALISED
    image coordinates: [{"text", "conf", "box": (x0, y0, x1, y1)}].
    Used by document classification to map where text actually sits.
    Coordinates are in the READING image's space — the warped
    rendition when framing found a quad (see read_document_text) —
    so template zones, which are document-relative, compare against
    document-relative boxes."""
    exe = shutil.which("tesseract")
    if not exe or Image is None:
        return []
    path, _warp = _reading_path(path)
    variants = _prep_variants(path)
    if not variants:
        return []
    name, vpath = variants[0]
    try:
        with Image.open(vpath) as vim:
            vw, vh = vim.size
        out = subprocess.run([exe, vpath, "stdout", "--psm", "3", "tsv"],
                             capture_output=True, text=True, timeout=60)
        words = []
        for row in (out.stdout or "").splitlines()[1:]:
            parts = row.split("\t")
            if len(parts) != 12 or parts[0] != "5" or not parts[11].strip():
                continue
            try:
                left, top, width, height = (float(parts[6]), float(parts[7]), float(parts[8]), float(parts[9]))
                conf = float(parts[10])
            except Exception:
                continue
            words.append({"text": parts[11], "conf": conf,
                          "box": (left / vw, top / vh, (left + width) / vw, (top + height) / vh)})
        if len(words) < 60:
            # Tiled fallback (owner's low-resolution upload,
            # 2026-10-26): at low source resolution the full-page
            # pass goes nearly blind — 47 words on his real slip,
            # with neither the field labels nor the values found —
            # while the SAME image read in overlapping quadrant
            # tiles yields the labels and values at high confidence
            # ('NIN:' 96, 'AYANSIPE' 91, 'ZENAS' 78 measured). Small
            # print needs the pixels per word that tiling gives it.
            # Tiles are cut from this same 2x prep image, so tile
            # boxes map back into reading-image fractions directly;
            # duplicates in the overlaps are dropped by centre.
            try:
                import cv2 as _cv2
                timg = _cv2.imread(vpath)
                if timg is not None:
                    th, tw = timg.shape[:2]
                    # Dedupe by BOX OVERLAP, not centre+text: the
                    # full-page pass and a tile often read the same
                    # printed word twice with slightly different
                    # boxes AND different text (a degraded token and
                    # its clean twin — 'AXANSIPE' beside 'AYANSIPE');
                    # keeping both makes downstream harvests join
                    # them into one Frankenstein value. When boxes
                    # overlap substantially, the higher-confidence
                    # read wins.
                    def _iou(a, b):
                        # Overlap coefficient (inter / smaller area),
                        # not Jaccard: a tight tile box sits INSIDE
                        # the full-page pass's loose box for the same
                        # word — Jaccard scores that ~0.3 and misses
                        # the duplicate; containment scores it 1.0.
                        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                        inter = ix * iy
                        if inter <= 0:
                            return 0.0
                        smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                        return inter / smaller if smaller > 0 else 0.0
                    seen = [w for w in words]
                    for qy in (0.0, 0.44):
                        for qx in (0.0, 0.44):
                            tx0, ty0 = int(qx * tw), int(qy * th)
                            tile = timg[ty0:int((qy + 0.56) * th), tx0:int((qx + 0.56) * tw)]
                            fd, ttmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
                            try:
                                _cv2.imwrite(ttmp, tile)
                                tout = subprocess.run([exe, ttmp, "stdout", "--psm", "3", "tsv"],
                                                      capture_output=True, text=True, timeout=60)
                            finally:
                                try: os.unlink(ttmp)
                                except Exception: pass
                            tth, ttw = tile.shape[:2]
                            for row in (tout.stdout or "").splitlines()[1:]:
                                parts = row.split("\t")
                                if len(parts) != 12 or parts[0] != "5" or not parts[11].strip():
                                    continue
                                try:
                                    left, top, width, height = (float(parts[6]), float(parts[7]), float(parts[8]), float(parts[9]))
                                    conf = float(parts[10])
                                except Exception:
                                    continue
                                gx = (tx0 + left) / tw; gy = (ty0 + top) / th
                                gx1 = (tx0 + left + width) / tw; gy1 = (ty0 + top + height) / th
                                nbox = (gx, gy, gx1, gy1)
                                clash = None
                                for s in seen:
                                    if _iou(nbox, s["box"]) > 0.6:
                                        clash = s
                                        break
                                if clash is not None:
                                    if conf > clash["conf"]:
                                        clash["text"] = parts[11]
                                        clash["conf"] = conf
                                        clash["box"] = nbox
                                    continue
                                nw = {"text": parts[11], "conf": conf, "box": nbox}
                                seen.append(nw)
                                words.append(nw)
            except Exception:
                pass
        return words
    except Exception:
        return []
    finally:
        if vpath != path:
            try: os.unlink(vpath)
            except Exception: pass

# ---------------- 2. MRZ <-> VIZ cross-validation ----------------

_DOB_LABEL = re.compile(r"\b(DOB|BIRTH|BORN)\b")
_EXP_LABEL = re.compile(r"\b(EXPIRY|EXPIRES|EXP|VALID)\b")

def _labelled_date(lines, label_re):
    for line in lines:
        m = label_re.search(line.upper())
        if m:
            # The date that belongs to THIS label is the first date at
            # or after the label on the line (a line can carry both a
            # DOB and an expiry label — taking the line's first date
            # misattributes it, found by the matrix tests 2026-10-26).
            dates = C.find_dates_in_text(line[m.start():]) or C.find_dates_in_text(line)
            if dates:
                return dates[0]
    return None

def cross_check_mrz_viz(ocr_text, parsed):
    """Compare a valid parsed MRZ against the visual zone. Material
    disagreement -> fail / mrz_viz_mismatch. Nothing comparable ->
    unclear (recorded, never a fake pass)."""
    l1, l2 = C.find_mrz_lines(ocr_text or "")
    mrz_lines = {C.clean_mrz_line(l1 or ""), C.clean_mrz_line(l2 or "")}
    viz_lines = [l for l in (ocr_text or "").splitlines() if C.clean_mrz_line(l) not in mrz_lines and l.strip()]
    viz_text = "\n".join(viz_lines)
    fields = {}
    compared = 0
    mismatches = []
    mrz_dob = C.yymmdd_to_date(parsed["dob_yymmdd"], is_dob=True)
    mrz_exp = C.yymmdd_to_date(parsed["expiry_yymmdd"])
    viz_dob = _labelled_date(viz_lines, _DOB_LABEL)
    viz_exp = _labelled_date(viz_lines, _EXP_LABEL)
    if viz_dob is not None:
        compared += 1
        fields["dob"] = {"mrz": mrz_dob.isoformat() if mrz_dob else None, "viz": viz_dob.isoformat(), "agree": viz_dob == mrz_dob}
        if viz_dob != mrz_dob:
            mismatches.append("dob")
    if viz_exp is not None:
        compared += 1
        fields["expiry"] = {"mrz": mrz_exp.isoformat() if mrz_exp else None, "viz": viz_exp.isoformat(), "agree": viz_exp == mrz_exp}
        if viz_exp != mrz_exp:
            mismatches.append("expiry")
    names = parsed.get("names") or {}
    surname = (names.get("surname") or "").strip()
    if surname:
        present = surname.split()[0] in C._tokens(viz_text)
        fields["surname"] = {"mrz": surname, "in_viz": present}
        # Surname presence is recorded but does NOT count as a compared
        # field: it is weak evidence (OCR drops words; absence is not
        # material). Only labelled-date fields make the zones comparable
        # — with none of them, the honest result is unclear, not pass.
    docnum = (parsed.get("document_number") or "").strip()
    if docnum:
        fields["document_number"] = {"mrz": docnum,
                                     "in_viz": docnum in re.sub(r"[^A-Z0-9]", "", viz_text.upper())}
    findings = {"fields": fields, "compared": compared, "mismatches": mismatches}
    if mismatches:
        return {"status": "fail", "findings": findings, "reason_codes": ["mrz_viz_mismatch"]}
    if compared:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    return {"status": "unclear", "findings": findings, "reason_codes": ["mrz_viz_insufficient_data"]}

# ---------------- 2b. data-consistency matrix (Addition 10A) ----------------

def _name_agree(a, b):
    ta, tb = C._tokens(a), C._tokens(b)
    if not ta or not tb:
        return None
    return ta == tb or ta.issubset(tb) or tb.issubset(ta)

def _date_agree(a, b):
    if not a or not b:
        return None
    return a == b

def _number_agree(a, b):
    na, nb = _alnum(a or ""), _alnum(b or "")
    if not na or not nb:
        return None
    return na == nb

_FIELD_COMPARE = {"name": _name_agree, "dob": _date_agree, "expiry": _date_agree, "number": _number_agree}

def build_data_consistency(doc_fields=None, applicant=None, mrz_parsed=None, ocr_text="", aamva=None, extracted=None):
    """Pairwise agreement record across every data source present:
    printed (document fields), ocr (extracted from the image text),
    mrz, barcode (decoded AAMVA payload), applicant (profile) — over
    name / dob / document number / expiry. Each pair verdict is
    agree | disagree | not_available. ANY disagree fails the check
    with named findings (e.g. mrz_vs_barcode_number_disagree) plus the
    generic data_inconsistency reason: for auto-approval, no disagree
    may exist among available pairs.

    `extracted` (identity-from-document build): the template field
    extraction findings["fields"] dict, added as an "extraction"
    source. The caller passes it ONLY when nothing was declared (the
    document path): there the matrix compares the document's own
    reads — extraction vs the labelled-date printed source, vs the
    MRZ, vs a decoded payload — and the applicant source is empty, so
    no applicant pair can ever disagree. On the declared path the
    argument is omitted and behaviour is exactly as before."""
    doc_fields = doc_fields or {}
    applicant = applicant or {}
    sources = {}
    if extracted:
        def _ev(name):
            return (extracted.get(name) or {}).get("value") or None
        ex_name = f"{_ev('given_names') or ''} {_ev('surname') or ''}".strip()
        sources["extraction"] = {"name": ex_name or None, "dob": _ev("dob"),
                                  "number": _ev("number"), "expiry": _ev("expiry")}
    # "printed" = the fields as EXTRACTED from the document image
    # (Addition 10A's "printed OCR fields") — built below from the OCR
    # text; the submitted doc_fields serve only as read candidates.
    # The applicant's typed claim is validated separately by the
    # consistency check; the matrix compares independent sources.
    sources["applicant"] = {
        "name": f"{applicant.get('first_name') or ''} {applicant.get('last_name') or ''}".strip() or None,
        "dob": applicant.get("dob"), "number": None, "expiry": None}
    if mrz_parsed and mrz_parsed.get("valid"):
        names = mrz_parsed.get("names") or {}
        mdob = C.yymmdd_to_date(mrz_parsed["dob_yymmdd"], is_dob=True)
        mexp = C.yymmdd_to_date(mrz_parsed["expiry_yymmdd"])
        sources["mrz"] = {
            "name": f"{names.get('given_names', '')} {names.get('surname', '')}".strip() or None,
            "dob": mdob.isoformat() if mdob else None,
            "number": mrz_parsed.get("document_number"),
            "expiry": mexp.isoformat() if mexp else None}
    if aamva:
        sources["barcode"] = {
            "name": f"{aamva.get('first_name', '')} {aamva.get('surname', '')}".strip() or None,
            "dob": (_aamva_date(aamva["dob"]).isoformat() if aamva.get("dob") and _aamva_date(aamva["dob"]) else None),
            "number": aamva.get("number"),
            "expiry": (_aamva_date(aamva["expiry"]).isoformat() if aamva.get("expiry") and _aamva_date(aamva["expiry"]) else None)}
    # Printed source, extracted from the image text: labelled VIZ
    # dates, the document number as actually read in the text, and
    # the printed name when its tokens appear in the read.
    l1, l2 = C.find_mrz_lines(ocr_text or "")
    mrz_lines = {C.clean_mrz_line(l1 or ""), C.clean_mrz_line(l2 or "")}
    viz_lines = [l for l in (ocr_text or "").splitlines() if C.clean_mrz_line(l) not in mrz_lines and l.strip()]
    printed = {"name": None, "dob": None, "number": None, "expiry": None}
    viz_dob = _labelled_date(viz_lines, _DOB_LABEL)
    viz_exp = _labelled_date(viz_lines, _EXP_LABEL)
    if viz_dob: printed["dob"] = viz_dob.isoformat()
    if viz_exp: printed["expiry"] = viz_exp.isoformat()
    pnum = doc_fields.get("doc_number")
    if pnum and _alnum(pnum) in re.sub(r"[^A-Z0-9]", "", (ocr_text or "").upper()):
        printed["number"] = pnum
    pname = f"{doc_fields.get('doc_first_name') or ''} {doc_fields.get('doc_last_name') or ''}".strip()
    if pname and C._tokens(pname) and C._tokens(pname).issubset(C._tokens(ocr_text)):
        printed["name"] = pname
    if any(printed.values()):
        sources["printed"] = printed
    sources = {k: sources[k] for k in ("printed", "extraction", "applicant", "mrz", "barcode") if k in sources}
    names = list(sources.keys())
    matrix = {}
    disagreements = []
    compared = 0
    for field, cmp_fn in _FIELD_COMPARE.items():
        matrix[field] = {}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                va, vb = sources[a].get(field), sources[b].get(field)
                verdict = cmp_fn(va, vb)
                key = f"{a}_vs_{b}"
                if verdict is None:
                    matrix[field][key] = "not_available"
                elif verdict:
                    matrix[field][key] = "agree"
                    compared += 1
                else:
                    matrix[field][key] = "disagree"
                    compared += 1
                    disagreements.append(f"{a}_vs_{b}_{field}_disagree")
    findings = {"matrix": matrix, "disagreements": disagreements,
                "sources_present": names, "pairs_compared": compared}
    if disagreements:
        return {"status": "fail", "findings": findings,
                "reason_codes": disagreements + ["data_inconsistency"]}
    if compared:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    return {"status": "unclear", "findings": findings, "reason_codes": ["data_consistency_not_available"]}

# ---------------- 3. machine-readable code decoding ----------------

def _decode_qr(path):
    if cv2 is None or not path:
        return None
    try:
        img = cv2.imread(path)
        if img is None:
            return None
        det = cv2.QRCodeDetector()
        data, _pts, _ = det.detectAndDecode(img)
        if data:
            return data
        big = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        data, _pts, _ = det.detectAndDecode(big)
        return data or None
    except Exception:
        return None

def _aamva_date(mmddyyyy):
    try:
        return date(int(mmddyyyy[4:8]), int(mmddyyyy[0:2]), int(mmddyyyy[2:4]))
    except Exception:
        return None

def _decode_barcodes(path):
    """zxing-cpp (optional): all barcodes on one image."""
    if zxingcpp is None or not path or Image is None:
        return []
    try:
        out = []
        for r in zxingcpp.read_barcodes(Image.open(path)):
            out.append({"format": str(r.format), "text": (r.text or "")[:2000]})
        return out
    except Exception:
        return []

def _alnum(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

def decode_codes(front_path=None, back_path=None, doc_fields=None, country=None, kind=None):
    """Decode QR (OpenCV) + barcodes (zxing, if installed) on the
    document images and validate the payloads SEMANTICS via
    server/payloads.py: AAMVA element parsing + format validation,
    NG NIN-slip QR structure, Aadhaar secure-QR decompression, PhilID
    QR structure — each cross-checked against the printed document
    fields. Decoded content is evidence, never truth: disagreement
    fails with code_decode_mismatch. Absence of any code is 'unclear',
    honestly (most documents carry no decodable code in reach)."""
    from . import payloads as PAYLOADS
    doc_fields = doc_fields or {}
    findings = {"qr": None, "barcodes": [], "aamva": None, "payloads": [],
                "zxing": "available" if zxingcpp is not None else "unavailable",
                "opencv": "available" if cv2 is not None else "unavailable"}
    mismatches = []
    found_any = False

    def _absorb(parsed, side):
        """Record a parsed payload + cross-check it; extend mismatches."""
        if not parsed:
            return
        entry = {"standard": parsed["standard"], "side": side,
                 "validation_depth": parsed.get("validation_depth"),
                 "fields": parsed.get("fields")}
        if parsed.get("depth_note"):
            entry["depth_note"] = parsed["depth_note"]
        if parsed["standard"] == "AAMVA":
            entry["elements_present"] = sorted((parsed.get("elements") or {}).keys())
            entry["format"] = parsed.get("format")
            f = parsed["fields"]
            # Backwards-compatible summary shape (build_data_consistency
            # and the console read this): dates stay MMDDYYYY here.
            findings["aamva"] = {"number": f.get("number"), "surname": f.get("surname"),
                                 "first_name": f.get("first_name"),
                                 "dob": f.get("dob_raw"), "expiry": f.get("expiry_raw")}
            findings["aamva_format"] = parsed.get("format")
            findings["aamva_format_valid"] = parsed.get("format_valid")
        mm, compared = PAYLOADS.cross_check_payload(parsed, doc_fields, country=country, kind=kind)
        entry["cross_checked_fields"] = compared
        findings["payloads"].append(entry)
        mismatches.extend(mm)

    for side, p in (("front", front_path), ("back", back_path)):
        if not p:
            continue
        qr = _decode_qr(p)
        if qr:
            found_any = True
            findings["qr"] = {"side": side, "data": qr[:600]}
            parsed = None
            if country == "IN" or (qr.strip().isdigit() and len(qr.strip()) >= 100):
                parsed = PAYLOADS.parse_aadhaar_qr(qr)
            if parsed is None and (country == "NG" or "NIN" in qr.upper()):
                parsed = PAYLOADS.parse_nin_qr(qr)
            if parsed is None and country == "PH":
                parsed = PAYLOADS.parse_philid_qr(qr)
            if parsed is None and "DAQ" in qr.upper():
                parsed = PAYLOADS.parse_aamva(qr)
            if parsed is None:
                # Unrouted QR: try each structural parser in turn.
                parsed = (PAYLOADS.parse_aadhaar_qr(qr) or PAYLOADS.parse_nin_qr(qr)
                          or PAYLOADS.parse_philid_qr(qr))
            _absorb(parsed, side)
        for bc in _decode_barcodes(p):
            found_any = True
            entry = {"side": side, "format": bc["format"], "chars": len(bc["text"])}
            findings["barcodes"].append(entry)
            parsed = PAYLOADS.parse_aamva(bc["text"])
            if parsed is None and "PDF417" not in bc["format"]:
                parsed = (PAYLOADS.parse_nin_qr(bc["text"]) or PAYLOADS.parse_philid_qr(bc["text"]))
            _absorb(parsed, side)
    findings["mismatches"] = mismatches
    findings["found_any"] = found_any
    if mismatches:
        return {"status": "fail", "findings": findings, "reason_codes": ["code_decode_mismatch"]}
    if found_any:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    return {"status": "unclear", "findings": findings, "reason_codes": ["no_machine_code_found"]}
