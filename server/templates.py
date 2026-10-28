"""Document classification against country-specific layout templates
(owner's Addition 9, 2026-10-26): the captured image must classify AS
the document type the session CLAIMS, by layout — not merely be a
rectangle of roughly the right shape.

A template describes where things live on the real document:
  aspect          width/height of the document itself
  portrait_zone   relative box (x0, y0, x1, y1) where the portrait sits
  portrait_expected  whether the document carries a portrait at all
  labels          text fragments printed on the document type
  number_zone     relative box where the document number is printed
  mrz_zone        "bottom" for TD3/TD1 documents that carry an MRZ
  level           "full" (decision-bearing), "generic" (the TD3
                  template for passports outside the priority set), or
                  "coarse" (aspect + portrait-left fallback). Phase 4
                  WS1 (2026-10-26): every document type in the registry
                  now has a FULL template (zones/labels from
                  research/*.md) except non-NG/US passports, which use
                  the generic TD3 template; the coarse fallback remains
                  for any future registry type added without one, and
                  findings always state the level that actually ran.

Measurement on the captured image:
  * the image aspect vs the template aspect;
  * the portrait located with the YuNet face detector (a real ID
    portrait IS a face) and its centre tested against portrait_zone;
  * OCR word boxes (tesseract TSV) searched for the expected labels
    and for a document-number-like token inside number_zone;
  * MRZ presence/position from the vision layer's parse.

Elements score into a 0-100 classification score. FULL templates:
score >= 70 passes; below fails with document_classification_mismatch
— a claimed passport whose layout is not a passport auto-rejects in
the standard path. COARSE templates: below threshold is an unclear
with the same reason (strong risk, never an auto-approval). PASS
THRESHOLD CALIBRATION (synthetic fixtures, 2026-10-26): the drawn
passport fixture scores ~76 as a passport and ~58 claimed as a US
driver's licence; a room/scene photo scores near 0. Real documents
carry more of every element (a real portrait photo, full printed
labels) than the drawn fixture does.
"""
import re

try:
    import cv2
except Exception:
    cv2 = None

from . import docregistry as DOCREG
from . import face as FACE
from . import vision as VISION

PASS_SCORE = 70

# (country, kind) -> template. The priority set is FULL; every other
# registry type gets a COARSE template built from the registry facts,
# and all other countries' passports get the generic TD3 template.
FULL_TEMPLATES = {
    ("NG", "passport"): {
        "aspect": 1.42, "portrait_zone": (0.03, 0.15, 0.42, 0.78), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PASSPORT", "NIGERIA"], "number_zone": (0.45, 0.05, 0.98, 0.35), "mrz_zone": "bottom"},
    ("US", "passport"): {
        "aspect": 1.42, "portrait_zone": (0.03, 0.15, 0.42, 0.78), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PASSPORT", "UNITED STATES"], "number_zone": (0.45, 0.05, 0.98, 0.35), "mrz_zone": "bottom"},
    ("NG", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENCE", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "voter_card"): {
        # Portrait zone corrected 2026-10-28: the INEC PVC prints the
        # portrait on the RIGHT (specimen dossier estimate
        # (0.66, 0.30, 0.97, 0.78); owner's genuine sample agrees) —
        # the template carried the driver's-licence left zone, so a
        # found portrait on a genuine card scored as misplaced.
        "aspect": 1.586, "portrait_zone": (0.66, 0.30, 0.97, 0.78), "portrait_expected": True, "pattern_expected": True,
        "labels": ["VOTER", "INEC", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "nin_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["NATIONAL", "IDENTITY", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "nin_slip"): {
        # The REAL wide paper slip (rectification 2026-10-26, layout
        # from research/docs-africa.md + the owner's specimen
        # geometry): NIMC header across the top, Tracking ID top-left,
        # NIN number left-centre, name fields centre, portrait right
        # (~x 0.78-0.95). Aspect is the registry RANGE for this paper
        # type (merged in get_template), not a point value. Current
        # standard/premium slips print a portrait (the earliest
        # enrolment printouts may not — a missing face scores the
        # neutral 0.48, never a hard fail).
        "aspect": 2.0, "portrait_zone": (0.76, 0.15, 0.97, 0.60), "portrait_expected": True, "pattern_expected": False,
        "labels": ["NATIONAL IDENTITY", "NIN"], "number_zone": (0.02, 0.16, 0.46, 0.40), "mrz_zone": None},
    ("US", "passport_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PASSPORT CARD", "UNITED STATES"], "number_zone": (0.36, 0.05, 0.98, 0.42),
        "mrz_zone": None},  # the passport card's MRZ is on the BACK; the front is classified
    ("US", "drivers_license"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.38, 0.90), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENSE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("US", "state_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.38, 0.90), "portrait_expected": True, "pattern_expected": True,
        "labels": ["IDENTIFICATION", "CARD"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("US", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.38, 0.90), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENSE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["NATIONAL", "IDENTITY", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    # ---- Phase 4 WS1: full templates for the researched registry ----
    ("GB", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING", "LICENCE", "UNITED KINGDOM"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("GB", "pass_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PASS", "PROOF OF AGE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("CA", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENCE", "PERMIS"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("CA", "photo_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PHOTO CARD", "IDENTIFICATION"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("AU", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENCE", "AUSTRALIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("AU", "photo_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PHOTO CARD", "PROOF OF AGE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("DE", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["FÜHRERSCHEIN", "BUNDESREPUBLIK"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("DE", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PERSONALAUSWEIS", "BUNDESREPUBLIK"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("GH", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENCE", "GHANA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("GH", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["GHANA CARD", "GHANA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("GH", "voter_card"): {
        "aspect": 1.46, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["VOTER", "GHANA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("KE", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["REPUBLIC OF KENYA", "IDENTITY CARD"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("KE", "maisha_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["MAISHA", "KENYA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("KE", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "KENYA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("ZA", "smart_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["SOUTH AFRICA", "IDENTITY"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("ZA", "green_id_book"): {
        "aspect": 1.42, "portrait_zone": (0.03, 0.15, 0.42, 0.78), "portrait_expected": True, "pattern_expected": False,
        "labels": ["SOUTH AFRICA", "IDENTITY"], "number_zone": (0.45, 0.05, 0.98, 0.35), "mrz_zone": None},
    ("ZA", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "SOUTH AFRICA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IN", "aadhaar"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["AADHAAR", "GOVERNMENT OF INDIA"], "number_zone": (0.10, 0.60, 0.95, 0.95), "mrz_zone": None},
    ("IN", "pan_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.30, 0.30, 0.85), "portrait_expected": True, "pattern_expected": True,
        "labels": ["INCOME TAX", "PERMANENT ACCOUNT"], "number_zone": (0.30, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IN", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "INDIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IN", "voter_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["ELECTION COMMISSION", "VOTER"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("PH", "philid"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PHILIPPINES", "NATIONAL ID"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("PH", "umid"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["UMID", "SOCIAL SECURITY"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("PH", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVER", "LICENSE", "PHILIPPINES"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("SG", "nric"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["REPUBLIC OF SINGAPORE", "IDENTITY CARD"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("SG", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "SINGAPORE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("AE", "emirates_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["EMIRATES ID", "UNITED ARAB EMIRATES"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("AE", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "EMIRATES"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("FR", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["CARTE NATIONALE", "REPUBLIQUE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("FR", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PERMIS DE CONDUIRE", "REPUBLIQUE"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NL", "national_id"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["IDENTITEITSKAART", "NEDERLAND"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NL", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["RIJBEWIJS", "NEDERLAND"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IE", "passport_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["PASSPORT CARD", "IRELAND"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IE", "drivers_licence"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["DRIVING LICENCE", "IRELAND"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("IE", "age_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["AGE CARD", "GARDA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
}
GENERIC_TD3 = {
    "aspect": 1.42, "portrait_zone": (0.03, 0.15, 0.42, 0.78), "portrait_expected": True, "pattern_expected": True,
    "labels": ["PASSPORT"], "number_zone": (0.45, 0.05, 0.98, 0.35), "mrz_zone": "bottom"}

_LABEL_ALIASES = {"LICENCE": ("LICENCE", "LICENSE"), "LICENSE": ("LICENSE", "LICENCE"),
                  # INEC's small logo acronym rarely survives OCR of a
                  # photographed PVC; the commission's full name is
                  # printed large directly under the federal header
                  # (calibration 2026-10-28: genuine PVCs found 1/3
                  # labels — NIGERIA only — and failed classification).
                  "INEC": ("INEC", "ELECTORAL COMMISSION", "NATIONAL ELECTORAL")}

# Country-anchor words: the issuing-country names authorities print
# on their documents. A template label containing one of these words
# is an ANCHOR label — the only label family that discriminates
# between countries whose documents share generic structure (same
# aspect, same portrait side, "DRIVER LICENCE" in both). Measured
# 2026-10-27: a California licence claimed as a Nigerian licence
# scored 76.3 (pass) because DRIVER + LICENCE (via the spelling
# alias) supplied 2 of the NG template's 3 labels and only NIGERIA
# was missing. When a template HAS anchor labels and none is found,
# the labels fraction is capped — generic words alone cannot carry a
# cross-country claim. Countries whose cards carry no single federal
# phrase (US state-issued cards) have no entry and are unchanged.
_ALPHA3 = {"NG": "NGA", "US": "USA", "CA": "CAN", "GB": "GBR", "AU": "AUS",
           "DE": "DEU", "GH": "GHA", "KE": "KEN", "ZA": "ZAF", "IN": "IND",
           "PH": "PHL", "SG": "SGP", "AE": "ARE", "FR": "FRA", "NL": "NLD",
           "IE": "IRL"}

_COUNTRY_ANCHOR_WORDS = {
    "NG": ("NIGERIA",), "GH": ("GHANA",), "KE": ("KENYA",),
    "ZA": ("SOUTH AFRICA",), "AU": ("AUSTRALIA",), "IN": ("INDIA",),
    "PH": ("PHILIPPINES",), "SG": ("SINGAPORE",), "AE": ("EMIRATES",),
    "GB": ("UNITED KINGDOM",), "IE": ("IRELAND", "GARDA"),
    "DE": ("BUNDESREPUBLIK",), "FR": ("REPUBLIQUE",),
    "NL": ("NEDERLAND",), "CA": ("PERMIS",), "US": ("UNITED STATES",),
}

def get_template(country, kind):
    """-> (template_dict, level) — level 'full' | 'coarse' | 'generic'.
    Registry geometry is merged over every template: paper/booklet
    types carry aspect_min/aspect_max there (the registry is the
    source of truth for physical geometry), and the aspect element
    scores against the RANGE for those types."""
    entry = DOCREG.get_document(country, kind)
    geo = {}
    if entry and entry.get("aspect_min"):
        geo = {"aspect_min": entry["aspect_min"], "aspect_max": entry["aspect_max"]}
    t = FULL_TEMPLATES.get((country, kind))
    if t:
        return {**t, **geo, "level": "full"}, "full"
    if kind == "passport":
        return {**GENERIC_TD3, "level": "generic"}, "generic"
    if entry:
        return {"aspect": entry.get("aspect", 1.586), **geo,
                "portrait_zone": (0.02, 0.15, 0.36, 0.88),
                "portrait_expected": kind != "nin_slip",
                "pattern_expected": kind != "nin_slip",
                "labels": [], "number_zone": (0.36, 0.05, 0.98, 0.42),
                "mrz_zone": "bottom" if entry.get("mrz") else None,
                "level": "coarse"}, "coarse"
    return None, "none"

def _centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

def _assemble_zone_number(zone_words, country, kind):
    """Assemble the document number from FRAGMENTED digit tokens
    inside the number zone (Session-5 diagnosis, 2026-10-26).

    The single-token rule (one token with >= 5 alphanumerics) misses
    numbers OCR shatters into short tokens — on the owner's slip the
    stretched warp broke the digit line into 1-3 char tokens — and it
    also misses numbers PRINTED in groups (the print itself separates
    the groups, so each group is its own word box). This path groups
    the zone's word boxes into lines, walks runs of ADJACENT
    pure-digit tokens (same line, small horizontal gap), concatenates
    each run, and counts the zone as read only when a concatenation
    satisfies the type's OWN number format (fieldtemplates
    validate_number — pattern or check-digit validator). A run that
    assembles to the wrong shape is not evidence and is skipped; for
    types with no format to judge by, an assembled run needs >= 8
    digits before it counts. Returns the assembled number or None."""
    try:
        from . import fieldtemplates as FT
    except Exception:
        return None
    items = sorted(zone_words or [],
                   key=lambda wd: ((wd["box"][1] + wd["box"][3]) / 2.0, wd["box"][0]))
    lines = []
    for wd in items:
        cy = (wd["box"][1] + wd["box"][3]) / 2.0
        if lines and abs(cy - lines[-1][0]) <= 0.03:
            lines[-1][1].append(wd)
        else:
            lines.append((cy, [wd]))
    for _cy, line in lines:
        line.sort(key=lambda wd: wd["box"][0])
        runs = []
        run = []
        prev_x1 = None
        for wd in line:
            digits = re.sub(r"\D", "", wd["text"] or "")
            pure = bool(digits) and not re.search(r"[A-Za-z]", wd["text"] or "")
            gap = (wd["box"][0] - prev_x1) if prev_x1 is not None else 0.0
            if pure and gap <= 0.08:
                run.append(digits)
            else:
                if len(run) >= 2:
                    runs.append("".join(run))
                run = [digits] if pure else []
            prev_x1 = wd["box"][2]
        if len(run) >= 2:
            runs.append("".join(run))
        for joined in runs:
            if len(joined) < 6:
                continue
            valid = FT.validate_number(country, kind, joined)
            if valid is True:
                return joined
            if valid is None and len(joined) >= 8:
                return joined
    return None

def _inside(pt, zone, pad=0.0):
    return (zone[0] - pad <= pt[0] <= zone[2] + pad) and (zone[1] - pad <= pt[1] <= zone[3] + pad)

def check_classification(image_path, country, kind, ocr_text="", mrz_parsed=None, words=None):
    """Classify the captured image against the claimed type's template.
    Returns the standard check dict; findings carry the per-element
    evidence and the calibrated score."""
    tpl, level = get_template(country or "", kind or "")
    if tpl is None:
        return {"status": "unclear", "findings": {"template": "none", "claimed": f"{country}/{kind}"},
                "reason_codes": ["classification_template_missing"]}
    findings = {"template_level": level, "claimed": f"{country}/{kind}", "elements": {}}
    # Measure in DOCUMENT space: when framing found a quad, the
    # warped rendition's dimensions ARE the document's (the camera
    # frame's own aspect is the phone's, not the document's — scoring
    # a wide paper slip against the portrait frame it was shot in was
    # part of the 2026-10-26 rectification diagnosis). Callers should
    # pass ALL OCR evidence text they hold in ocr_text (every read
    # pass, not only the chosen one): the labels element is judged on
    # that union — a header can land in a non-chosen pass.
    measure_path = image_path
    quad_area = None
    warped = None
    try:
        from . import framing as FRAMING
        warped = FRAMING.warped_rendition(image_path)
        if warped:
            measure_path = warped
            findings["measured_on"] = "warped"
            analysis = FRAMING.analyse_path(image_path)
            if analysis:
                quad_area = analysis.get("area_ratio")
    except Exception:
        pass
    img = None
    if cv2 is not None:
        try: img = cv2.imread(measure_path)
        except Exception: img = None
    if img is None:
        return {"status": "unclear", "findings": {**findings, "error": "image_unreadable"},
                "reason_codes": ["classification_image_unreadable"]}
    h, w = img.shape[:2]
    scored = []  # (weight, fraction)
    # --- aspect ---
    aspect = w / h if h else 0

    def _aspect_match(a):
        if tpl.get("aspect_min"):
            lo, hi = tpl["aspect_min"], tpl["aspect_max"]
            if lo <= a <= hi:
                return 1.0
            if lo * 0.90 <= a <= hi * 1.10:
                return 0.5
            return 0.0
        rel = abs(a - tpl["aspect"]) / tpl["aspect"] if tpl["aspect"] else 1
        return 1.0 if rel <= 0.10 else (0.5 if rel <= 0.20 else 0.0)

    a_frac = _aspect_match(aspect)
    aspect_rec = {"image": round(aspect, 3), "match": a_frac}
    if tpl.get("aspect_min"):
        aspect_rec["range"] = [tpl["aspect_min"], tpl["aspect_max"]]
    else:
        aspect_rec["template"] = tpl["aspect"]
    # Flat-capture regime: the document fills >= 85% of the frame, so
    # the frame's own aspect is ALSO the document's (a scan-like
    # image), and the quad fit's pixel noise (rounded corners bias
    # the warped measure — measured: a drawn passport read 1.576 on
    # the warp against 1.55 on the frame, straddling the tolerance)
    # must not decide the element alone: score both, take the better.
    # In the photographed regime (small quad) only the document-space
    # measure counts — the frame's aspect there is the phone's.
    if quad_area is not None and quad_area >= 0.85 and measure_path != image_path:
        try:
            orig = cv2.imread(image_path) if cv2 is not None else None
        except Exception:
            orig = None
        if orig is not None:
            oh, ow = orig.shape[:2]
            frame_aspect = ow / oh if oh else 0
            frame_frac = _aspect_match(frame_aspect)
            aspect_rec["frame_image"] = round(frame_aspect, 3)
            aspect_rec["frame_match"] = frame_frac
            a_frac = max(a_frac, frame_frac)
            aspect_rec["match"] = a_frac
    aspect_neutral = False
    if not warped:
        # No document-space measure exists (framing found no quad):
        # the frame's aspect is the PHONE's, not the document's, and
        # scoring it against the template manufactures a mismatch on
        # genuine hand-held captures (measured 2026-10-27: a genuine
        # CA licence, card upright inside a portrait phone frame,
        # scored aspect 0). Absence of evidence is not evidence: the
        # element is EXCLUDED from the score (2026-10-28 — as a 0.48
        # drag it capped genuine hand-held documents below the pass
        # line no matter how well the evidenced elements scored;
        # measured on the owner's genuine INEC PVCs). Framing quality
        # is gated separately.
        aspect_rec["frame_only"] = True
        aspect_rec["match"] = None
        aspect_rec["neutral"] = True
        aspect_neutral = True
    findings["elements"]["aspect"] = aspect_rec
    if not aspect_neutral:
        scored.append((25, a_frac))
    # --- portrait position (YuNet on the document image) ---
    if tpl.get("portrait_expected"):
        face = None
        try: face = FACE.largest_face(img)
        except Exception: face = None
        if face is not None and float(face[2]) < 0.05 * w:
            # Detector noise, not a portrait (2026-10-28): YuNet
            # returned a 1.4%-of-frame box on the genuine INEC PVC's
            # glare/texture, which then scored as a MISPLACED portrait
            # (0.16) — manufactured evidence against a genuine card.
            # A printed document portrait is never that small; treat
            # sub-5% boxes as not found (neutral, excluded below).
            face = None
        if face is None:
            # Not proof of absence (glare, print quality, a drawn
            # stand-in): the element is EXCLUDED from the score
            # (2026-10-28, same recalibration as the aspect element —
            # a 0.48 drag here plus a neutral aspect made the pass
            # line unreachable for genuine hand-held captures).
            # A face in the WRONG place is the strong tell, scored
            # below when a face IS found.
            findings["elements"]["portrait"] = {"found": False, "position_match": None,
                                                "neutral": True}
        else:
            box = (float(face[0]) / w, float(face[1]) / h, (float(face[0]) + float(face[2])) / w, (float(face[1]) + float(face[3])) / h)
            inside = _inside(_centre(box), tpl["portrait_zone"], pad=0.08)
            findings["elements"]["portrait"] = {"found": True, "box": [round(v, 3) for v in box],
                                                "position_match": inside}
            scored.append((25, 1.0 if inside else 0.16))
    # --- expected labels ---
    anchor_absent = False
    labels = tpl.get("labels") or []
    if labels:
        up = (ocr_text or "").upper()
        found = []
        for lab in labels:
            aliases = _LABEL_ALIASES.get(lab, (lab,))
            if any(a in up for a in aliases):
                found.append(lab)
        labels_rec = {"expected": labels, "found": found}
        labels_frac = len(found) / len(labels)
        anchor_words = _COUNTRY_ANCHOR_WORDS.get((country or "").upper(), ())
        anchor_labels = [lab for lab in labels
                         if any(w in lab.upper() for w in anchor_words)]
        if anchor_labels and not any(lab in found for lab in anchor_labels):
            # The claim's own country anchor is absent: generic shared
            # words cannot carry the element (see _COUNTRY_ANCHOR_WORDS).
            labels_frac = min(labels_frac, 0.34)
            labels_rec["anchor_missing"] = anchor_labels
            anchor_absent = True
        findings["elements"]["labels"] = labels_rec
        scored.append((25, labels_frac))
    # --- document-number zone read ---
    zone = tpl.get("number_zone")
    if zone:
        if words is None:
            words = VISION.ocr_words(image_path)
        zone_words = [wd for wd in (words or []) if _inside(_centre(wd["box"]), zone)]
        hits = [wd["text"] for wd in zone_words
                if sum(ch.isalnum() for ch in wd["text"]) >= 5]
        # Assembly path: no single token qualifies, but the zone's
        # digit tokens may still BE the number — shattered by OCR or
        # printed in groups — when concatenated (see
        # _assemble_zone_number; the type's own format judges).
        assembled = None
        if not hits:
            assembled = _assemble_zone_number(zone_words, country, kind)
        zone_rec = {"read": bool(hits) or assembled is not None, "tokens": hits[:4]}
        if assembled is not None:
            zone_rec["assembled"] = assembled
        findings["elements"]["number_zone"] = zone_rec
        scored.append((15, 1.0 if zone_rec["read"] else 0.0))
    # --- MRZ zone ---
    if mrz_parsed is None:
        # Independent band probe (2026-10-26): the OCR pipeline no
        # longer hunts the MRZ band for document types that carry no
        # MRZ (a speed fix in vision.read_document_text) — but THIS
        # check is exactly where a forbidden MRZ must be caught: a
        # claimed non-MRZ card whose image carries a check-digit-valid
        # MRZ is evidence against the claim. Probe the band here so
        # the element is judged on evidence, not on an empty input.
        try:
            import shutil as _sh
            from . import checks as _C
            _exe = _sh.which("tesseract")
            if _exe:
                _band = VISION._mrz_band_text(image_path, _exe)
                if _band:
                    mrz_parsed = _C.parse_mrz(_band)
                    findings["elements"]["mrz_probe"] = {
                        "source": "classification_band_probe",
                        "valid_mrz": bool(mrz_parsed and mrz_parsed.get("valid"))}
        except Exception:
            pass
    if tpl.get("mrz_zone"):
        ok = bool(mrz_parsed and mrz_parsed.get("valid"))
        findings["elements"]["mrz"] = {"expected_zone": tpl["mrz_zone"], "valid_mrz": ok}
        scored.append((15, 1.0 if ok else 0.0))
    elif level == "coarse":
        # Coarse templates are "aspect + portrait-left + MRZ-ABSENT":
        # a valid MRZ on a claimed non-MRZ card type is evidence
        # against the claim, and its absence is evidence for it.
        present = bool(mrz_parsed and mrz_parsed.get("valid"))
        findings["elements"]["mrz_absent"] = {"valid_mrz_present": present}
        scored.append((15, 0.0 if present else 1.0))
    total_w = sum(wt for wt, _ in scored) or 1
    score = round(100 * sum(wt * fr for wt, fr in scored) / total_w, 1)
    findings["scored_elements"] = len(scored)
    if anchor_absent and score >= PASS_SCORE:
        # Country-anchor guard (2026-10-28): with neutral elements
        # excluded from the denominator, a cross-country claim could
        # otherwise ride generic labels + a readable number zone over
        # the pass line. A claim whose own country anchor never
        # appeared cannot pass, whatever the evidenced elements say
        # (the labels-fraction cap above stays as the element-level
        # expression of the same rule). Exemption: a check-digit-valid
        # MRZ whose issuing state IS the claimed country is itself
        # country-grade evidence — the anchor word going unread in
        # the VIZ must not convict a cryptographically consistent
        # document (the synthetic NG passport fixture: VIZ labels
        # read PASSPORT only, MRZ valid and NGA-issued).
        _l1 = (mrz_parsed or {}).get("line1") or ""
        if not _l1 and ocr_text:
            # The band probe can return a valid parse whose line 1
            # fell outside the probed strip; the caller's full OCR
            # text usually carries both lines — re-parse for line 1
            # before judging the issuing state.
            try:
                from . import checks as _CHECKS
                _full = _CHECKS.parse_mrz(ocr_text)
                if _full:
                    _l1 = _full.get("line1") or ""
            except Exception:
                pass
        _issuing = _l1[2:5].rstrip("<") if len(_l1) >= 5 else ""
        if mrz_parsed and mrz_parsed.get("valid") and _issuing and \
                _issuing == _ALPHA3.get((country or "").upper(), ""):
            findings["anchor_via_mrz"] = _issuing
        else:
            score = round(PASS_SCORE - 0.1, 1)
            findings["anchor_capped"] = True
    findings["score"] = score
    findings["pass_threshold"] = PASS_SCORE
    if len(scored) < 2:
        # Too little evidence was measurable to judge the claim at
        # all (e.g. no quad, no portrait, no labels, no zone read):
        # unclear, never a manufactured pass or fail.
        return {"status": "unclear", "findings": findings,
                "reason_codes": ["classification_evidence_insufficient"]}
    if score >= PASS_SCORE:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if level == "full":
        return {"status": "fail", "findings": findings, "reason_codes": ["document_classification_mismatch"]}
    return {"status": "unclear", "findings": findings, "reason_codes": ["document_classification_mismatch"]}
