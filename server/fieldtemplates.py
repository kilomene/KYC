"""Per-document field-extraction templates (Phase 4 WS1, 2026-10-26).

For EVERY document type in server/docregistry.py there is a template
here: for each field (surname, given_names, dob, expiry where the type
carries one, document number) a RELATIVE ZONE on the document, LABEL
ANCHORS printed next to the field (including the local-language
labels on DE/FR/NL documents), and a FORMAT VALIDATOR for the document
number (a pattern per document type, and real check-digit algorithms
where the format carries one — Verhoeff for Aadhaar, the published
checksum-letter algorithm for Singapore NRIC/FIN).

Extraction is zone-first with label anchoring:
  1. label-anchored read — find the anchor words in the OCR word
     boxes, take the value that follows them on the same line;
  2. zone read — tokens whose centre falls inside the field's zone
     (date-shaped token for dates, pattern-shaped token for numbers,
     alphabetic tokens for names);
  3. text fallback — the label-anchored logic over the plain OCR text
     (what the pre-WS1 pipeline effectively did), run over the UNION
     of all OCR passes' lines when the caller supplies them
     (ocr_texts), not only the winning pass.
Every field records its SOURCE (label | zone | text) and, for the
document number, whether the extracted value passes the type's format
validator. A number extracted from the document that FAILS its own
type's format is a fail (field_number_format_invalid): the value was
read, and it is not shaped like the number that document carries.
Fallback discipline: an invalid candidate only surfaces that fail
when it is PLAUSIBLY the number (digit-bearing, or entirely
confusable-mappable to digits at plausible length — see
_plausible_number_fallback); a non-digit word harvested after a
label that appears in the document's own TITLE (the NIN slip's
header contains its number label) is discarded as not_found, never
adopted into a fail.

Honest limits: zones are the standard layout conventions for each
document family (portrait-left ID-1 cards, TD3 data pages, the NIN
slip's paper layout), consistent with the classification templates in
server/templates.py; they are not traced from licensed specimens.
Where a field cannot be read, the finding says not_found — nothing is
guessed. The NRIC checksum uses the published weight/letter tables
(ICA): weights 2,7,6,5,4,3,2 over the 7 digits, +4 for T/G prefixes,
mod 11 into the S/T letter set JZIHGFEDCBA or the F/G set
XWUTRQPNMLK.
"""
import re
from datetime import date

from . import checks as C
from . import docregistry as DOCREG

# ---------------- Verhoeff (Aadhaar check digit) ----------------
# The published Verhoeff algorithm (1969), as used by UIDAI: the 12th
# Aadhaar digit is a Verhoeff check digit over the first 11.
_VD = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
       [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
       [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
       [9,8,7,6,5,4,3,2,1,0]]
_VP = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
       [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
       [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
_VINV = [0,4,3,2,1,5,6,7,8,9]

def verhoeff_valid(number):
    """True iff the digit string passes Verhoeff validation."""
    s = re.sub(r"\D", "", str(number or ""))
    if not s:
        return False
    c = 0
    for i, ch in enumerate(reversed(s)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0

def verhoeff_digit(base):
    """The Verhoeff check digit for a digit string (fixture support)."""
    s = re.sub(r"\D", "", str(base or ""))
    c = 0
    for i, ch in enumerate(reversed(s)):
        c = _VD[c][_VP[(i + 1) % 8][int(ch)]]
    return str(_VINV[c])

def aadhaar_valid(number):
    s = re.sub(r"\D", "", str(number or ""))
    return len(s) == 12 and verhoeff_valid(s)

# ---------------- Singapore NRIC/FIN checksum letter ----------------
_NRIC_W = (2, 7, 6, 5, 4, 3, 2)
_NRIC_ST = "JZIHGFEDCBA"
_NRIC_FG = "XWUTRQPNMLK"

def nric_check_letter(prefix, digits7):
    total = sum(int(d) * w for d, w in zip(digits7, _NRIC_W))
    if prefix in ("T", "G"):
        total += 4
    table = _NRIC_ST if prefix in ("S", "T") else _NRIC_FG
    return table[total % 11]

def nric_valid(number):
    s = re.sub(r"[^A-Z0-9]", "", str(number or "").upper())
    m = re.fullmatch(r"([STFG])(\d{7})([A-Z])", s)
    if not m:
        return False
    return nric_check_letter(m.group(1), m.group(2)) == m.group(3)

_VALIDATORS = {"aadhaar": aadhaar_valid, "nric": nric_valid,
               "nin": lambda v: bool(re.fullmatch(r"\d{11}", re.sub(r"\D", "", str(v or ""))))}

# ---------------- labels per country (local language included) ----------------
_EN = {
    "surname": ["SURNAME", "LAST NAME", "FAMILY NAME"],
    "given_names": ["GIVEN NAMES", "GIVEN NAME", "FIRST NAME", "FORENAMES"],
    "dob": ["DATE OF BIRTH", "DOB", "DATE OF BIRTH/AGE", "BIRTH DATE"],
    "expiry": ["DATE OF EXPIRY", "DATE OF EXPIRE", "EXPIRY DATE", "EXPIRY", "EXPIRES", "VALID UNTIL", "EXP"],
    "number": ["DOCUMENT NUMBER", "DOCUMENT NO", "CARD NUMBER", "CARD NO", "ID NUMBER", "NUMBER", "NO"],
}
_LABELS = {
    "DE": {
        "surname": ["FAMILIENNAME", "NAME"],
        "given_names": ["VORNAMEN", "VORNAME"],
        "dob": ["GEBURTSDATUM", "GEBURTSTAG", "GEBOREN"],
        "expiry": ["GÜLTIG BIS", "GULTIG BIS", "ABLAUFDATUM", "GÜLTIGKEIT"],
        "number": ["AUSWEISNUMMER", "DOKUMENTNUMMER", "NUMMER"],
    },
    "FR": {
        "surname": ["NOM DE FAMILLE", "NOM"],
        "given_names": ["PRÉNOMS", "PRENOMS", "PRÉNOM", "PRENOM"],
        "dob": ["DATE DE NAISSANCE", "NÉ LE", "NE LE", "NAISSANCE"],
        "expiry": ["DATE D'EXPIRATION", "DATE DE VALIDITÉ", "EXPIRE LE", "VALIDITÉ", "VALIDITE"],
        "number": ["NUMÉRO DE DOCUMENT", "NUMÉRO", "NUMERO", "N°"],
    },
    "NL": {
        "surname": ["ACHTERNAAM", "NAAM"],
        "given_names": ["VOORNAMEN", "VOORNAAM"],
        "dob": ["GEBOORTEDATUM", "GEBOREN"],
        "expiry": ["GELDIG TOT", "VERVALDATUM", "GELDIGHEID"],
        "number": ["DOCUMENTNUMMER", "PERSOONSNUMMER", "NUMMER"],
    },
}
for _c in ("NG", "US", "GB", "CA", "AU", "GH", "KE", "ZA", "IN", "PH", "SG", "AE", "IE"):
    _LABELS[_c] = _EN
# Per-document label overrides where the printed anchors differ.
_LABEL_OVERRIDES = {
    ("IN", "aadhaar"): {"number": ["AADHAAR NUMBER", "UID", "NUMBER"],
                        "dob": ["DATE OF BIRTH", "DOB", "YEAR OF BIRTH"]},
    ("IN", "pan_card"): {"number": ["PERMANENT ACCOUNT NUMBER", "PAN"],
                         "surname": ["NAME"], "given_names": []},
    ("NG", "nin_slip"): {"number": ["NATIONAL IDENTIFICATION NUMBER", "NIN"],
                         "surname": ["SURNAME", "LAST NAME"],
                         "given_names": ["FIRST NAME", "MIDDLE NAME", "GIVEN NAMES"]},
    ("NG", "nin_card"): {"number": ["NIN", "NUMBER"]},
    ("NG", "national_id"): {"number": ["NIN", "NUMBER"]},
    ("SG", "nric"): {"number": ["NRIC NUMBER", "NRIC NO", "IC NUMBER", "NUMBER"]},
    ("AE", "emirates_id"): {"number": ["ID NUMBER", "IDENTITY NUMBER", "NUMBER"]},
    ("PH", "philid"): {"number": ["PCN", "CARD NUMBER", "NUMBER"]},
}

# ---------------- zones per layout class ----------------
_ZONES = {
    "passport": {"surname": (0.38, 0.08, 0.99, 0.28), "given_names": (0.38, 0.22, 0.99, 0.44),
                 "dob": (0.38, 0.40, 0.82, 0.62), "expiry": (0.38, 0.55, 0.88, 0.78),
                 "number": (0.55, 0.03, 0.99, 0.22)},
    "card": {"surname": (0.33, 0.05, 0.99, 0.27), "given_names": (0.33, 0.19, 0.99, 0.43),
             "dob": (0.33, 0.38, 0.78, 0.62), "expiry": (0.52, 0.55, 0.99, 0.80),
             "number": (0.33, 0.03, 0.99, 0.25)},
    # The real NIN slip layout (rectification 2026-10-26; research +
    # the owner's specimen geometry, measured on the perspective
    # warp): a NIMC header band occupies the top ~quarter; BELOW it a
    # ruled table — Tracking ID row top-left, NIN row under it,
    # surname / first / middle / gender rows in the CENTRE column
    # (labels ~x 0.36, values ~x 0.50-0.63), address right-centre,
    # portrait far right. Zones therefore start below the header
    # band: an earlier zone that overlapped the header read the
    # header line as the "surname" (measured on the owner's frame).
    # The standard slip prints NO date of birth (the premium slip
    # does) — the dob zone covers the lower-left field area and
    # simply finds nothing on slips that don't carry it.
    "slip": {"surname": (0.34, 0.27, 0.66, 0.40), "given_names": (0.34, 0.38, 0.66, 0.60),
             "dob": (0.01, 0.52, 0.37, 0.72), "expiry": (0.0, 0.0, 0.0, 0.0),
             "number": (0.01, 0.30, 0.37, 0.52)},
    "book": {"surname": (0.35, 0.10, 0.99, 0.32), "given_names": (0.35, 0.26, 0.99, 0.46),
             "dob": (0.35, 0.44, 0.80, 0.64), "expiry": (0.35, 0.60, 0.85, 0.80),
             "number": (0.35, 0.04, 0.99, 0.24)},
}
_LAYOUT_CLASS = {"nin_slip": "slip", "green_id_book": "book"}

# ---------------- document-number format per type ----------------
_GENERIC_NUM = r"[A-Z0-9]{6,20}"
_NUMBER_PATTERNS = {
    ("NG", "nin_slip"): r"\d{11}", ("NG", "nin_card"): r"\d{11}", ("NG", "national_id"): r"\d{11}",
    ("NG", "voter_card"): r"[0-9A-Z]{10,20}", ("NG", "drivers_licence"): r"[A-Z0-9]{8,15}",
    ("IN", "aadhaar"): r"\d{12}", ("IN", "pan_card"): r"[A-Z]{5}\d{4}[A-Z]",
    ("IN", "voter_id"): r"[A-Z]{3}\d{7}", ("IN", "drivers_licence"): r"[A-Z0-9-]{10,20}",
    ("SG", "nric"): r"[STFG]\d{7}[A-Z]", ("SG", "drivers_licence"): r"[STFG]\d{7}[A-Z]",
    ("AE", "emirates_id"): r"784\d{12}",
    ("PH", "philid"): r"\d{16}", ("PH", "umid"): r"\d{12}", ("PH", "drivers_licence"): r"[A-Z]\d{10}",
    ("ZA", "smart_id"): r"\d{13}", ("ZA", "green_id_book"): r"\d{13}",
    ("GH", "national_id"): r"GHA\d{10}",
    ("DE", "national_id"): r"[A-Z0-9]{9}", ("NL", "national_id"): r"[A-Z0-9]{9}",
    ("FR", "national_id"): r"[A-Z0-9]{9,12}",
    ("US", "drivers_license"): r"[A-Z0-9-]{5,20}", ("US", "drivers_licence"): r"[A-Z0-9-]{5,20}",
    ("US", "state_id"): r"[A-Z0-9-]{5,20}",
}
_NUMBER_VALIDATORS = {
    ("IN", "aadhaar"): "aadhaar", ("SG", "nric"): "nric", ("SG", "drivers_licence"): "nric",
    ("NG", "nin_slip"): "nin", ("NG", "nin_card"): "nin", ("NG", "national_id"): "nin",
}

def _build_templates():
    out = {}
    for country, docs in DOCREG.DOCUMENT_REGISTRY.items():
        for kind, entry in docs.items():
            labels = {f: list(v) for f, v in _LABELS.get(country, _EN).items()}
            for f, v in _LABEL_OVERRIDES.get((country, kind), {}).items():
                labels[f] = list(v)
            zones = _ZONES[_LAYOUT_CLASS.get(kind, "passport" if kind in ("passport",) else "card")]
            fields = {}
            for field in ("surname", "given_names", "dob", "expiry", "number"):
                if field == "expiry" and not entry.get("has_expiry"):
                    continue
                spec = {"zone": zones[field], "labels": labels.get(field, [])}
                if field == "number":
                    spec["pattern"] = _NUMBER_PATTERNS.get((country, kind), _GENERIC_NUM)
                    if (country, kind) in _NUMBER_VALIDATORS:
                        spec["validator"] = _NUMBER_VALIDATORS[(country, kind)]
                fields[field] = spec
            level = "full" if (country in ("NG", "US") or kind != "passport") else "generic"
            out[(country, kind)] = {"level": level, "layout": _LAYOUT_CLASS.get(kind, "passport" if kind == "passport" else "card"),
                                    "fields": fields}
    return out

FIELD_TEMPLATES = _build_templates()

def get_field_template(country, kind):
    return FIELD_TEMPLATES.get(((country or "").upper(), kind or ""))

def validate_number(country, kind, value):
    """Format validation for an extracted document number.
    -> True/False, or None when the type has no validator."""
    tpl = get_field_template(country, kind)
    if not tpl:
        return None
    spec = tpl["fields"].get("number") or {}
    raw = re.sub(r"[\s-]", "", str(value or "").upper())
    validator = spec.get("validator")
    if validator:
        return _VALIDATORS[validator](raw)
    pattern = spec.get("pattern")
    if pattern:
        return bool(re.fullmatch(pattern, raw))
    return None

# ---------------- date parsing ----------------
_MONTHS = {}
for _i, _names in enumerate([
        ("JAN", "JANUARY", "JANUAR", "JANVIER", "JANUARI"),
        ("FEB", "FEBRUARY", "FEBRUAR", "FÉVRIER", "FEVRIER", "FEBRUARI"),
        ("MAR", "MARCH", "MÄRZ", "MAERZ", "MARS", "MAART"),
        ("APR", "APRIL", "AVRIL"),
        ("MAY", "MAI", "MEI"),
        ("JUN", "JUNE", "JUNI", "JUIN"),
        ("JUL", "JULY", "JULI", "JUILLET", "JULI"),
        ("AUG", "AUGUST", "AOÛT", "AOUT", "AUGUSTUS"),
        ("SEP", "SEPTEMBER", "SEPTEMBRE", "SEPTEMBER"),
        ("OCT", "OCTOBER", "OKTOBER", "OCTOBRE", "OKTOBER"),
        ("NOV", "NOVEMBER", "NOVEMBRE", "NOVEMBER"),
        ("DEC", "DECEMBER", "DEZEMBER", "DÉCEMBRE", "DECEMBRE", "DECEMBER")]):
    for _n in _names:
        _MONTHS[_n] = _i + 1

def parse_date_value(s):
    """Parse a printed date value in the formats the launch documents
    use (ISO, DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY, '12 AUG 1974',
    '12 August 1974'). Returns a date or None."""
    if not s:
        return None
    t = str(s).strip().upper()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", t)
    if m:
        return C._safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        return C._safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{1,2})\s+([A-ZÄÉÛ]+)\s+(\d{4})", t)
    if m and m.group(2) in _MONTHS:
        return C._safe_date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"([A-ZÄÉÛ]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and m.group(1) in _MONTHS:
        return C._safe_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
    return None

# ---------------- extraction ----------------

def _norm_word(w):
    return re.sub(r"[^A-Z0-9ÄÉÈÜÖÄSS]", "", (w or "").upper())

def _group_lines(words):
    """Group OCR word boxes into lines by vertical proximity."""
    items = []
    for wd in words or []:
        box = wd["box"]
        items.append({"text": wd["text"], "cx": (box[0] + box[2]) / 2,
                      "cy": (box[1] + box[3]) / 2, "box": box})
    items.sort(key=lambda it: (round(it["cy"] / 0.03), it["cx"]))
    lines = []
    for it in items:
        if lines and abs(it["cy"] - lines[-1][0]["cy"]) <= 0.03:
            lines[-1].append(it)
        else:
            lines.append([it])
    for ln in lines:
        ln.sort(key=lambda it: it["cx"])
    return lines

def _label_span(line, labels):
    """If a line starts with / contains a label anchor, return
    (label, index_after_label) else None. Multi-word labels match
    consecutive words, tolerating ONE stray token interspersed
    between the label's words — merged word streams (a full-page
    pass plus tile reads of the same page) interleave fragments
    into label lines ('First AN Name:'), and a label that is
    plainly there must still anchor."""
    norms = [_norm_word(it["text"]) for it in line]
    for lab in labels:
        parts = [_norm_word(p) for p in lab.split()]
        parts = [p for p in parts if p]
        if not parts:
            continue
        for i in range(0, len(norms) - len(parts) + 1):
            if norms[i:i + len(parts)] == parts:
                return lab, i + len(parts)
        if len(parts) >= 2:
            for i in range(0, len(norms) - len(parts)):
                j, k, skips = i, 0, 0
                while j < len(norms) and k < len(parts):
                    if norms[j] == parts[k]:
                        k += 1
                    else:
                        skips += 1
                        if skips > 1:
                            break
                    j += 1
                if k == len(parts):
                    return lab, j
    return None

def _value_from_tokens(field, tokens):
    """Interpret raw value tokens for a field. -> value string or None."""
    if not tokens:
        return None
    joined = " ".join(tokens)
    if field in ("dob", "expiry"):
        d = parse_date_value(joined)
        if d:
            return d.isoformat()
        # date may be split across tokens like 12 / 08 / 1974
        d = parse_date_value(re.sub(r"\s+", "", joined))
        return d.isoformat() if d else None
    if field == "number":
        for i, tok in enumerate(tokens):
            cand = re.sub(r"[\s-]", "", tok.upper())
            if len(cand) >= 4 and re.fullmatch(r"[A-Z0-9]+", cand):
                # Grouped digit numbers (e.g. Aadhaar prints
                # "1234 5678 9012"): keep concatenating following
                # pure-digit tokens.
                if cand.isdigit():
                    j = i + 1
                    while j < len(tokens) and re.fullmatch(r"\d+", tokens[j]) and len(cand) + len(tokens[j]) <= 20:
                        cand += tokens[j]
                        j += 1
                return cand
        return None
    # names: alphabetic tokens only, stop at digits/labels
    keep = []
    for tok in tokens:
        t = re.sub(r"[^A-Za-zÀ-ÿ-]", "", tok)
        if t and not any(ch.isdigit() for ch in tok):
            keep.append(t.upper())
        if len(keep) >= 3:
            break
    # A leading single letter ahead of a real name token is read
    # debris (watermark fragments on laminated documents — the
    # owner's slip read 'E AYANSIPE'), never the start of a printed
    # surname/given-names value.
    if len(keep) >= 2 and len(keep[0]) == 1 and len(keep[1]) >= 3:
        keep = keep[1:]
    return " ".join(keep) if keep else None

_NUMERIC_CONFUSABLES = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1",
                                      "Z": "2", "S": "5", "G": "6", "B": "8"})

def _normalize_numeric(value):
    return str(value or "").upper().translate(_NUMERIC_CONFUSABLES)

def _is_digit_format(spec):
    """True when the field's number format is digit-only (a check-digit
    validator for digits, or a pattern with no letter classes)."""
    if (spec or {}).get("validator") in ("nin", "aadhaar"):
        return True
    pattern = (spec or {}).get("pattern") or ""
    return bool(pattern) and "[A-Z" not in pattern

def _recover_number_zone(image_path, spec, partial, words=None):
    """Corroborated digit-zone recovery (owner's real NIN slip,
    2026-10-26): the ordinary passes read his number's first 8 digits
    and mangled the tail where the digits cross the watermark — the
    number WAS in the photo, below the general passes' quality bar.
    When (and only when) the resolved number is missing or
    format-invalid for a fixed-length digit format, this pass zooms
    on the number's own location and reads it with a matrix of
    independent variants (scales x {plain, Otsu, median+Otsu} x two
    page modes, digits whitelisted).

    Location: the word boxes of the digit-bearing tokens the primary
    read already produced inside the template's number zone (the
    anchor), expanded — falling back to the whole zone. The crop is
    taken from the ORIGINAL image (mapped through the framing quad),
    never from the warped rendition: the warp resamples an already
    soft source a second time, and the first implementation measured
    exactly that — every rendition-crop read carried junk prefixes
    from the label column and table rules, and no candidate won.

    A candidate is adopted ONLY when it wins the vote decisively —
    at least 3 exact-length reads and at least twice the runner-up —
    AND agrees with the digits the ordinary passes did read on at
    least 75% of the overlapping prefix. The recovery completes a
    corroborated read; it never invents one: no decisive winner, no
    number."""
    try:
        pat = (spec or {}).get("pattern") or ""
        m = re.fullmatch(r"\\d\{(\d+)\}", pat)
        zone = (spec or {}).get("zone")
        if not m or not zone or tuple(zone) == (0.0, 0.0, 0.0, 0.0) or not image_path:
            return None
        want = int(m.group(1))
        import shutil, subprocess, tempfile, os
        exe = shutil.which("tesseract")
        if not exe:
            return None
        import cv2
        import numpy as np
        from . import framing as FRAMING
        # ---- locate: anchor word boxes inside the zone ----
        pd = re.sub(r"\D", "", _normalize_numeric(str(partial))) if partial else ""
        anchors = []
        # (a) the field's own LABEL is the strongest landmark: it is
        # large, bold print that survives at resolutions where the
        # value's digits do not (measured on the owner's low-res
        # upload: label 'NIN:' read at conf 96 while the value read
        # as garbage). The value sits on the label's own row,
        # immediately to its right.
        label_words = set()
        for lab in (spec.get("labels") or []):
            parts = [t for t in re.split(r"[^A-Za-z0-9]+", lab.upper()) if len(t) >= 3]
            if len(parts) == 1:
                label_words.add(parts[0])
        label_box = None
        for w in (words or []):
            tok = re.sub(r"[^A-Za-z0-9]", "", str(w.get("text") or "").upper())
            if tok in label_words:
                box = w.get("box") or (0, 0, 0, 0)
                cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
                if zone[0] - 0.06 <= cx <= zone[2] + 0.06 and zone[1] - 0.06 <= cy <= zone[3] + 0.06:
                    label_box = box
                    break
        if label_box is not None:
            lh = label_box[3] - label_box[1]
            lcy = (label_box[1] + label_box[3]) / 2.0
            frac = (min(1.0, label_box[2] + 0.004), max(0.0, lcy - 1.1 * lh),
                    min(1.0, label_box[2] + 0.36), min(1.0, lcy + 1.1 * lh))
            anchors = None  # frac decided by the label
        else:
            frac = None
        if frac is None:
            for w in (words or []):
                box = w.get("box") or (0, 0, 0, 0)
                cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
                if not (zone[0] - 0.05 <= cx <= zone[2] + 0.05 and zone[1] - 0.05 <= cy <= zone[3] + 0.05):
                    continue
                digs = re.sub(r"\D", "", _normalize_numeric(str(w.get("text") or "")))
                if len(digs) >= 4 and (not pd or digs in pd or pd.startswith(digs[:6]) or digs[:6] in pd):
                    anchors.append(box)
        if frac is None and anchors:
            ax0 = min(b[0] for b in anchors); ay0 = min(b[1] for b in anchors)
            ax1 = max(b[2] for b in anchors); ay1 = max(b[3] for b in anchors)
            aw, ah = ax1 - ax0, ay1 - ay0
            frac = (max(0.0, ax0 - 0.6 * aw - 0.015), max(0.0, ay0 - 0.9 * ah - 0.01),
                    min(1.0, ax1 + 0.6 * aw + 0.015), min(1.0, ay1 + 0.9 * ah + 0.01))
        if frac is None:
            frac = (max(0.0, zone[0] - 0.02), max(0.0, zone[1] - 0.02),
                    min(1.0, zone[2] + 0.02), min(1.0, zone[3] + 0.02))
        # ---- crop from the ORIGINAL via the framing quad ----
        orig = cv2.imread(image_path)
        if orig is None:
            return None
        H, W = orig.shape[:2]
        analysis = FRAMING.analyse_path(image_path)
        quad = analysis.get("quad") if analysis else None
        if quad is not None:
            # Only a quad the framing check itself would accept may
            # steer the crop — the same gates warped_rendition uses.
            # A small inner feature (a portrait box, a text block)
            # otherwise hijacks the mapping and the crop lands on a
            # fragment (measured on the borderless synthetic slip:
            # framing "found" the portrait box, aspect 0.80, and the
            # mapped crop read nothing).
            area = analysis.get("area_ratio") or 0.0
            width_frac = analysis.get("width_frac") or 0.0
            if not (area >= FRAMING.PASS_RATIO or
                    (width_frac >= FRAMING.WIDE_MIN_WIDTH_FRAC and area >= FRAMING.WIDE_PASS_AREA)):
                quad = None
        if quad is not None:
            q = np.array(quad, dtype="float64")  # TL, TR, BR, BL
            def _map(u, v):
                top = q[0] + u * (q[1] - q[0])
                bot = q[3] + u * (q[2] - q[3])
                return top + v * (bot - top)
            pts = [_map(frac[0], frac[1]), _map(frac[2], frac[1]),
                   _map(frac[2], frac[3]), _map(frac[0], frac[3])]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            x0 = max(0, int(min(xs)) - 4); x1 = min(W, int(max(xs)) + 4)
            y0 = max(0, int(min(ys)) - 4); y1 = min(H, int(max(ys)) + 4)
        else:
            x0 = int(W * frac[0]); x1 = int(W * frac[2])
            y0 = int(H * frac[1]); y1 = int(H * frac[3])
        crop = orig[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        votes = {}
        for scale in (3, 4, 5, 6):
            up = cv2.resize(grey, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            variants = (up,
                        cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
                        cv2.threshold(cv2.medianBlur(up, 3), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
            for arr in variants:
                fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
                try:
                    cv2.imwrite(tmp, arr)
                    for psm in ("7", "6"):
                        out = subprocess.run([exe, tmp, "stdout", "--psm", psm,
                                              "-c", "tessedit_char_whitelist=0123456789"],
                                             capture_output=True, text=True, timeout=60)
                        d = re.sub(r"\D", "", out.stdout or "")
                        if len(d) == want:
                            votes[d] = votes.get(d, 0) + 1
                        elif want < len(d) <= want + 4:
                            # The value's digits with junk bled in
                            # from a neighbouring column (measured:
                            # the true number as the first 11 of a
                            # 14-digit read). Every window votes;
                            # only a candidate repeated across
                            # independent variants can clear the
                            # decisive-vote bar below.
                            for k in range(0, len(d) - want + 1):
                                w = d[k:k + want]
                                votes[w] = votes.get(w, 0) + 1
                finally:
                    try: os.unlink(tmp)
                    except Exception: pass
        if not votes:
            return None
        ranked = sorted(votes.items(), key=lambda kv: -kv[1])
        best, best_votes = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else 0
        if best_votes < 3 or best_votes < 2 * max(runner, 1):
            return None
        if len(pd) >= 6:
            agree = sum(1 for a, b in zip(pd, best) if a == b)
            if agree < 0.75 * min(len(pd), want):
                return None
        return best
    except Exception:
        return None


def _plausible_number_fallback(cand):
    """Fallback discipline (Session-5 diagnosis, 2026-10-26): may an
    INVALID label-line candidate still surface as the number (so its
    format failure fails the extraction)? Only when it is PLAUSIBLY
    the number:

      * it bears a real digit (a short or misread number — "12345"
        for an 11-digit NIN — is a number that failed, and the FAIL
        is the honest verdict), or
      * it carries no digit but is ENTIRELY confusable-mappable to
        digits at a plausible length (>= 6) — a digit-format number
        OCR could have read as pure letters.

    A plain word is neither: the NIN slip's header line contains the
    label text itself ("...Identification Number" is the field's own
    anchor), and the token after the title — a 4-char alphabetic
    header word — was adopted by the old fallback and converted a
    not-found into a hard FAIL on a genuine document. Implausible
    candidates are DISCARDED: the field records not_found and the
    search continues."""
    if not cand:
        return False
    if any(ch.isdigit() for ch in cand):
        return True
    normed = _normalize_numeric(cand)
    return normed.isdigit() and len(normed) >= 6

def extract_fields(image_path, country, kind, ocr_text="", words=None, ocr_texts=None):
    """Template-guided field extraction. Returns the standard check
    dict; findings carry per-field {value, source, format_valid}.

    ocr_texts: the texts of ALL OCR passes (vision.read_document_text
    exposes them as "pass_texts"), not only the winning pass. The
    text fallback (step 3) searches the UNION of every pass's lines:
    the pass that wins on confidence/MRZ grounds is not always the
    pass that read a given printed field — passes disagree by zone
    on real captures, and judging extraction on the winner alone
    manufactures not-found fields out of text the pipeline had in
    fact read."""
    country = (country or "").upper()
    tpl = get_field_template(country, kind)
    if tpl is None:
        return {"status": "unclear",
                "findings": {"template_level": "none", "claimed": f"{country}/{kind}", "fields": {}},
                "reason_codes": ["field_template_missing"]}
    if words is None:
        from . import vision as VISION
        words = VISION.ocr_words(image_path) if image_path else []
    lines = _group_lines(words)
    text_lines = []
    _seen_lines = set()
    for _t in [ocr_text or ""] + list(ocr_texts or []):
        for _l in _t.splitlines():
            if _l.strip() and _l not in _seen_lines:
                _seen_lines.add(_l)
                text_lines.append(_l)
    fields_out = {}
    all_labels = [lab for spec in tpl["fields"].values() for lab in spec["labels"]]
    for field, spec in tpl["fields"].items():
        labels = spec["labels"]
        value, source = None, None
        # 1) label-anchored in word boxes. For the NUMBER field a
        # label hit whose value FAILS the type's format validation
        # does not end the search: document titles contain the label
        # words too (the NIN slip's header "...Identification Number
        # Slip" would otherwise harvest the word after the title as
        # the "number" — measured on a layout-faithful drawing). The
        # first VALID candidate wins; the first PLAUSIBLE invalid one
        # is kept as a fallback so a genuine format failure still
        # surfaces — an implausible one (a non-digit title word) is
        # discarded outright, never adopted (see
        # _plausible_number_fallback). Among valid candidates the
        # spec's label preference order decides, then line order.
        fallback = None
        valid_cands = []  # (label_rank, line_order, cand)
        for li, ln in enumerate(lines):
            hit = _label_span(ln, labels)
            if hit:
                lab_hit, after = hit
                items_after = ln[after:]
                if field in ("surname", "given_names"):
                    # Column discipline (owner's real slip, 2026-10-26):
                    # NIMC prints Surname and Address in the same row
                    # band, different columns — the label-line harvest
                    # walked across the gutter and adopted address
                    # words into the surname ('E AYANSIPE ADDRESS').
                    # A name value lives in ONE cell: stop at the
                    # first column gutter (a horizontal gap wider
                    # than 5% of the document between tokens).
                    trimmed = []
                    prev = None
                    for it in items_after:
                        if prev is not None and it["box"][0] - prev["box"][2] > 0.05:
                            break
                        trimmed.append(it); prev = it
                    items_after = trimmed
                cand = _value_from_tokens(field, [it["text"] for it in items_after])
                if cand:
                    if field == "number" and validate_number(country, kind, cand) is False:
                        if fallback is None and _plausible_number_fallback(cand):
                            fallback = cand
                        continue
                    # Label PRIORITY beats line order: the spec lists
                    # a field's labels in preference order ('FIRST
                    # NAME' before 'MIDDLE NAME'), so a valid value
                    # under the primary label wins even when a
                    # secondary label's line comes first in the
                    # stream (merged word sources reorder lines).
                    valid_cands.append((labels.index(lab_hit), li, cand))
        if valid_cands:
            valid_cands.sort(key=lambda t: (t[0], t[1]))
            value, source = valid_cands[0][2], "label"
        if value is None and fallback is not None:
            value, source = fallback, "label"
        # 2) zone read
        if value is None and spec.get("zone") and spec["zone"] != (0.0, 0.0, 0.0, 0.0):
            z = spec["zone"]
            toks = []
            for ln in lines:
                for it in ln:
                    if z[0] <= it["cx"] <= z[2] and z[1] <= it["cy"] <= z[3]:
                        if _label_span([it], labels) or _norm_word(it["text"]) in [_norm_word(x) for x in all_labels]:
                            continue
                        toks.append(it["text"])
            if field == "number":
                # Prefer a DIGIT-BEARING token that passes the type's
                # own format validator, then any digit-bearing token —
                # a zone also contains title words and surnames, which
                # generic patterns would otherwise happily accept.
                for tok in toks:
                    if any(ch.isdigit() for ch in tok) and validate_number(country, kind, tok) is True:
                        value = re.sub(r"[\s-]", "", tok.upper())
                        break
                if value is None:
                    digit_toks = [t for t in toks if any(ch.isdigit() for ch in t)]
                    value = _value_from_tokens(field, digit_toks)
            else:
                value = _value_from_tokens(field, toks)
            if value:
                source = "zone"
        # 3) text fallback (label-anchored over plain OCR text).
        # Word-BOUNDARY matching: a bare substring search lets the
        # surname anchor "NAME" match inside "VORNAMEN" and harvest
        # the given-names line as the surname (measured, WS1 bench).
        if value is None and text_lines:
            fallback = None
            for raw in text_lines:
                up = raw.upper()
                for lab in labels:
                    m = re.search(r"(?<![A-Z0-9ÄÉÜ])" + re.escape(lab) + r"(?![A-Z0-9ÄÉÜ])", up)
                    if m:
                        cand = _value_from_tokens(field, raw[m.end():].split())
                        if cand:
                            if field == "number" and validate_number(country, kind, cand) is False:
                                if fallback is None and _plausible_number_fallback(cand):
                                    fallback = cand
                                continue
                            value, source = cand, "text"
                            break
                if value:
                    break
            if value is None and fallback is not None:
                value, source = fallback, "text"
        # 4) corroborated digit-zone recovery (number field only):
        # the resolved number is missing or format-invalid, but the
        # digits may still be recoverable from the number zone by a
        # dedicated variant-vote read. Runs only on this failure —
        # the ordinary sources always win when they produce a valid
        # number.
        if field == "number" and _is_digit_format(spec) and \
                (value is None or validate_number(country, kind, value) is False):
            recovered = _recover_number_zone(image_path, spec, value, words=words)
            if recovered:
                value, source = recovered, "zone_recovery"
        entry = {"value": value, "source": source}
        if field == "number" and value:
            valid = validate_number(country, kind, value)
            if valid is False and _is_digit_format(spec):
                # Digit-format numbers suffer classic OCR confusables
                # (O/0, I-L/1, S/5, B/8, G/6, Z/2). Normalise and
                # re-validate; only a value that then PASSES its
                # check digit / format is rewritten.
                normed = _normalize_numeric(value)
                if normed != value and validate_number(country, kind, normed) is True:
                    entry["value_raw"] = value
                    value = normed
                    entry["value"] = value
                    valid = True
            entry["format_valid"] = valid
        fields_out[field] = entry
    extracted = sum(1 for f in fields_out.values() if f["value"])
    findings = {"template_level": tpl["level"], "layout": tpl["layout"],
                "claimed": f"{country}/{kind}", "fields": fields_out,
                "fields_extracted": extracted}
    num = fields_out.get("number") or {}
    if num.get("value") and num.get("format_valid") is False:
        return {"status": "fail", "findings": findings,
                "reason_codes": ["field_number_format_invalid"]}
    if extracted:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    return {"status": "unclear", "findings": findings,
            "reason_codes": ["field_extraction_sparse"]}
