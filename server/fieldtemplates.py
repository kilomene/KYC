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
    ("NG", "nin_card"): {"number": ["NIN", "NUMBER"],
                         "surname": ["SURNAME", "NOM"],
                         "given_names": ["GIVEN NAMES", "PRENOMS", "PRÉNOMS"],
                         "dob": ["DATE OF BIRTH", "DATE DE NAISSANCE", "DOB"]},
    ("NG", "national_id"): {"number": ["NIN", "NUMBER"]},
    # INEC voter's card (calibration 2026-10-27, owner's genuine
    # sample): the identity number is the VIN; the PU code beside
    # the portrait is a polling-unit code, not an identity number.
    ("NG", "voter_card"): {"number": ["VIN", "VOTER IDENTIFICATION NUMBER"],
                           "surname": ["SURNAME"],
                           "given_names": ["FIRST NAME", "GIVEN NAMES"],
                           "dob": ["DATE OF BIRTH", "DOB"]},
    # FRSC driver's licence, 2011 scheme (calibration 2026-10-27):
    # the front's own abbreviations are the anchors — L/NO for the
    # number, D of B / ISS / EXP for the dates.
    ("NG", "drivers_licence"): {"number": ["L/NO", "LICENCE NO", "LICENSE NO"],
                                "surname": ["SURNAME", "NAME"],
                                "given_names": ["FIRST NAME", "OTHER NAMES", "GIVEN NAMES"],
                                "dob": ["D OF B", "DOB", "DATE OF BIRTH"],
                                "expiry": ["EXP", "EXPIRY"]},
    # US licences/IDs print in two dialects: California-style word
    # labels (LN / FN / DL / DOB / EXP) and the numbered AAMVA
    # furniture most other states use (4d LIC NO, 3 DOB, 4b EXP,
    # 1/2 name lines) — plus state variants like Virginia's
    # 'Customer identifier' and bare 'Name'. Calibration
    # 2026-10-28 across IL/CO/OK/NV/VA/WI/OR cards: without the
    # numbered composites the reader missed dates wholesale, and
    # on Wisconsin an unanchored zone scoop borrowed the ISSUE
    # date into both date slots and falsely expired the card.
    ("US", "drivers_license"): {"number": ["4D LIC NO", "LIC NO", "DL NO", "DL", "DLN", "4D",
                                           "CUSTOMER IDENTIFIER"],
                                "surname": ["LN", "SURNAME", "NAME"],
                                "given_names": ["FN", "GIVEN NAMES", "FIRST NAME"],
                                "dob": ["3 DOB", "DOB", "DATE OF BIRTH"],
                                "expiry": ["4B EXP", "EXP", "EXPIRES"]},
    # State IDs (New York non-driver ID, Illinois ID cards): same
    # numbered furniture; IL prints '4d LIC NO' even on ID cards.
    ("US", "state_id"): {"number": ["4D LIC NO", "LIC NO", "ID", "ID NUMBER"],
                         "surname": ["LN", "SURNAME", "NAME"],
                         "given_names": ["FN", "GIVEN NAMES", "FIRST NAME"],
                         "dob": ["3 DOB", "DOB", "DATE OF BIRTH"],
                         "expiry": ["4B EXP", "EXPIRES", "EXPIRY", "EXP"]},
    # Canada passport data page is bilingual throughout; the
    # French halves of the labels are first-class anchors.
    ("CA", "passport"): {"number": ["PASSPORT NO", "PASSPORT", "PASSEPORT"],
                         "surname": ["SURNAME", "NOM"],
                         "given_names": ["GIVEN NAMES", "PRENOMS", "PRÉNOMS"],
                         "dob": ["DATE OF BIRTH", "DATE DE NAISSANCE"],
                         "expiry": ["DATE OF EXPIRY", "DATE D'EXPIRATION", "EXPIRY"]},
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
    # INEC voter's card (measured on the owner's genuine sample,
    # 2026-10-27): coat of arms + title band on top, PU CODE beside
    # the portrait at the right, the data block down the LEFT two
    # thirds — name line (SURNAME, FIRST MIDDLE) upper-middle, DOB
    # with GENDER beside it, OCCUPATION, ADDRESS, and the VIN line
    # across the lower-middle. Portrait occupies the right third.
    "inecpvc": {"surname": (0.03, 0.27, 0.67, 0.44), "given_names": (0.03, 0.35, 0.67, 0.52),
                "dob": (0.03, 0.40, 0.50, 0.58), "expiry": (0.0, 0.0, 0.0, 0.0),
                "number": (0.03, 0.50, 0.70, 0.74)},
    # FRSC licence, 2011 scheme (owner's genuine sample): header
    # band, L/NO band under it, portrait LEFT (sample is ground
    # truth for its vintage), data block to the right of the
    # portrait, dates mid-block, address lower.
    "frsc": {"surname": (0.32, 0.28, 0.99, 0.44), "given_names": (0.32, 0.36, 0.99, 0.54),
             "dob": (0.32, 0.48, 0.68, 0.66), "expiry": (0.58, 0.48, 0.99, 0.68),
             "number": (0.28, 0.12, 0.99, 0.28)},
    # NIMC digital NIN slip — the plastic print of the NIN record
    # (owner's genuine sample): header band, portrait left, name /
    # DOB / sex block centre, QR top-right, and the 11-digit NIN
    # printed LARGE across the bottom strip. NOT the paper slip's
    # table and NOT the GMPC chip card (that card's identity rides
    # its MRZ, which the identity layer merges before zones).
    "nin_digital": {"surname": (0.24, 0.36, 0.72, 0.52), "given_names": (0.24, 0.47, 0.72, 0.64),
                    "dob": (0.24, 0.58, 0.62, 0.78), "expiry": (0.0, 0.0, 0.0, 0.0),
                    "number": (0.15, 0.76, 0.99, 0.99)},
    # New York non-driver ID (owner's genuine sample, landscape
    # 21+ card): greyscale portrait top-LEFT, ID number band under
    # the title, surname/given stacked centre-right of the portrait
    # row, address under the names, DOB + Expires bold at the
    # bottom-left of the data block.
    "nyid": {"surname": (0.28, 0.26, 0.82, 0.42), "given_names": (0.28, 0.36, 0.82, 0.54),
             "dob": (0.26, 0.60, 0.62, 0.80), "expiry": (0.52, 0.60, 0.88, 0.82),
             "number": (0.28, 0.06, 0.82, 0.24)},
}
_LAYOUT_CLASS = {"nin_slip": "slip", "green_id_book": "book"}
# Per-(country, kind) layout classes where one kind name spans
# countries with genuinely different card geometry.
_LAYOUT_CLASS_CC = {("NG", "voter_card"): "inecpvc",
                    ("NG", "drivers_licence"): "frsc",
                    ("NG", "nin_card"): "nin_digital",
                    ("US", "state_id"): "nyid"}

# ---------------- document-number format per type ----------------
_GENERIC_NUM = r"[A-Z0-9]{6,20}"
_NUMBER_PATTERNS = {
    ("NG", "nin_slip"): r"\d{11}", ("NG", "nin_card"): r"\d{11}", ("NG", "national_id"): r"\d{11}",
    ("NG", "voter_card"): r"[0-9A-Z]{10,22}", ("NG", "drivers_licence"): r"[A-Z0-9]{10,14}",
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
            layout = _LAYOUT_CLASS_CC.get((country, kind)) or _LAYOUT_CLASS.get(
                kind, "passport" if kind in ("passport",) else "card")
            zones = _ZONES[layout]
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
            out[(country, kind)] = {"level": level, "layout": layout,
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

def parse_date_value(s, mdy=False):
    """Parse a printed date value in the formats the launch documents
    use (ISO, DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY, '12 AUG 1974',
    '12 August 1974'). Returns a date or None.

    The numeric a/b/year order is day-first by default — most launch
    countries print DD/MM/YYYY. Two disambiguators, in order:
    (1) VALIDITY — a 'month' above 12 cannot be a month, so when the
    second number exceeds 12 the only possible reading is
    month-first (US '04/20/2031': the old day-first-only parse
    returned None, the field fell to the zone scoop, and a borrowed
    issue date landed in both date slots — measured on a genuine
    Wisconsin licence, 2026-10-28). This fires only where the
    day-first reading is impossible, so day-first documents are
    untouched.
    (2) LOCALE — when both numbers are <= 12 the order is genuinely
    ambiguous; callers pass mdy=True for month-first countries
    (US, PH) so '04/03/2023' reads as April 3, not March 4."""
    if not s:
        return None
    t = str(s).strip().upper()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", t)
    if m:
        return C._safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if b > 12 and a <= 12:
            return C._safe_date(y, a, b)
        if mdy and a <= 12 and b <= 12:
            return C._safe_date(y, a, b)
        return C._safe_date(y, b, a)
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

def _edit_distance_le1(a, b):
    """True iff a and b are within one insertion, deletion or
    substitution of each other (single-letter OCR misreads of a
    printed label word — 'LAME' for 'NAME' where the table rule
    ate the first letter's left stroke)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1; j += 1
        elif not skipped:
            skipped = True; j += 1
        else:
            return False
    return True


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
        if len(parts) >= 2:
            # Fused label: segmentation sometimes merges the label's
            # words into ONE token ('|FirstName:' on the owner's
            # high-res slip read) — the concatenation of the parts is
            # still unmistakably the label, and it must anchor.
            fused = "".join(parts)
            for i, n in enumerate(norms):
                if n == fused:
                    return lab, i + 1
        for i in range(0, len(norms) - len(parts) + 1):
            if norms[i:i + len(parts)] == parts:
                return lab, i + len(parts)
        if len(parts) == 1 and len(parts[0]) >= 2:
            # AAMVA field-number prefix fused to the label: US cards
            # print '3 DOB' / '4b EXP', and segmentation routinely
            # fuses the furniture into the label token ('3DOB',
            # '4BEXP' — measured on a genuine Wisconsin licence,
            # 2026-10-28: '3DOB' never matched the DOB anchor, the
            # field fell to the zone scoop). The digits (plus the
            # optional sub-letter) are anchor furniture, not value.
            for i, n in enumerate(norms):
                for _pat in (r"\d{1,2}([A-Z]{2,})", r"\d{1,2}[A-Z]([A-Z]{2,})"):
                    m = re.fullmatch(_pat, n)
                    if m and m.group(1) == parts[0]:
                        return lab, i + 1
        if len(parts) == 1 and len(parts[0]) >= 5:
            # One-letter misread of a single-word label ('Surman'
            # for 'Surname:' — the final letter eaten at the cell
            # rule): within edit distance 1 it is still the label,
            # and it must anchor — otherwise the field falls to the
            # zone scoop and a neighbouring column's row can join
            # the value. Exact anchors above win first.
            for i, n in enumerate(norms):
                if _edit_distance_le1(n, parts[0]):
                    return lab, i + 1
        if len(parts) >= 2:
            for i in range(0, len(norms) - len(parts)):
                j, k, skips = i, 0, 0
                while j < len(norms) and k < len(parts):
                    # A part also matches on a one-letter misread
                    # (parts of 4+ letters only): printed labels sit
                    # under rules and watermark ink, and a single
                    # eaten letter must not unanchor a label whose
                    # other words read exactly in sequence.
                    if norms[j] == parts[k] or (len(parts[k]) >= 4 and _edit_distance_le1(norms[j], parts[k])):
                        k += 1
                    else:
                        skips += 1
                        if skips > 1:
                            break
                    j += 1
                if k == len(parts):
                    return lab, j
    return None

def _value_from_tokens(field, tokens, mdy=False):
    """Interpret raw value tokens for a field. -> value string or None.
    mdy: the document's country prints numeric dates month-first
    (US, PH) — forwarded to parse_date_value for ambiguous dates."""
    if not tokens:
        return None
    joined = " ".join(tokens)
    if field in ("dob", "expiry"):
        d = parse_date_value(joined, mdy=mdy)
        if d:
            return d.isoformat()
        # date may be split across tokens like 12 / 08 / 1974
        d = parse_date_value(re.sub(r"\s+", "", joined), mdy=mdy)
        return d.isoformat() if d else None
    if field == "number":
        # Clean to the alphanumeric core first: a trailing '.' or a
        # neighbouring rule must not disqualify the very token that
        # carries the number (owner's real NIN slip, 2026-10-27: the
        # read token was '161394034780.' — the full stop failed the
        # old clean-token test, the extractor skipped the number and
        # harvested the word 'FIRST' from the next cell instead).
        cleaned = [re.sub(r"[^A-Z0-9]", "", str(tok or "").upper()) for tok in tokens]
        # Digit-bearing tokens are tried before pure-letter ones: a
        # document number virtually always carries a digit, while a
        # label line can carry plenty of plain words ('First Name:'
        # shares the NIN slip's number row).
        order = sorted(range(len(cleaned)),
                       key=lambda i: 0 if any(ch.isdigit() for ch in cleaned[i]) else 1)
        for i in order:
            cand = cleaned[i]
            if len(cand) >= 4 and re.fullmatch(r"[A-Z0-9]+", cand):
                # Grouped digit numbers (e.g. Aadhaar prints
                # "1234 5678 9012"): keep concatenating following
                # pure-digit tokens.
                if cand.isdigit():
                    j = i + 1
                    while j < len(cleaned) and cleaned[j].isdigit() and len(cand) + len(cleaned[j]) <= 20:
                        cand += cleaned[j]
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

_BAND_WORDS_CACHE = {}


def _band_name_items(image_path, tpl):
    """Word stream of the NAME BAND (the union of the surname and
    given-names zones, padded), re-read from the reading image at
    ~3x on a plain grey rendition. Measured (2026-10-27, digital
    NIN slip): the stylized name print over the coat-of-arms
    watermark contributes NO usable tokens to the full-page stream
    (its name zones come back empty), while the band crop at 3x
    reads the surname as one clean token and the given names as
    two; CLAHE / adaptive / Otsu renditions of the same band read
    WORSE, so the rescue uses plain grey. Returns (band_path,
    items) or (None, []). Cached per (image, zones)."""
    fields = (tpl or {}).get("fields") or {}
    zones = []
    for f in ("surname", "given_names"):
        z = ((fields.get(f) or {}).get("zone"))
        if z:
            zones.append(tuple(z))
    if not zones:
        return None, []
    return _band_items_for_zones(image_path, zones)


def _band_items_for_zones(image_path, zones):
    """Shared band reader: crop the union of `zones` (padded) from
    the reading image, upscale to ~900px tall, one plain-grey
    TSV read at psm 6. Returns (band_path, items) or (None, []).
    Cached per (image, zone-union)."""
    try:
        import os as _os
        x0 = max(0.0, min(z[0] for z in zones) - 0.03)
        x1 = min(1.0, max(z[2] for z in zones) + 0.04)
        y0 = max(0.0, min(z[1] for z in zones) - 0.02)
        y1 = min(1.0, max(z[3] for z in zones) + 0.03)
        key = (image_path, round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))
        if key in _BAND_WORDS_CACHE:
            return _BAND_WORDS_CACHE[key]
        import tempfile
        import cv2
        # _reading_image returns the reading rendition as a
        # GRAYSCALE ARRAY (not a path) — crop the band from it.
        img = _reading_image(image_path)
        if img is None:
            return None, []
        hh, ww = img.shape[:2]
        band = img[int(y0 * hh):int(y1 * hh), int(x0 * ww):int(x1 * ww)]
        if band.size == 0:
            return None, []
        factor = max(2, min(4, round(900 / max(1, band.shape[0]))))
        grey = cv2.resize(band, None, fx=factor, fy=factor,
                          interpolation=cv2.INTER_CUBIC)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        _os.close(fd)
        cv2.imwrite(tmp, grey)
        # Direct TSV read at psm 6 — vision.ocr_words routes through
        # the full-page reading machinery (warps, tiles), which
        # mangles a short wide strip and returned ZERO words for this
        # band (measured); the plain band read is what the offline
        # proof used.
        import shutil
        import subprocess as _sp
        words = []
        exe = shutil.which("tesseract")
        if exe:
            out = _sp.run([exe, tmp, "stdout", "--psm", "6", "tsv"],
                          capture_output=True, text=True, timeout=90,
                          env={**_os.environ, "OMP_THREAD_LIMIT": "1"})
            for row in (out.stdout or "").splitlines()[1:]:
                parts = row.split("\t")
                if len(parts) != 12 or parts[0] != "5" or not parts[11]:
                    continue
                try:
                    l, t = int(parts[6]), int(parts[7])
                    wpx, hpx = int(parts[8]), int(parts[9])
                    conf = float(parts[10])
                except Exception:
                    continue
                words.append({"text": parts[11], "conf": conf,
                              "box": (l, t, l + wpx, t + hpx)})
        bh, bw = grey.shape[:2]
        items = []
        for wd in words:
            bx = wd.get("box") or (0, 0, 0, 0)
            items.append({"text": wd.get("text", ""), "conf": wd.get("conf", 0),
                          "box": (bx[0] / bw, bx[1] / bh, bx[2] / bw, bx[3] / bh),
                          "cx": ((bx[0] + bx[2]) / 2.0) / bw,
                          "cy": ((bx[1] + bx[3]) / 2.0) / bh})
        # Dual-engine band read (unified reader, 2026-10-28): the
        # name band is ALSO read by PaddleOCR and its items merged
        # in — same fractional schema; a token the Tesseract band
        # read missed can now seed a band candidate, and candidates
        # still face _band_verify's corroboration before adoption.
        # Any engine failure leaves the Tesseract items untouched.
        try:
            from . import ocr2 as _OCR2
            _pitems = _OCR2.read_words_for_image_file(tmp)
            if _pitems:
                def _iou(a, b):
                    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
                    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
                    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
                    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
                    return inter / ua if ua > 0 else 0.0
                for _pi in _pitems:
                    _pn = "".join(c for c in _pi["text"].upper() if c.isalnum())
                    _hit = None
                    for _it in items:
                        if _iou(_it["box"], _pi["box"]) >= 0.4:
                            _hit = _it
                            break
                    if _hit is None:
                        items.append(_pi)
                    elif "".join(c for c in _hit["text"].upper() if c.isalnum()) == _pn:
                        _hit["conf"] = max(_hit["conf"], _pi["conf"])
        except Exception:
            pass
        if len(_BAND_WORDS_CACHE) >= 4:
            _BAND_WORDS_CACHE.clear()
        _BAND_WORDS_CACHE[key] = (tmp, items)
        return tmp, items
    except Exception:
        return None, []


def _band_verify(band_path, cand_items):
    """Corroboration for band-rescue candidates, on the BAND FILE
    itself. _verify_name_tokens cannot serve here: it re-reads
    token boxes from the page's READING image, and for a band
    strip that machinery warps/rescales the strip, so the boxes
    land on the wrong print and the gate vetoes TRUE tokens
    (measured 2026-10-27: the digital slip's cleanly-read surname
    was vetoed while a bracket fragment survived). Same recipe,
    correct substrate: tight-crop each token's box from the band
    image (±3px, 5x, psm 8, A-Z whitelist — _reread_token's own
    recipe); a non-empty disagreeing re-read vetoes; then the
    row-geometry chain around the first verified token drops
    off-row fragments."""
    import os as _os
    import shutil as _sh
    import subprocess as _sp
    import tempfile as _tf
    try:
        import cv2
        img = cv2.imread(band_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []
        exe = _sh.which("tesseract")
        if not exe:
            return []
        H, W = img.shape[:2]

        def _reread(box):
            # Pad scales with the token: the page verifier's fixed
            # ±3px was calibrated on full-page images; on the band
            # strip it crops so tight that tesseract merges
            # neighbouring print into the word (measured: the true
            # surname read back as 10 chars at ±3px, exactly itself
            # at ±8px). A quarter-height pad reproduces the page
            # recipe's proportions at band scale.
            _pad = max(6, int(0.25 * (box[3] - box[1]) * H))
            x0 = max(0, int(box[0] * W) - _pad); y0 = max(0, int(box[1] * H) - _pad)
            x1 = min(W, int(box[2] * W) + _pad); y1 = min(H, int(box[3] * H) + _pad)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                return ""
            big = cv2.resize(crop, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
            fd, tmp = _tf.mkstemp(suffix=".png"); _os.close(fd)
            try:
                cv2.imwrite(tmp, big)
                out = _sp.run([exe, tmp, "stdout", "--psm", "8",
                               "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
                              capture_output=True, text=True, timeout=30,
                              env={**_os.environ, "OMP_THREAD_LIMIT": "1"})
                return re.sub(r"[^A-Z]", "", (out.stdout or "").upper())
            finally:
                try: _os.unlink(tmp)
                except Exception: pass

        alpha = [it for it in cand_items
                 if len(re.sub(r"[^A-Za-z]", "", str(it["text"]))) >= 2]
        if not alpha:
            return []
        surv = []
        for it in alpha:
            want = re.sub(r"[^A-Z]", "", str(it["text"]).upper())
            got = _reread(it["box"])
            if got and want and got != want:
                continue
            surv.append((it, bool(got and got == want)))
        if not surv:
            return []
        ref_idx = next((i for i, (_it, v) in enumerate(surv) if v), 0)
        ref = surv[ref_idx][0]
        rh = max(1e-6, ref["box"][3] - ref["box"][1])
        rcy = (ref["box"][1] + ref["box"][3]) / 2.0
        kept = []
        for i, (it, _v) in enumerate(surv):
            h = it["box"][3] - it["box"][1]
            cy = (it["box"][1] + it["box"][3]) / 2.0
            if i < ref_idx:
                if h >= 0.6 * rh and abs(cy - rcy) <= 0.7 * rh:
                    kept.append(it)
                continue
            if i == ref_idx:
                kept.append(it)
                continue
            if 0.55 * rh <= h <= 1.7 * rh and abs(cy - rcy) <= 0.7 * rh:
                kept.append(it)
            else:
                break
        return kept
    except Exception:
        return []


def _recover_name_band(image_path, field, fspec, tpl, all_labels):
    """Name-band rescue: find this field's label line in the band
    stream and take its value — the tokens after the label on the
    same line, or the whole next line when the layout prints the
    value BELOW the label (the digital slip's arrangement, measured).
    The candidate passes the same corroboration gate as every other
    name source (_verify_name_tokens against the band rendition)."""
    band_path, items = _band_name_items(image_path, tpl)
    if not band_path or not items:
        return None
    labels = list((fspec or {}).get("labels") or [])
    if not labels:
        return None
    # group into lines by row proximity
    items = sorted(items, key=lambda it: (it["cy"], it["cx"]))
    lines = []
    for it in items:
        h = max(1e-6, it["box"][3] - it["box"][1])
        if lines and abs(it["cy"] - lines[-1][0]["cy"]) <= 0.9 * h:
            lines[-1].append(it)
        else:
            lines.append([it])
    for ln in lines:
        ln.sort(key=lambda it: it["cx"])
    label_norms = [_norm_word(x) for x in all_labels]

    def _band_span(ln):
        """Label span in a band line. The band's tight crop fuses
        bilingual labels into single tokens ('SURNAME/NOM' reads as
        one word; 'NAMES/PRENOMS' likewise) that the exact matcher
        cannot see — so after the standard span, accept a token
        sequence whose normalised forms carry the label's words as
        prefixes, any remainder being another known label word."""
        span = _label_span(ln, labels)
        if span:
            return span
        norms = [_norm_word(it["text"]) for it in ln]
        for lab in labels:
            words = [_norm_word(w) for w in str(lab).split() if _norm_word(w)]
            if not words:
                continue
            for i in range(len(ln)):
                j, wi, ok = i, 0, True
                while wi < len(words):
                    if j >= len(ln):
                        ok = False
                        break
                    tok = norms[j]
                    if tok == words[wi]:
                        j += 1
                        wi += 1
                    elif tok.startswith(words[wi]) and \
                            tok[len(words[wi]):] in label_norms:
                        j += 1
                        wi += 1
                    else:
                        ok = False
                        break
                if ok:
                    return (i, j)
        return None

    def _yields(cand_items):
        if not cand_items:
            return None
        kept = _band_verify(band_path, cand_items)
        cand = _value_from_tokens(field, [it["text"] for it in kept])
        if cand and max((len(t) for t in re.findall(r"[A-Za-z]+", cand)), default=0) >= 3:
            return cand
        return None

    for li, ln in enumerate(lines):
        span = _band_span(ln)
        if not span:
            continue
        same_line = [it for it in ln[span[1]:]
                     if _norm_word(it["text"]) not in label_norms]
        got = _yields(same_line)
        if got:
            return got
        if li + 1 < len(lines):
            next_line = [it for it in lines[li + 1]
                         if _norm_word(it["text"]) not in label_norms
                         and not _band_span([it])]
            got = _yields(next_line)
            if got:
                return got
    return None


def _recover_dob_band(image_path, fspec, tpl, all_labels):
    """Date-band rescue for a printed DOB the full-page stream
    lost (the digital NIN slip's date row sits in the same
    watermark field as its names). Crops the DOB zone alone,
    finds the field's label line (fused bilingual labels handled
    with the same prefix rule as the name band), and assembles
    the date from the tokens after the label or on the next
    line through the ordinary date parser. The label anchor +
    a fully parseable, sane date is the gate — stray digit
    groups elsewhere never qualify."""
    try:
        zone = ((fspec or {}).get("zone"))
        if not zone:
            return None
        band_path, items = _band_items_for_zones(image_path, [tuple(zone)])
        if not band_path or not items:
            return None
        labels = list((fspec or {}).get("labels") or [])
        if not labels:
            return None
        items = sorted(items, key=lambda it: (it["cy"], it["cx"]))
        lines = []
        for it in items:
            h = max(1e-6, it["box"][3] - it["box"][1])
            if lines and abs(it["cy"] - lines[-1][0]["cy"]) <= 0.9 * h:
                lines[-1].append(it)
            else:
                lines.append([it])
        for ln in lines:
            ln.sort(key=lambda it: it["cx"])
        label_norms = [_norm_word(x) for x in all_labels]

        def _span(ln):
            span = _label_span(ln, labels)
            if span:
                return span
            norms = [_norm_word(it["text"]) for it in ln]
            for lab in labels:
                words = [_norm_word(w) for w in str(lab).split() if _norm_word(w)]
                if not words:
                    continue
                for i in range(len(ln)):
                    j, wi, ok = i, 0, True
                    while wi < len(words):
                        if j >= len(ln):
                            ok = False
                            break
                        tok = norms[j]
                        if tok == words[wi] or (tok.startswith(words[wi])
                                                and tok[len(words[wi]):] in label_norms):
                            j += 1
                            wi += 1
                        else:
                            ok = False
                            break
                    if ok:
                        return (i, j)
            return None

        from datetime import date as _date
        for li, ln in enumerate(lines):
            span = _span(ln)
            if not span:
                continue
            cand_sets = [[it for it in ln[span[1]:]
                          if _norm_word(it["text"]) not in label_norms]]
            if li + 1 < len(lines):
                cand_sets.append([it for it in lines[li + 1]
                                  if _norm_word(it["text"]) not in label_norms
                                  and not _span([it])])
            for cand in cand_sets:
                if not cand:
                    continue
                val = _value_from_tokens("dob", [it["text"] for it in cand])
                if not val:
                    continue
                try:
                    d = _date.fromisoformat(str(val)[:10])
                except Exception:
                    continue
                if _date(1900, 1, 1) <= d <= _date.today():
                    return val
        return None
    except Exception:
        return None


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
    number.

    The matrix reads every colour channel (a coloured watermark or
    stamp is bright in its own channel, so each channel's reads fail
    differently and their agreement means something), on a crop the
    value's own anchor token bounds. When the string vote cannot
    decide but the primary partial is over-length by one or two
    digits — junk fused to one end of a faithful read — a
    containment stage adjudicates the partial's own windows: a read
    that contains one window but not its rival began or ended inside
    the true number, which only the true window explains."""
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
        # Digit anchors: tokens the primary read produced inside the
        # zone that carry the number's digits (fully or partly). The
        # centre must sit INSIDE the zone proper — a token in the
        # margin above the zone is the NEIGHBOURING row's print (the
        # slip's tracking ID, whose long digit run otherwise hijacks
        # the crop to the wrong row, measured 2026-10-27).
        anchor_rows = []
        for w in (words or []):
            box = w.get("box") or (0, 0, 0, 0)
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            if not (zone[0] <= cx <= zone[2] and zone[1] <= cy <= zone[3]):
                continue
            digs = re.sub(r"\D", "", _normalize_numeric(str(w.get("text") or "")))
            if len(digs) >= 4 and (not pd or digs in pd or pd.startswith(digs[:6]) or digs[:6] in pd):
                anchors.append(box)
                anchor_rows.append((box, digs))
        frac = None
        if label_box is not None:
            lh = label_box[3] - label_box[1]
            lcy = (label_box[1] + label_box[3]) / 2.0
            frac = [min(1.0, label_box[2] + 0.004), max(0.0, lcy - 1.1 * lh),
                    min(1.0, label_box[2] + 0.36), min(1.0, lcy + 1.1 * lh)]
            # Refine with the digit anchor(s) on the label's own row:
            # the label frac's fixed +0.36 width swallows the NEXT
            # cell (on the NIN slip, 'First Name:' and its value),
            # whose letterforms bleed junk digits into the reads, and
            # the label-height band can clip the value's taller
            # glyphs. The anchor token IS the value's ink: bound the
            # crop to its span (plus a pitch of slack), and let the
            # band cover its full height.
            row = [(b, d) for (b, d) in anchor_rows
                   if abs((b[1] + b[3]) / 2.0 - lcy) <= 1.5 * lh]
            if row:
                ax0 = min(b[0] for b, _ in row); ax1 = max(b[2] for b, _ in row)
                ay0 = min(b[1] for b, _ in row); ay1 = max(b[3] for b, _ in row)
                ah = ay1 - ay0
                widest = max(row, key=lambda bd: len(bd[1]))
                pitch = (widest[0][2] - widest[0][0]) / max(1, len(widest[1]))
                frac[0] = max(frac[0], ax0 - 1.0 * pitch)
                frac[2] = min(frac[2], ax1 + 1.2 * pitch)
                frac[1] = min(frac[1], max(0.0, ay0 - 0.1 * ah))
                frac[3] = max(frac[3], min(1.0, ay1 + 0.1 * ah))
            frac = tuple(frac)
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
        # ---- the read matrix: independent optical views ----
        # Every colour channel is a different physical view of the
        # ink: a green watermark is bright in the green channel and
        # dark in the others, so channel reads fail DIFFERENTLY —
        # which is what makes their agreement meaningful. (Owner's
        # slip, 2026-10-27: the green-channel plain reads were the
        # only ones that carried the number's last digit past the
        # green stamp arc printed over it; grey/Otsu reads merged
        # the arc into the glyph and voted it a 2.)
        def _run_matrix(crop_img, scales=(3, 6)):
            """The channel x binarisation x scale x psm read matrix
            over one crop; returns (reads, votes)."""
            chans = {"grey": cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)}
            _cb, _cg, _cr = cv2.split(crop_img)
            chans.update({"blue": _cb, "green": _cg, "red": _cr})
            # The reads are independent subprocess calls; run them two
            # at a time (this host has 2 cores) and consume the results
            # IN JOB ORDER, so the vote arithmetic is byte-identical to
            # the sequential matrix — only the wall time changes (the
            # sequential 64-read matrix pushed a full verification past
            # the flow client's 60s budget, measured 2026-10-27).
            jobs = []  # (family, array, psm)
            for cname, base in chans.items():
                # Scales 3 and 6 only: the middle scales resample the
                # same segmentation and their reads correlate with the
                # extremes; the diversity that decides outcomes is
                # channel x binarisation x segmentation mode. Halving
                # the matrix keeps every family at 4 reads while the
                # wall time fits the flow's time budget.
                for scale in scales:
                    up = cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                    variants = (("plain", up),
                                ("otsu", cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]))
                    for tname, arr in variants:
                        for psm in ("7", "6"):
                            jobs.append((f"{cname}-{tname}", arr, psm))

            def _one_read(job):
                fam, arr, psm = job
                fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
                try:
                    cv2.imwrite(tmp, arr)
                    out = subprocess.run([exe, tmp, "stdout", "--psm", psm,
                                          "-c", "tessedit_char_whitelist=0123456789"],
                                         capture_output=True, text=True, timeout=60, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
                    return fam, re.sub(r"\D", "", out.stdout or "")
                except Exception:
                    return fam, ""
                finally:
                    try: os.unlink(tmp)
                    except Exception: pass

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(_one_read, jobs))
            reads = []  # (family, digits)
            votes = {}
            exact = {}
            for fam, d in results:
                if not d:
                    continue
                reads.append((fam, d))
                if len(d) == want:
                    votes[d] = votes.get(d, 0) + 1
                    exact[d] = exact.get(d, 0) + 1
                elif want < len(d) <= want + 4:
                    # The value's digits with junk bled in from a
                    # neighbouring column (measured: the true number as
                    # the first 11 of a 14-digit read). Every window
                    # votes; only a candidate repeated across independent
                    # variants can clear the decisive-vote bar below.
                    for k in range(0, len(d) - want + 1):
                        w = d[k:k + want]
                        votes[w] = votes.get(w, 0) + 1
            return reads, votes, exact

        def _banded():
            # No landmark survived in the word stream (no label
            # token, no digit anchor): the value's line inside
            # the zone crop is unknown, and the single-line reads
            # choke on a multi-line crop — neighbouring rows'
            # digits mix into the string (measured on the
            # owner's full-resolution upload: the zone crop is
            # plainly legible, the matrix read nothing). Probe
            # three overlapping horizontal bands with one cheap
            # read each; the band(s) carrying the digit mass
            # get the full matrix, pooled.
            reads, votes, exact = [], {}, {}
            _ch = crop.shape[0]
            _scored = []
            for _f0, _f1 in ((0.0, 0.45), (0.28, 0.73), (0.55, 1.0)):
                _band = crop[int(_f0 * _ch):int(_f1 * _ch)]
                if _band.size == 0:
                    continue
                _grey = cv2.cvtColor(_band, cv2.COLOR_BGR2GRAY)
                _up = cv2.resize(_grey, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                _fd, _tmp = tempfile.mkstemp(suffix=".png"); os.close(_fd)
                _boxes = []
                try:
                    cv2.imwrite(_tmp, _up)
                    _out = subprocess.run([exe, _tmp, "stdout", "--psm", "6", "tsv",
                                          "-c", "tessedit_char_whitelist=0123456789"],
                                         capture_output=True, text=True, timeout=60, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
                    _d = ""
                    for _row in (_out.stdout or "").splitlines()[1:]:
                        _p = _row.split("\t")
                        if len(_p) != 12 or _p[0] != "5":
                            continue
                        _digs = re.sub(r"\D", "", _p[11])
                        if not _digs:
                            continue
                        _d += _digs
                        try:
                            _boxes.append((float(_p[6]), float(_p[7]), float(_p[8]), float(_p[9]), len(_digs)))
                        except Exception:
                            pass
                except Exception:
                    _d = ""
                finally:
                    try: os.unlink(_tmp)
                    except Exception: pass
                # Refine the band to its digit cluster before the
                # matrix: a band still carries the label and parts
                # of the rows above/below, and the over-length
                # reads' window votes split evenly between the true
                # window and its shift (measured: the probe read
                # the number perfectly, the band matrix tied). The
                # cluster crop is the value's own ink, like the
                # anchor-refined crop on the informed path.
                if _boxes:
                    _bh, _bw = _band.shape[:2]
                    _med_h = sorted(b[3] for b in _boxes)[len(_boxes) // 2] / 4.0
                    _best_row = None
                    for _b in _boxes:
                        _cy = (_b[1] + _b[3] / 2.0) / 4.0
                        _row = [o for o in _boxes if abs((o[1] + o[3] / 2.0) / 4.0 - _cy) <= 0.8 * _med_h]
                        _mass = sum(o[4] for o in _row)
                        if _best_row is None or _mass > _best_row[0]:
                            _best_row = (_mass, _row)
                    if _best_row and _best_row[0] >= 6:
                        _row = _best_row[1]
                        _x0 = max(0, int(min(b[0] for b in _row) / 4.0 - _med_h))
                        _x1 = min(_bw, int(max((b[0] + b[2]) for b in _row) / 4.0 + _med_h))
                        _y0 = max(0, int(min(b[1] for b in _row) / 4.0 - 0.3 * _med_h))
                        _y1 = min(_bh, int(max((b[1] + b[3]) for b in _row) / 4.0 + 0.3 * _med_h))
                        if _x1 - _x0 >= 20 and _y1 - _y0 >= 8:
                            _band = _band[_y0:_y1, _x0:_x1]
                _scored.append((len(_d), _band))
            _scored.sort(key=lambda t: -t[0])
            # A band whose digit mass doubles the runner-up is the
            # value's row — running the matrix on a second band too
            # only burns the time budget (measured on a junk upload
            # whose MRZ band out-massed everything: two bands cost
            # ~70s for the same honest not-found).
            if len(_scored) >= 2 and _scored[0][0] >= 6 and _scored[0][0] >= 2 * max(_scored[1][0], 1):
                _chosen = [_scored[0][1]]
            else:
                _chosen = [_b for (_n, _b) in _scored if _n >= 6][:2]
            if not _chosen and _scored:
                _chosen = [_scored[0][1]]
            # Read budget across bands: one band gets the wider
            # scale set; two bands share the leaner set, so the
            # fallback's total matrix cost stays bounded.
            _scales = (3, 4, 6) if len(_chosen) == 1 else (3, 6)
            for _band in _chosen:
                _r2, _v2, _e2 = _run_matrix(_band, scales=_scales)
                reads.extend(_r2)
                for _k, _v in _v2.items():
                    votes[_k] = votes.get(_k, 0) + _v
                for _k, _v in _e2.items():
                    exact[_k] = exact.get(_k, 0) + _v
            return reads, votes, exact

        informed = label_box is not None or bool(anchors)
        if informed:
            reads, votes, exact = _run_matrix(crop)
            if not votes:
                # The landmark crop read nothing votable —
                # the landmark was a neighbouring row's print
                # after all. Banded sweep as the last resort.
                _r2, _v2, _e2 = _banded()
                reads.extend(_r2)
                for _k, _v in _v2.items():
                    votes[_k] = votes.get(_k, 0) + _v
                for _k, _v in _e2.items():
                    exact[_k] = exact.get(_k, 0) + _v
        else:
            reads, votes, exact = _banded()
        ranked = sorted(votes.items(), key=lambda kv: -kv[1])
        if ranked:
            best, best_votes = ranked[0]
            runner = ranked[1][1] if len(ranked) > 1 else 0
            if best_votes >= 3 and best_votes >= 2 * max(runner, 1):
                if len(pd) >= 6:
                    agree = sum(1 for a, b in zip(pd, best) if a == b)
                    if agree < 0.75 * min(len(pd), want):
                        return None
                return best
        # Exact-length reads are the strongest evidence class: a
        # complete independent read of the whole string carries no
        # window ambiguity, while a shifted rival's combined votes
        # are mostly window spill from over-length reads (measured
        # on the owner's full-resolution upload: combined 5-3, the
        # rival's votes nearly all spill). A decisive exact leader
        # that also leads the combined pool wins.
        eranked = sorted(exact.items(), key=lambda kv: -kv[1])
        if eranked:
            ebest, evotes = eranked[0]
            erunner = eranked[1][1] if len(eranked) > 1 else 0
            if evotes >= 3 and evotes >= 2 * max(erunner, 1) and votes.get(ebest, 0) >= max(votes.values()):
                if len(pd) >= 6:
                    agree = sum(1 for a2, b2 in zip(pd, ebest) if a2 == b2)
                    if agree < 0.75 * min(len(pd), want):
                        return None
                return ebest
        # ---- containment adjudication (over-length partial) ----
        # The primary read produced MORE digits than the format
        # holds — junk fused to ONE end of a faithfully read number
        # (the slip's primary read is the true 11 digits plus a
        # trailing '0' the stamp arc contributed). The candidates
        # are the partial's own windows; the matrix reads decide
        # WHICH end is junk: a read that contains one window but not
        # its rival must have begun or ended inside the true number,
        # which only the true window can explain. Adopted only on
        # asymmetric evidence: the winner is contained in strictly
        # more independent reads than every rival, in at least two
        # rendition families (or twice exclusively), with at least
        # one read that contains it and no rival — and it must still
        # broadly agree with the string-vote leader when one exists.
        if want + 1 <= len(pd) <= want + 2:
            cands = []
            for k in range(0, len(pd) - want + 1):
                w = pd[k:k + want]
                if w not in cands:
                    cands.append(w)
            if len(cands) >= 2:
                pool = [(fam, d) for fam, d in reads if len(d) >= want]
                for b, digs in anchor_rows:
                    if len(digs) >= want:
                        pool.append(("primary", digs))
                scored = []
                for cand in cands:
                    containing = [(fam, d) for fam, d in pool if cand in d]
                    exclusive = [(fam, d) for fam, d in containing
                                 if not any(other != cand and other in d for other in cands)]
                    fams = {fam for fam, _ in containing}
                    scored.append((cand, len(containing), len(exclusive), fams))
                scored.sort(key=lambda s: -s[1])
                cand, n_cont, n_excl, fams = scored[0]
                runner_cont = scored[1][1] if len(scored) > 1 else 0
                if n_cont >= 3 and n_cont > runner_cont and n_excl >= 1 and \
                        (len(fams) >= 2 or n_excl >= 2):
                    if ranked and ranked[0][1] >= 3:
                        leader = ranked[0][0]
                        agree = sum(1 for a, b in zip(leader, cand) if a == b)
                        if agree < want - 2:
                            return None
                    return cand
        return None
    except Exception:
        return None
        return None


_READING_CACHE = {}


def _reading_image(image_path):
    """The READING image (warped rendition when framing found the
    document, else the image itself) as a grayscale array, cached
    per file version: the name-token verification re-reads several
    boxes from the same image, and re-running the framing analysis
    and warp for every token multiplied the extraction cost."""
    try:
        import os
        import cv2
        from . import vision as VISION
        st = os.stat(image_path)
        key = (image_path, st.st_mtime_ns, st.st_size)
        if key not in _READING_CACHE:
            if len(_READING_CACHE) > 4:
                _READING_CACHE.clear()
            rpath, _warp = VISION._reading_path(image_path)
            _READING_CACHE[key] = cv2.imread(rpath, cv2.IMREAD_GRAYSCALE)
        return _READING_CACHE[key]
    except Exception:
        return None


def _reread_token(image_path, box):
    """Tight-crop single-word re-read of one token's box (fractions
    of the READING image — the same space ocr_words reports).
    Returns the cleaned A-Z string the re-read produced, or '' when
    it produced nothing (inconclusive, never a veto by itself)."""
    try:
        import shutil, subprocess, tempfile, os
        import cv2
        exe = shutil.which("tesseract")
        if not exe or not image_path:
            return ""
        img = _reading_image(image_path)
        if img is None:
            return ""
        H, W = img.shape[:2]
        x0 = max(0, int(box[0] * W) - 3); y0 = max(0, int(box[1] * H) - 3)
        x1 = min(W, int(box[2] * W) + 3); y1 = min(H, int(box[3] * H) + 3)
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return ""
        big = cv2.resize(crop, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
        fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd)
        try:
            cv2.imwrite(tmp, big)
            out = subprocess.run([exe, tmp, "stdout", "--psm", "8",
                                  "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
                                 capture_output=True, text=True, timeout=30, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            return re.sub(r"[^A-Z]", "", (out.stdout or "").upper())
        finally:
            try: os.unlink(tmp)
            except Exception: pass
    except Exception:
        return ""


def _verify_name_tokens(image_path, items):
    """Corroboration gate for name-value tokens harvested from a
    label line. Watermark ghost letters and neighbouring-row print
    bleed into the value's row band as extra alpha tokens (measured
    on the owner's slip at BOTH resolutions: 'AYANSIPE EMSS AS',
    'ZENAS NY SS', 'AYANSIPE SA') — same band, sometimes HIGHER
    confidence than the real value, so neither the column-gap rule
    nor confidence can separate them. Two measured stages can:

      * re-read agreement — every token's own box, cropped tight
        and re-read as a single word, must not CONTRADICT the
        token: ghost fragments are pieces of larger letters and
        re-read as something else ('NY'->'YQ', 'EMSS'->'SS'), while
        every real value token measured re-reads verbatim. An
        EMPTY re-read is inconclusive and never vetoes;
      * row geometry around the first exactly-verified token —
        the value's tokens share one printed row: heights within
        [0.55, 1.7]x of the reference and centres within 0.7 of
        its height, the chain stopping at the first violator
        (ghost letters are ~2x the value's height; the address
        header sits a full row up). Unverified leaders shorter
        than 0.6x the reference are sliver fragments and drop."""
    alpha = [it for it in items if re.search(r"[A-Za-z]", str(it["text"]))
             and (it["box"][3] - it["box"][1]) >= 0.004 and (it["box"][2] - it["box"][0]) >= 0.004]
    if not alpha:
        return items
    # Stage 1: an independent tight-crop re-read of every token's
    # own box. A NON-EMPTY re-read that disagrees vetoes the token
    # (ghost fragments re-read as other letters); an empty one is
    # inconclusive and never vetoes. If every token is vetoed the
    # unfiltered list stands — a verification hiccup must not
    # manufacture a not-found.
    surv = []  # (item, re-read agreed exactly)
    for it in alpha:
        want = re.sub(r"[^A-Z]", "", str(it["text"]).upper())
        got = _reread_token(image_path, it["box"])
        if got and want and got != want:
            continue
        surv.append((it, bool(got and got == want)))
    if not surv:
        return alpha
    # Stage 2: row geometry around the first EXACTLY-verified
    # token (every real value token measured re-reads verbatim, so
    # it is the trustworthy row reference). Unverified leaders
    # shorter than 0.6x its height are sliver fragments of a
    # neighbouring row and drop; full-height unverified leaders
    # stay — a faint real first token is never sacrificed to a
    # later token's cleaner read. Past the reference, the chain
    # stops at the first token off the row's height/centre band.
    ref_idx = next((i for i, (_it, v) in enumerate(surv) if v), 0)
    ref = surv[ref_idx][0]
    rh = max(1e-6, ref["box"][3] - ref["box"][1])
    rcy = (ref["box"][1] + ref["box"][3]) / 2.0
    kept = []
    for i, (it, _v) in enumerate(surv):
        h = it["box"][3] - it["box"][1]
        cy = (it["box"][1] + it["box"][3]) / 2.0
        if i < ref_idx:
            if h >= 0.6 * rh and abs(cy - rcy) <= 0.7 * rh:
                kept.append(it)
            continue
        if i > ref_idx and not (0.55 * rh <= h <= 1.7 * rh and abs(cy - rcy) <= 0.7 * rh):
            break
        kept.append(it)
    return kept if kept else [it for it, _v in surv]


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

def _triad_found(fields, tpl):
    """How many of the template's identity triad (surname,
    given_names, number — those it defines) the extraction actually
    FOUND. A name value counts only with a token of 3+ letters (a
    lone 'A' from a neighbouring column is not a found surname); a
    number counts when a value is present."""
    n = 0
    for f in ("surname", "given_names", "number"):
        if f not in tpl["fields"]:
            continue
        v = (fields.get(f) or {}).get("value")
        if not v:
            continue
        if f == "number" or any(len(t) >= 3 for t in re.split(r"[^A-Za-z]+", str(v)) if t):
            n += 1
    return n


def extract_fields(image_path, country, kind, ocr_text="", words=None, ocr_texts=None):
    """Template-guided extraction with one tile-rescue retry.

    A page can read RICH in total words — background junk inflates
    the count past the tile gate — while its value rows are blind
    (measured on the owner's full-resolution slip upload,
    2026-10-27: 163 words, the surname/first-name/number rows
    garbled or missing, extraction surname 'A'). No word-count
    signal can see that shape, so when this pass leaves any of the
    template's identity triad unfound, the word stream is re-read
    WITH the quadrant tiles forced and the extraction re-run once;
    the retry is adopted when it finds at least as much of the
    triad (its stream is a superset read of the same page, judged
    by the same corroboration gates)."""
    base_words = words
    if base_words is None and image_path:
        try:
            from . import vision as VISION
            base_words = VISION.ocr_words(image_path)
        except Exception:
            base_words = None
    result = _extract_fields_pass(image_path, country, kind, ocr_text=ocr_text,
                                  words=base_words, ocr_texts=ocr_texts)
    if words is not None or not image_path:
        return result
    tpl = get_field_template((country or "").upper(), kind)
    if tpl is None:
        return result
    fields = result["findings"]["fields"]
    triad_max = sum(1 for f in ("surname", "given_names", "number") if f in tpl["fields"])
    if _triad_found(fields, tpl) >= triad_max:
        return result
    if base_words is not None and len(base_words) < 25:
        # A near-empty page is not a blind document — it is not a
        # document at all; the rescue reads cannot manufacture
        # fields from it, and doubling the extraction cost on junk
        # uploads breaks the flow's time budget (measured: a
        # 12-word synthetic card's extraction tripled).
        return result
    try:
        from . import vision as VISION
        rich = VISION.ocr_words(image_path, force_tiles=True)
    except Exception:
        return result
    if not rich:
        return result
    retry = _extract_fields_pass(image_path, country, kind, ocr_text=ocr_text,
                                 words=rich, ocr_texts=ocr_texts)
    if _triad_found(retry["findings"]["fields"], tpl) >= _triad_found(fields, tpl):
        return retry
    return result


def _recover_vin(lines, text_lines):
    """Strongest VIN-shaped run on the card: a maximal run of
    adjacent alphanumeric tokens (word lines first, then the raw
    pass texts) whose joined form is 15-24 chars with >= 8 digits
    and >= 1 letter. Returns the joined candidate or None."""
    def _best_from(token_rows):
        best = None  # (digits, trimmed_rank, joined)
        for toks in token_rows:
            run = []
            def flush(run):
                nonlocal best
                if not run:
                    return
                # The run can open with the field's own LABEL misread
                # and fused in ('VIN' -> 'YIN' chained straight into
                # the number groups — measured on the genuine card: a
                # 22-char candidate whose first 3 chars were the
                # label, the VIN itself 19). Judge the run both ways;
                # on equal digits the label-trimmed form wins.
                variants = [(run, 0)]
                first = re.sub(r"[^A-Z0-9]", "", str(run[0]).upper())
                if first in ("VIN", "YIN") and len(run) > 1:
                    variants.append((run[1:], 1))
                for variant, trimmed_rank in variants:
                    joined = re.sub(r"[^A-Z0-9]", "", "".join(variant).upper())
                    digs = sum(c.isdigit() for c in joined)
                    if 15 <= len(joined) <= 24 and digs >= 8 and \
                            any(c.isalpha() for c in joined):
                        cand = (digs, trimmed_rank, joined)
                        if best is None or cand[0] > best[0] or \
                                (cand[0] == best[0] and cand[1] > best[1]) or \
                                (cand[0] == best[0] and cand[1] == best[1]
                                 and len(joined) > len(best[2])):
                            best = cand
            for t in toks:
                cleaned = re.sub(r"[^A-Z0-9]", "", str(t).upper())
                if len(cleaned) >= 2:
                    run.append(str(t))
                else:
                    flush(run); run = []
            flush(run)
        return best[2] if best else None
    rows = []
    for ln in lines or []:
        try:
            rows.append([it["text"] for it in ln])
        except Exception:
            continue
    hit = _best_from(rows)
    if not hit:
        hit = _best_from([str(l).split() for l in (text_lines or [])])
    if hit and len(hit) > 21 and hit[:3] in ("VIN", "YIN"):
        # Over-length with the label fused INTO the leading token
        # (not a separate token the variant judge above can drop):
        # the dossier's VIN is ~19 chars, so a 22-char candidate
        # opening with the misread label carries the label's glyphs
        # inside its first group. Strip the label prefix; the digits
        # — the identity-critical part — are untouched either way.
        rest = hit[3:]
        if len(rest) >= 15 and sum(c.isdigit() for c in rest) >= 8:
            return rest
    return hit

def _extract_fields_pass(image_path, country, kind, ocr_text="", words=None, ocr_texts=None):
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
    _mdy = country in ("US", "PH")
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
    label_parts = {_norm_word(w) for lab in all_labels for w in lab.split()
                   if len(_norm_word(w)) >= 4}
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
                    # Corroboration gate: watermark ghost letters
                    # and neighbouring-row print bleed into the
                    # value's row band as extra tokens the gap rule
                    # cannot see (they chain across in <5% steps).
                    items_after = _verify_name_tokens(image_path, trimmed)
                cand = _value_from_tokens(field, [it["text"] for it in items_after], mdy=_mdy)
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
                    valid_cands.append((labels.index(lab_hit), li, cand,
                                        items_after[0]["box"][0] if items_after else None))
        if valid_cands:
            valid_cands.sort(key=lambda t: (t[0], t[1]))
            if field == "given_names":
                # A person printed with separate FIRST NAME and
                # MIDDLE NAME cells carries BOTH as their given
                # names (the NIN slip prints exactly that): join the
                # best value of each DISTINCT label in the spec's
                # preference order. A second label that merely
                # re-reads the same value adds nothing — exact
                # duplicates and substrings merge instead of joining.
                per_label = {}
                for rank, _li, cand, _x0 in valid_cands:
                    per_label.setdefault(rank, cand)
                if len(per_label) >= 2:
                    parts = []
                    for rank in sorted(per_label):
                        cand = per_label[rank]
                        merged = False
                        for k, p in enumerate(parts):
                            if cand == p or cand in p:
                                merged = True
                                break
                            if p in cand:
                                parts[k] = cand
                                merged = True
                                break
                        if not merged:
                            parts.append(cand)
                    if len(parts) >= 2 and sum(len(p.split()) for p in parts) <= 4:
                        value, source = " ".join(parts), "label"
            if value is None:
                value, source = valid_cands[0][2], "label"
            if field == "given_names" and value is not None:
                # Orphan-row harvest: a sibling name row whose LABEL
                # was destroyed in the read (a watermark letter or
                # the lamination crease over the label text) still
                # prints its VALUE in the same column. When such a
                # row exists inside the field's zone — no recognisable
                # label of ANY field on the line, its value tokens
                # aligned with the anchored value's column, purely
                # alphabetic — it belongs to the given names (the
                # owner's slip: 'Middle Name:' garbled beyond label
                # matching while 'OLATUNDE' read clean). Only the
                # nearest such line may join, and never with tokens
                # the anchored value already carries.
                contrib = [(t[1], t[3]) for t in valid_cands
                           if t[2] and t[2] in value and t[3] is not None]
                if contrib and spec.get("zone"):
                    used = {li for li, _x in contrib}
                    anchor_x0 = min(x for _li, x in contrib)
                    z = spec["zone"]
                    best = None  # (line distance, line idx, orphan value)
                    for li, ln in enumerate(lines):
                        if li in used:
                            continue
                        if any(_label_span(ln, [lab]) for lab in all_labels):
                            continue
                        oitems = [it for it in ln
                                  if z[0] <= it["cx"] <= z[2] and z[1] <= it["cy"] <= z[3]
                                  and it["box"][0] >= anchor_x0 - 0.02
                                  and len(re.sub(r"[^A-Za-z]", "", it["text"])) >= 3
                                  and not any(c.isdigit() for c in it["text"])]
                        if not oitems:
                            continue
                        toks = [it["text"] for it in _verify_name_tokens(image_path, oitems)]
                        if not toks:
                            continue
                        ov = _value_from_tokens("given_names", toks)
                        if ov and not any(tok in value.split() for tok in ov.split()):
                            dist = min(abs(li - u) for u in used)
                            if best is None or dist < best[0]:
                                best = (dist, li, ov)
                    if best is not None:
                        _d, oli, ov = best
                        if oli < min(used):
                            value = ov + " " + value
                        else:
                            value = value + " " + ov
        if value is None and fallback is not None:
            value, source = fallback, "label"
        # 2) zone read
        if value is None and spec.get("zone") and spec["zone"] != (0.0, 0.0, 0.0, 0.0):
            z = spec["zone"]
            if field in ("surname", "given_names"):
                # Per-line and corroborated, like the label harvest:
                # a zone spans several printed rows, and scooping
                # its tokens flat interleaves the rows and lets
                # watermark fragments ride along (measured on the
                # owner's high-res slip: 'ZENAS NY SS' — the value
                # plus ghost fragments, the real middle-name value
                # cut off by the token cap). Read each in-zone line
                # on its own, verify its tokens, and join the lines
                # in reading order.
                parts = []
                for ln in lines:
                    zitems = [it for it in ln
                              if z[0] <= it["cx"] <= z[2] and z[1] <= it["cy"] <= z[3]
                              and not _label_span([it], labels)
                              and _norm_word(it["text"]) not in [_norm_word(x) for x in all_labels]]
                    if not zitems:
                        continue
                    # A line whose label was destroyed can still
                    # open with the label's readable FRAGMENT
                    # ('lame:' — the tail of 'Middle Name:'), which
                    # is debris, never a value token: drop a leading
                    # token within one letter of any label word when
                    # a value token follows it on the line.
                    if len(zitems) > 1 and any(_edit_distance_le1(_norm_word(zitems[0]["text"]), p)
                                               for p in label_parts):
                        zitems = zitems[1:]
                    kept = _verify_name_tokens(image_path, zitems)
                    cand = _value_from_tokens(field, [it["text"] for it in kept], mdy=_mdy)
                    if not cand:
                        continue
                    merged = False
                    for k, p in enumerate(parts):
                        if cand == p or cand in p:
                            merged = True
                            break
                        if p in cand:
                            parts[k] = cand
                            merged = True
                            break
                    if not merged:
                        parts.append(cand)
                    if field == "surname":
                        # A surname is ONE printed row; a second
                        # in-zone line is a neighbouring column's
                        # row (the slip's address column intersects
                        # the surname zone and joined its first word
                        # onto the value, measured 2026-10-27).
                        break
                if parts and sum(len(p.split()) for p in parts) <= 4:
                    value, source = " ".join(parts), "zone"
                toks = None
            else:
                toks = []
                for ln in lines:
                    for it in ln:
                        if z[0] <= it["cx"] <= z[2] and z[1] <= it["cy"] <= z[3]:
                            if _label_span([it], labels) or _norm_word(it["text"]) in [_norm_word(x) for x in all_labels]:
                                continue
                            toks.append(it["text"])
            if toks is not None:
                if field == "number":
                    # Prefer a DIGIT-BEARING token that passes the
                    # type's own format validator, then any
                    # digit-bearing token — a zone also contains
                    # title words and surnames, which generic
                    # patterns would otherwise happily accept.
                    for tok in toks:
                        cleaned_tok = re.sub(r"[^A-Z0-9]", "", str(tok or "").upper())
                        if any(ch.isdigit() for ch in cleaned_tok) and validate_number(country, kind, cleaned_tok) is True:
                            value = cleaned_tok
                            break
                    if value is None:
                        digit_toks = [t for t in toks if any(ch.isdigit() for ch in t)]
                        value = _value_from_tokens(field, digit_toks, mdy=_mdy)
                else:
                    value = _value_from_tokens(field, toks, mdy=_mdy)
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
                        cand = _value_from_tokens(field, raw[m.end():].split(), mdy=_mdy)
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
        # 3c) name-band rescue (surname / given_names only): the
        # resolved name is missing or a fragment (no alpha token of
        # 3+ letters — watermark-era stylized print can vanish from
        # the full-page stream entirely) while the template carries
        # name zones. The band re-read (see _band_name_items) is
        # adopted only when it is strictly stronger: a longer
        # longest-alpha-token than the current value's.
        if field in ("surname", "given_names"):
            def _longest_alpha(v):
                toks = [t for t in re.findall(r"[A-Za-z]+", str(v or ""))]
                return max((len(t) for t in toks), default=0)
            if _longest_alpha(value) < 3:
                band_val = _recover_name_band(image_path, field, spec, tpl, all_labels)
                if band_val and _longest_alpha(band_val) > _longest_alpha(value):
                    value, source = band_val, "band_reread"
        # 3d) date-band rescue (dob only): the DOB resolved to
        # nothing while the template carries a dob zone — the
        # digital slip's date row shares the watermark field that
        # swallows its names. Label-anchored band read; see
        # _recover_dob_band for the gate.
        if field == "dob" and value is None:
            band_val = _recover_dob_band(image_path, spec, tpl, all_labels)
            if band_val:
                value, source = band_val, "band_reread"
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
            elif value is not None and re.fullmatch(r"[\d\s-]+", str(value)):
                # An OVER-LENGTH digit string is a faithful read with
                # junk fused to one end (the slip's 11 digits plus a
                # '0' the stamp arc contributed). When recovery cannot
                # separate the junk, the honest state is "not read" —
                # a format FAIL would assert the PRINTED number is
                # wrong, which this evidence does not show. (A
                # short or exact-length misread stays a fallback and
                # fails on its own merits, per the session-5 rule.)
                _m = re.fullmatch(r"\\d\{(\d+)\}", (spec or {}).get("pattern") or "")
                if _m and len(re.sub(r"\D", "", str(value))) > int(_m.group(1)):
                    value, source = None, None
        # 4b) INEC VIN run recovery (NG voter_card number only,
        # calibration 2026-10-27): the VIN prints as spaced
        # alphanumeric groups, and its first glyph misreads often
        # enough ('VIN' -> 'YIN') that the label and zone paths
        # miss it, while the line itself carries a long, digit-rich
        # run that no other line on the card resembles. Adopt the
        # strongest such run (15-24 chars joined, >= 8 digits, at
        # least one letter) from the word lines or the pass texts;
        # it still has to pass the type's format validation at the
        # entry step below.
        if field == "number" and (country, kind) == ("NG", "voter_card") and \
                (value is None or validate_number(country, kind, value) is False
                 or not any(c.isalpha() for c in str(value))):
            # The all-digit case: the resolved value can be format-valid
            # yet be the WRONG FIELD — the card's other number, the PU
            # code, is all digits, while the VIN (this type's identity
            # number) is alphanumeric. A format-valid all-digit value
            # must not shadow the VIN run (measured 2026-10-27: zone
            # step adopted a 10-digit value while _recover_vin held a
            # 22-char letter-bearing run from the VIN line itself).
            vin = _recover_vin(lines, text_lines)
            if vin:
                value, source = vin, "zone_recovery"
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
    # Cross-field date sanity (calibration 2026-10-28, Wisconsin):
    # a document never expires on or before the holder's birth
    # date. When the two extracted dates collide that way, at
    # least one is a BORROWED date — an unanchored zone/text scoop
    # that harvested a neighbouring row's date (there, the issue
    # date filled both slots and falsely expired a valid card).
    # Label/band-anchored values are trusted as printed; an
    # unanchored offender is dropped to 'not read' rather than
    # allowed to decide the verification.
    _dob, _exp = fields_out.get("dob") or {}, fields_out.get("expiry") or {}
    if _dob.get("value") and _exp.get("value") and _exp["value"] <= _dob["value"]:
        for _f in ("dob", "expiry"):
            if fields_out[_f].get("source") not in ("label", "band_reread"):
                fields_out[_f] = {"value": None, "source": None}
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
