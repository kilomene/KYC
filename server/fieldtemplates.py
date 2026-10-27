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
    consecutive words."""
    norms = [_norm_word(it["text"]) for it in line]
    for lab in labels:
        parts = [_norm_word(p) for p in lab.split()]
        parts = [p for p in parts if p]
        if not parts:
            continue
        for i in range(0, len(norms) - len(parts) + 1):
            if norms[i:i + len(parts)] == parts:
                return lab, i + len(parts)
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
        # _plausible_number_fallback).
        fallback = None
        for ln in lines:
            hit = _label_span(ln, labels)
            if hit:
                _, after = hit
                cand = _value_from_tokens(field, [it["text"] for it in ln[after:]])
                if cand:
                    if field == "number" and validate_number(country, kind, cand) is False:
                        if fallback is None and _plausible_number_fallback(cand):
                            fallback = cand
                        continue
                    value, source = cand, "label"
                    break
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
