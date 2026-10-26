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
  format       Template/format consistency for the DECLARED document:
               document-number pattern, MRZ presence for passports, and
               OCR keywords that should appear on that document type.

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
          ("format", "moderate"): 30, ("format", "weak"): 10}

def check_authenticity(path, kind=None, country=None, doc_number=None, ocr_text="", mrz_found=False):
    signals = [ela_signal(path), metadata_signal(path), moire_signal(path),
               format_signal(kind or "", country or "", doc_number, ocr_text, mrz_found)]
    total = sum(POINTS.get((s["name"], s["strength"]), 0) for s in signals)
    findings = {"signals": signals, "signal_points": total,
                "note": "combined evidence decides; one weak signal alone never fails a document"}
    if total >= 60:
        strong_names = [s["name"] for s in signals if POINTS.get((s["name"], s["strength"]), 0) >= 20]
        return {"status": "fail", "findings": findings,
                "reason_codes": ["suspected_tamper" if "ela" in strong_names else "suspected_recapture_or_edit"]}
    if total >= 25:
        return {"status": "unclear", "findings": findings, "reason_codes": ["authenticity_signals_present"]}
    return {"status": "pass", "findings": findings, "reason_codes": []}
