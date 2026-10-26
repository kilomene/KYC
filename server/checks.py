"""Verification checks. Every check here actually runs code.

Statuses: pass | fail | unclear | not_run | error
Findings are structured dicts; reason_codes are machine-actionable strings.

Thresholds (capture_quality) — documented, deliberately simple for Phase 1:
  * image must open with Pillow and be a real image format
  * minimum size: width >= 640 and height >= 400 (a legible ID photo)
      below that -> fail (too_small)
  * sharpness: high-frequency energy, measured as the stddev of the
    difference between the greyscale image and a Gaussian-blurred
    (radius 2) copy of itself. Blurring an already-blurry image changes
    it very little, so this separates sharp from blurred reliably where
    a raw edge-map stddev did not (measured during the build).
      >= 5.0 -> sharp enough (pass)
      2.0 .. 5.0 -> unclear (borderline blur)
      < 2.0 -> fail (blurred)
Measured on the synthetic test images: sharp ID image scores ~26,
the same image Gaussian-blurred scores < 2, a flat image scores 0.
"""
import io, math, re, shutil, subprocess
from datetime import date

try:
    from PIL import Image, ImageChops, ImageFilter, ImageStat
except Exception:  # Pillow missing -> quality check must error, never pass
    Image = None

# ---------- capture quality ----------
def check_capture_quality(path=None, data=None):
    if Image is None:
        return {"status": "error", "findings": {"error": "pillow_unavailable"}, "reason_codes": ["capture_quality_error"]}
    try:
        im = Image.open(io.BytesIO(data) if data is not None else path)
        im.verify()
        im = Image.open(io.BytesIO(data) if data is not None else path)
    except Exception as e:
        return {"status": "fail", "findings": {"error": f"not_a_valid_image: {e}"}, "reason_codes": ["invalid_image"]}
    w, h = im.size
    findings = {"width": w, "height": h, "format": im.format}
    if w < 640 or h < 400:
        findings["sharpness"] = None
        return {"status": "fail", "findings": findings, "reason_codes": ["image_too_small"]}
    grey = im.convert("L")
    # Downscale very large images for a stable, fast score.
    grey.thumbnail((1200, 1200))
    diff = ImageChops.difference(grey, grey.filter(ImageFilter.GaussianBlur(radius=2)))
    sharp = ImageStat.Stat(diff).stddev[0]
    findings["sharpness"] = round(sharp, 2)
    if sharp >= 5.0:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if sharp >= 2.0:
        return {"status": "unclear", "findings": findings, "reason_codes": ["image_borderline_blur"]}
    return {"status": "fail", "findings": findings, "reason_codes": ["image_blurred"]}

# ---------- OCR ----------
def check_ocr(path, expect_mrz=True):
    """OCR via the vision layer (server/vision.py): MULTI-PASS reading —
    the known-good plain pass (greyscale + 2x upscale, --psm 3; NOT 6:
    measured 2026-10-26, psm 6 mis-segments bordered ID-like documents)
    plus an adaptive-threshold pass, best read wins (a check-digit-valid
    MRZ outranks raw confidence). Same contract as the old single pass:
    tesseract missing -> 'error', NEVER a pass. `expect_mrz` comes from
    the document registry: card types carry no MRZ, so the band pass
    is skipped for them (pure speed, no evidence lost)."""
    from . import vision
    return vision.read_document_text(path, expect_mrz=expect_mrz)

# ---------- MRZ (TD3 / passport) ----------
_CHARVAL = {c: i for i, c in enumerate("0123456789")}
_CHARVAL.update({chr(ord('A') + i): 10 + i for i in range(26)})
_CHARVAL['<'] = 0

def mrz_check_digit(s):
    weights = (7, 3, 1)
    total = sum(_CHARVAL.get(ch, 0) * weights[i % 3] for i, ch in enumerate(s))
    return str(total % 10)

def clean_mrz_line(line):
    # OCR frequently turns '<' into '«', '(', or drops it; we only strip
    # whitespace here and uppercase — check digits will catch real damage.
    return re.sub(r"\s+", "", line.strip().upper())

def find_mrz_lines(text):
    lines = [clean_mrz_line(l) for l in (text or "").splitlines()]
    lines = [l for l in lines if len(l) >= 30]
    for i, l in enumerate(lines):
        if l.startswith("P<") and len(l) >= 40:
            if i + 1 < len(lines) and len(lines[i + 1]) >= 40:
                return l[:44].ljust(44, "<"), lines[i + 1][:44].ljust(44, "<")
            return l[:44].ljust(44, "<"), None
    # Fallback: a standalone 44-char second line (some OCR drops line 1)
    return None, None

def parse_mrz(text):
    """Parse + validate a TD3 MRZ. Returns dict or None if no MRZ found.
    Validation is mathematical (ICAO 9303 check digits)."""
    l1, l2 = find_mrz_lines(text)
    if not l2:
        return None
    try:
        doc_number = l2[0:9]; doc_cd = l2[9]
        dob = l2[13:19]; dob_cd = l2[19]
        expiry = l2[21:27]; exp_cd = l2[27]
        personal = l2[28:42]; personal_cd = l2[42]
        composite_src = l2[0:10] + l2[13:20] + l2[21:43]
        composite_cd = l2[43]
        checks = {
            "document_number": mrz_check_digit(doc_number) == doc_cd,
            "dob": mrz_check_digit(dob) == dob_cd,
            "expiry": mrz_check_digit(expiry) == exp_cd,
            "personal_number": (personal_cd == "<" and mrz_check_digit(personal) in ("0", personal_cd)) or mrz_check_digit(personal) == personal_cd,
            "composite": mrz_check_digit(composite_src) == composite_cd,
        }
        # Personal-number check digit may be '<' when unused; ICAO: if the
        # field is all fillers the check digit is '<' or 0. Treat all-filler
        # personal number as valid regardless.
        if set(personal) == {"<"}:
            checks["personal_number"] = True
        names = ""
        if l1:
            raw = l1[5:]
            parts = raw.split("<<", 1)
            surname = parts[0].replace("<", " ").strip()
            given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            names = {"surname": surname, "given_names": given}
        return {"line1": l1, "line2": l2, "document_number": doc_number.rstrip("<"),
                "dob_yymmdd": dob, "expiry_yymmdd": expiry, "checks": checks,
                "valid": all(checks.values()), "names": names}
    except Exception as e:
        return {"valid": False, "checks": {}, "error": str(e), "line1": l1, "line2": l2}

def check_mrz(ocr_text):
    parsed = parse_mrz(ocr_text)
    if parsed is None:
        return {"status": "unclear", "findings": {"mrz_found": False}, "reason_codes": ["mrz_not_found"], "parsed": None}
    if parsed.get("valid"):
        return {"status": "pass", "findings": {"mrz_found": True, "checks": parsed["checks"]}, "reason_codes": [], "parsed": parsed}
    return {"status": "fail", "findings": {"mrz_found": True, "checks": parsed.get("checks", {})}, "reason_codes": ["mrz_check_digit_failed"], "parsed": parsed}

# ---------- date helpers ----------
def yymmdd_to_date(s, is_dob=False, today=None):
    today = today or date.today()
    try:
        yy, mm, dd = int(s[0:2]), int(s[2:4]), int(s[4:6])
    except Exception:
        return None
    if is_dob:
        year = 2000 + yy
        try: d = date(year, mm, dd)
        except ValueError: return None
        if d > today:
            d = date(1900 + yy, mm, dd)
        return d
    return _safe_date(2000 + yy, mm, dd)

def _safe_date(y, m, d):
    try: return date(y, m, d)
    except ValueError: return None

def parse_iso_date(s):
    if not s: return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s.strip())
    if not m: return None
    return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

# ---------- expiry / age ----------
def check_expiry_age(mrz_parsed=None, doc_expiry=None, doc_dob=None, applicant_dob=None, today=None, has_expiry=True, validity_end=None):
    """Expiry + age. `has_expiry` comes from the document registry
    (server/docregistry.py): document types with NO expiry date (e.g.
    NG NIN slip / NIN card / voter's card) must NEVER fail or go
    unclear for a missing expiry date — there is none. For those, this
    check passes on expiry outright and only the age leg applies.

    `validity_end` (Phase 4 WS1) is a document-TYPE validity window
    from the registry, independent of any printed date: the ZA green
    ID book prints no expiry yet stops being recognised as valid ID
    after 2028-03-31. Past that date the document fails with
    document_validity_window_ended, whatever its (absent) printed
    expiry says."""
    today = today or date.today()
    vend = parse_iso_date(validity_end) if isinstance(validity_end, str) else validity_end
    if vend is not None and today > vend:
        return {"status": "fail",
                "findings": {"validity_end": vend.isoformat(), "today": today.isoformat(),
                             "detail": "document type is no longer legally valid after this date"},
                "reason_codes": ["document_validity_window_ended"]}
    expiry = dob = None; source = None
    if mrz_parsed and mrz_parsed.get("valid"):
        expiry = yymmdd_to_date(mrz_parsed["expiry_yymmdd"], today=today)
        dob = yymmdd_to_date(mrz_parsed["dob_yymmdd"], is_dob=True, today=today)
        source = "mrz"
    if expiry is None:
        expiry = parse_iso_date(doc_expiry); source = source or "document_fields"
    if dob is None:
        dob = parse_iso_date(doc_dob) or parse_iso_date(applicant_dob); source = source or "document_fields"
    findings = {"source": source, "expiry": expiry.isoformat() if expiry else None, "dob": dob.isoformat() if dob else None,
                "has_expiry": bool(has_expiry)}
    if not has_expiry:
        findings["detail"] = "document type has no expiry date"
        findings["expiry"] = None
        if dob is None:
            return {"status": "unclear", "findings": findings, "reason_codes": ["dob_missing"]}
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        findings["age"] = age
        if age < 18:
            return {"status": "fail", "findings": findings, "reason_codes": ["underage"]}
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if expiry is None or dob is None:
        return {"status": "unclear", "findings": findings, "reason_codes": ["expiry_or_dob_missing"]}
    if expiry < today:
        return {"status": "fail", "findings": findings, "reason_codes": ["document_expired"]}
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    findings["age"] = age
    if age < 18:
        return {"status": "fail", "findings": findings, "reason_codes": ["underage"]}
    return {"status": "pass", "findings": findings, "reason_codes": []}

# ---------- proof of address (Phase 3) ----------
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

def find_dates_in_text(text):
    """All plausible document dates in OCR text (ISO, 'D Month YYYY',
    DD/MM/YYYY). Returns list of datetime.date."""
    out = []
    t = (text or "")
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", t):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d: out.append(d)
    low = t.lower()
    for m in re.finditer(r"(\d{1,2})\s+([a-z]{3,9})\s+(\d{4})", low):
        mon = _MONTHS.get(m.group(2)[:3])
        if mon:
            d = _safe_date(int(m.group(3)), mon, int(m.group(1)))
            if d: out.append(d)
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t):
        d = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d: out.append(d)
    return out

def check_poa(ocr_text, applicant_first=None, applicant_last=None, address=None,
              window_days=90, today=None):
    """Proof-of-address: the document must carry a date inside the
    tenant's window, the applicant's name, and at least half of the
    applicant's address tokens. No date found -> unclear (OCR may have
    missed it — a human looks), stale date -> fail."""
    today = today or date.today()
    dates = find_dates_in_text(ocr_text)
    text_tokens = _tokens(ocr_text)
    name_tokens = _tokens(f"{applicant_first or ''} {applicant_last or ''}")
    addr_tokens = _tokens(address)
    name_found = bool(name_tokens) and name_tokens.issubset(text_tokens) or (bool(name_tokens) and bool(name_tokens & text_tokens) and len(name_tokens & text_tokens) >= min(2, len(name_tokens)))
    addr_overlap = (len(addr_tokens & text_tokens) / len(addr_tokens)) if addr_tokens else None
    findings = {"dates_found": [d.isoformat() for d in dates],
                "doc_date": None, "age_days": None, "window_days": window_days,
                "name_found": bool(name_found and name_tokens),
                "address_overlap": (round(addr_overlap, 2) if addr_overlap is not None else None)}
    if not dates:
        return {"status": "unclear", "findings": findings, "reason_codes": ["poa_no_date_found"]}
    past = [d for d in dates if d <= today]
    doc_date = max(past) if past else min(dates)
    findings["doc_date"] = doc_date.isoformat()
    findings["age_days"] = (today - doc_date).days
    if doc_date > today:
        return {"status": "unclear", "findings": findings, "reason_codes": ["poa_date_in_future"]}
    if (today - doc_date).days > window_days:
        return {"status": "fail", "findings": findings, "reason_codes": ["poa_outdated"]}
    if name_tokens and not findings["name_found"]:
        return {"status": "unclear", "findings": findings, "reason_codes": ["poa_name_not_found"]}
    if addr_tokens and addr_overlap is not None and addr_overlap < 0.5:
        return {"status": "unclear", "findings": findings, "reason_codes": ["poa_address_mismatch"]}
    return {"status": "pass", "findings": findings, "reason_codes": []}

# ---------- consistency ----------
def _norm(s):
    # Non-letters become SPACES, not nothing: deleting them glues words
    # across newlines/punctuation ("BILL\nANNA" -> "BILLANNA"), which
    # silently broke name/address token matching (caught in Phase 3 PoA
    # verification, 2026-10-26).
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", (s or "").upper())).strip()

def _tokens(s):
    return set(_norm(s).split())

def check_consistency(applicant_first, applicant_last, applicant_dob,
                      mrz_parsed=None, doc_first=None, doc_last=None, doc_dob=None, ocr_text=""):
    app_tokens = _tokens(f"{applicant_first} {applicant_last}")
    doc_tokens = set(); dob_match = None; name_source = None
    if mrz_parsed and mrz_parsed.get("valid") and mrz_parsed.get("names"):
        doc_tokens = _tokens(mrz_parsed["names"].get("surname", "") + " " + mrz_parsed["names"].get("given_names", ""))
        name_source = "mrz"
        mrz_dob = yymmdd_to_date(mrz_parsed["dob_yymmdd"], is_dob=True)
        if mrz_dob and applicant_dob:
            dob_match = (mrz_dob == parse_iso_date(applicant_dob))
    if not doc_tokens and (doc_first or doc_last):
        doc_tokens = _tokens(f"{doc_first} {doc_last}"); name_source = "document_fields"
        if doc_dob and applicant_dob:
            dob_match = (parse_iso_date(doc_dob) == parse_iso_date(applicant_dob))
    if not doc_tokens and ocr_text:
        # Last resort: look for the applicant's own name tokens in OCR text.
        ocr_tokens = _tokens(ocr_text)
        if app_tokens and app_tokens.issubset(ocr_tokens):
            doc_tokens = set(app_tokens); name_source = "ocr_text"
    findings = {"name_source": name_source, "applicant_tokens": sorted(app_tokens),
                "document_tokens": sorted(doc_tokens), "dob_match": dob_match}
    if not doc_tokens or not app_tokens:
        return {"status": "unclear", "findings": findings, "reason_codes": ["consistency_no_document_name"]}
    overlap = app_tokens & doc_tokens
    if app_tokens.issubset(doc_tokens) or doc_tokens.issubset(app_tokens):
        if dob_match is False:
            return {"status": "fail", "findings": findings, "reason_codes": ["dob_mismatch"]}
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if not overlap:
        return {"status": "fail", "findings": findings, "reason_codes": ["name_mismatch"]}
    # Partial overlap: a human should look.
    if dob_match is False:
        return {"status": "fail", "findings": findings, "reason_codes": ["dob_mismatch"]}
    return {"status": "unclear", "findings": findings, "reason_codes": ["name_partial_match"]}
