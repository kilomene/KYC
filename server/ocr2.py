"""Second OCR engine — PaddleOCR (PP-OCRv5 mobile, CPU), unified with
the Tesseract reader into ONE reading family (owner's order,
2026-10-28: "build the extraction brain around both engines... they
now become one... a very strong family").

Design contract:
  * SAME word-stream schema as vision.ocr_words — items of
    {text, conf (0..100), box (x0, y0, x1, y1) as NORMALISED
    fractions of the reading image} (we predict on
    vision._reading_path, the exact image the Tesseract machinery
    reads), plus "src": "paddle".
  * Lazy singleton: the models (~21 MB, PP-OCRv5 mobile det+rec) load
    once per process on first use, behind a lock; construction takes
    ~10s and must never sit on a request path more than once.
  * TOTAL failure isolation: any problem — package missing, models
    missing, inference error, kill-switch — returns None and the
    platform behaves exactly as the single-engine build did. This
    engine can only ADD evidence; it can never become a dependency.
  * FAIL-CLOSED GATE: the engine runs only where explicitly
    enabled — env KYC_OCR2=on (set by the production and staging
    systemd units). Every other context (the test suite, offline
    scripts) stays deterministic single-engine unless it opts in.
    Models are read from the local
    PaddleX cache (~/.paddlex/official_models) — pre-fetched with
    curl at install/recovery time because the managed downloader's
    HTTP client cannot parse this host's egress-proxy URL.
  * oneDNN is disabled (enable_mkldnn=False): paddlepaddle 3.3.1's
    oneDNN executor raises NotImplementedError on these models
    (ConvertPirAttribute2RuntimeAttribute, measured 2026-10-28).
"""
import os
import re
import threading

_OCR = None
_LOCK = threading.Lock()
_FAILED = False

_MODEL_DIR = os.path.expanduser("~/.paddlex/official_models")
_DET = "PP-OCRv5_mobile_det"
_REC = "PP-OCRv5_mobile_rec"


def enabled():
    return os.environ.get("KYC_OCR2", "").strip().lower() in ("on", "1", "true")


def available():
    """Cheap availability probe (no model load): package importable
    and both model dirs present."""
    if not enabled() or _FAILED:
        return False
    try:
        import paddleocr  # noqa: F401
    except Exception:
        return False
    return all(os.path.isdir(os.path.join(_MODEL_DIR, m)) for m in (_DET, _REC))


def _get_ocr():
    global _OCR, _FAILED
    if _OCR is not None or _FAILED:
        return _OCR
    with _LOCK:
        if _OCR is not None or _FAILED:
            return _OCR
        try:
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            _OCR = PaddleOCR(
                text_detection_model_name=_DET,
                text_detection_model_dir=os.path.join(_MODEL_DIR, _DET),
                text_recognition_model_name=_REC,
                text_recognition_model_dir=os.path.join(_MODEL_DIR, _REC),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False)
        except Exception:
            _FAILED = True
            _OCR = None
    return _OCR


def read_words(image_path):
    """Read one image with PaddleOCR. Returns (words, text) in the
    shared contract, or None when the engine is unavailable or the
    read fails. `image_path` may be the stored document path — the
    reading rendition is resolved exactly as the Tesseract side
    resolves it, so both engines' boxes live in the same space."""
    if not enabled():
        return None
    ocr = _get_ocr()
    if ocr is None:
        return None
    try:
        from . import vision as VISION
        rend = VISION._reading_path(image_path)[0]
        res = ocr.predict(rend)
        if not res:
            return None
        r0 = res[0]
        # vision.ocr_words reports boxes as NORMALISED fractions
        # (x0, y0, x1, y1) of the reading image — match that contract
        # exactly so both engines' streams are interchangeable.
        import cv2
        img = cv2.imread(rend)
        if img is None:
            return None
        H, W = img.shape[:2]
        words = []
        for text, score, poly in zip(r0["rec_texts"], r0["rec_scores"],
                                     r0["rec_polys"]):
            toks = (text or "").split()
            if not toks:
                continue
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            # Paddle detects LINES; the extraction brain consumes
            # WORDS. Split the line box across its word tokens by
            # character share (spaces counted) — the same bridge the
            # 2026-10-28 benchmark validated.
            total = sum(len(t) for t in toks) + (len(toks) - 1)
            cx = x0
            for t in toks:
                w = (x1 - x0) * (len(t) / total)
                words.append({"text": t, "conf": float(score) * 100.0,
                              "box": (cx / W, y0 / H, (cx + w) / W, y1 / H),
                              "src": "paddle"})
                cx += (x1 - x0) * ((len(t) + 1) / total)
        text = "\n".join(r0["rec_texts"])
        return words, text
    except Exception:
        return None


_TRIAD = ("surname", "given_names", "number")


def extraction_fields(extraction):
    """Pull the {field: value} map out of an extract_fields result
    (fields live under findings.fields, each {value, source})."""
    out = {}
    if not isinstance(extraction, dict):
        return out
    fields = (extraction.get("findings", {}) or {}).get("fields", {}) or {}
    for name, entry in fields.items():
        v = entry.get("value") if isinstance(entry, dict) else entry
        if v:
            out[name] = v
    return out


def triad_complete(fields):
    return all(fields.get(f) for f in _TRIAD)


def _values_agree(field, a, b):
    if a is None or b is None:
        return False
    if field == "number":
        na = "".join(c for c in str(a).upper() if c.isalnum())
        nb = "".join(c for c in str(b).upper() if c.isalnum())
        return bool(na) and na == nb
    if field in ("dob", "expiry"):
        return str(a).strip() == str(b).strip()
    na = " ".join(str(a).upper().split())
    nb = " ".join(str(b).upper().split())
    return na == nb


def arbitrate(merged_fields, tess_fields, paddle_fields):
    """Cross-engine arbitration over the identity fields.

    Inputs are {field: value} maps from up to three extraction runs
    (unified merged-stream, Tesseract-only, Paddle-only; the latter
    two may be empty dicts when the lazy path did not need them).
    Returns (adopted, disagreements):
      adopted: {field: (value, provenance)} for fields the unified
        run missed but exactly one engine found (union completeness
        — the family keeps what any member proved), or where both
        single-engine runs agree against the merged run's silence.
      disagreements: [{field, merged, tesseract, paddle}] for every
        field where the engines' values conflict — surfaced in the
        read payload, never silently resolved. A conflict the merged
        run already settled keeps the merged value (the brain judged
        the combined evidence); a conflict with NO merged value is
        adopted from NEITHER engine for `number` (downstream
        arbiters — typed claim, MRZ, barcode payload — decide), and
        for names adopts the Tesseract value only when the Paddle
        value fails the plausibility screen while Tesseract's
        passes (the poisoned-record lesson: a wrong name adopted is
        worse than no name)."""
    adopted = {}
    disagreements = []
    fields = set(merged_fields) | set(tess_fields) | set(paddle_fields)
    for f in sorted(fields):
        mv = merged_fields.get(f)
        tv = tess_fields.get(f)
        pv = paddle_fields.get(f)
        # conflict between the two single-engine witnesses?
        if tv and pv and not _values_agree(f, tv, pv):
            disagreements.append({"field": f, "merged": mv,
                                  "tesseract": tv, "paddle": pv})
            if not mv:
                if f == "number":
                    continue  # downstream arbiters decide
                # names: prefer the plausible witness, if exactly
                # one is plausible
                try:
                    from . import app as _app
                    t_ok = _app._name_plausible(tv)
                    p_ok = _app._name_plausible(pv)
                except Exception:
                    t_ok, p_ok = True, False
                if t_ok and not p_ok:
                    adopted[f] = (tv, "tesseract_arbitrated")
                elif p_ok and not t_ok:
                    adopted[f] = (pv, "paddle_arbitrated")
                continue
        if mv and f in ("surname", "given_names"):
            # Superset rescue (owner session 16, 2026-10-29): the
            # unified read can be COMPLETE but PARTIAL — it adopted
            # one cell of a two-cell name (the middle name alone,
            # source 'text') while a single-engine witness read the
            # full name from its labels. A witness whose name tokens
            # STRICTLY CONTAIN the merged value's tokens, and which
            # passes the name plausibility screen, is adopted over
            # the fragment; the tightest superset wins, Tesseract
            # breaks ties. A subset witness changes nothing (the
            # merged read may legitimately carry more than one
            # engine saw), and junk a superset carries is handled
            # downstream by witness corroboration (identity.py).
            def _toks(v):
                return set(re.findall(r"[A-ZÀ-Þ]{2,}", str(v).upper()))
            _mt = _toks(mv)
            _sup = []
            for _wv, _prov in ((tv, "tesseract_superset"), (pv, "paddle_superset")):
                if _wv:
                    _wt = _toks(_wv)
                    if _mt and _mt < _wt:
                        _sup.append((len(_wt) - len(_mt), 0 if _prov.startswith("tesseract") else 1, _wv, _prov))
            if _sup:
                _sup.sort(key=lambda c: (c[0], c[1]))
                try:
                    from . import app as _app
                    _ok = _app._name_plausible(_sup[0][2])
                except Exception:
                    _ok = False
                if _ok:
                    adopted[f] = (_sup[0][2], _sup[0][3])
                    disagreements.append({"field": f, "merged": mv,
                                          "tesseract": tv, "paddle": pv,
                                          "resolution": "superset_witness_adopted"})
                    continue
        if mv:
            continue  # the unified brain's value stands
        if tv and pv and _values_agree(f, tv, pv):
            adopted[f] = (tv, "both_engines")
        elif tv and not pv:
            adopted[f] = (tv, "tesseract")
        elif pv and not tv:
            adopted[f] = (pv, "paddle")
    return adopted, disagreements


def read_words_for_image_file(path):
    """Read a STANDALONE image file (e.g. an extraction band strip)
    with PaddleOCR — no reading-path resolution, the file IS the
    image. Returns fractional-box items in the band reader's own
    schema ({text, conf, box (x0,y0,x1,y1) as fractions, cx, cy}) or
    None. Used to make the name-band rescue dual-engine."""
    if not enabled():
        return None
    ocr = _get_ocr()
    if ocr is None:
        return None
    try:
        res = ocr.predict(path)
        if not res:
            return None
        r0 = res[0]
        import cv2
        img = cv2.imread(path)
        if img is None:
            return None
        H, W = img.shape[:2]
        items = []
        for text, score, poly in zip(r0["rec_texts"], r0["rec_scores"],
                                     r0["rec_polys"]):
            toks = (text or "").split()
            if not toks:
                continue
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            total = sum(len(t) for t in toks) + (len(toks) - 1)
            cx = x0
            for t in toks:
                w = (x1 - x0) * (len(t) / total)
                bx = (cx / W, y0 / H, (cx + w) / W, y1 / H)
                items.append({"text": t, "conf": float(score) * 100.0,
                              "box": bx, "cx": (bx[0] + bx[2]) / 2.0,
                              "cy": (bx[1] + bx[3]) / 2.0, "src": "paddle"})
                cx += (x1 - x0) * ((len(t) + 1) / total)
        return items
    except Exception:
        return None
