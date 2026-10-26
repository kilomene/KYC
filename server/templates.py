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
  level           "full" (priority set, decision-bearing) or "coarse"
                  (aspect + portrait-left only, for the remaining
                  registry types — stated honestly in the findings)

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
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["VOTER", "INEC", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "nin_card"): {
        "aspect": 1.586, "portrait_zone": (0.02, 0.15, 0.36, 0.88), "portrait_expected": True, "pattern_expected": True,
        "labels": ["NATIONAL", "IDENTITY", "NIGERIA"], "number_zone": (0.36, 0.05, 0.98, 0.42), "mrz_zone": None},
    ("NG", "nin_slip"): {
        "aspect": 1.41, "portrait_zone": (0.60, 0.04, 0.97, 0.48), "portrait_expected": False, "pattern_expected": False,
        "labels": ["NATIONAL IDENTITY NUMBER", "NIN"], "number_zone": (0.03, 0.04, 0.60, 0.40), "mrz_zone": None},
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
}
GENERIC_TD3 = {
    "aspect": 1.42, "portrait_zone": (0.03, 0.15, 0.42, 0.78), "portrait_expected": True, "pattern_expected": True,
    "labels": ["PASSPORT"], "number_zone": (0.45, 0.05, 0.98, 0.35), "mrz_zone": "bottom"}

_LABEL_ALIASES = {"LICENCE": ("LICENCE", "LICENSE"), "LICENSE": ("LICENSE", "LICENCE")}

def get_template(country, kind):
    """-> (template_dict, level) — level 'full' | 'coarse' | 'generic'."""
    t = FULL_TEMPLATES.get((country, kind))
    if t:
        return {**t, "level": "full"}, "full"
    if kind == "passport":
        return {**GENERIC_TD3, "level": "generic"}, "generic"
    entry = DOCREG.get_document(country, kind)
    if entry:
        return {"aspect": entry.get("aspect", 1.586),
                "portrait_zone": (0.02, 0.15, 0.36, 0.88),
                "portrait_expected": kind != "nin_slip",
                "pattern_expected": kind != "nin_slip",
                "labels": [], "number_zone": (0.36, 0.05, 0.98, 0.42),
                "mrz_zone": "bottom" if entry.get("mrz") else None,
                "level": "coarse"}, "coarse"
    return None, "none"

def _centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

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
    img = None
    if cv2 is not None:
        try: img = cv2.imread(image_path)
        except Exception: img = None
    if img is None:
        return {"status": "unclear", "findings": {**findings, "error": "image_unreadable"},
                "reason_codes": ["classification_image_unreadable"]}
    h, w = img.shape[:2]
    scored = []  # (weight, fraction)
    # --- aspect ---
    aspect = w / h if h else 0
    rel = abs(aspect - tpl["aspect"]) / tpl["aspect"] if tpl["aspect"] else 1
    a_frac = 1.0 if rel <= 0.10 else (0.5 if rel <= 0.20 else 0.0)
    findings["elements"]["aspect"] = {"image": round(aspect, 3), "template": tpl["aspect"], "match": a_frac}
    scored.append((25, a_frac))
    # --- portrait position (YuNet on the document image) ---
    if tpl.get("portrait_expected"):
        face = None
        try: face = FACE.largest_face(img)
        except Exception: face = None
        if face is None:
            # Not proof of absence (glare, print quality, a drawn
            # stand-in): neutral-low. A face in the WRONG place is the
            # strong tell, scored below.
            findings["elements"]["portrait"] = {"found": False, "position_match": None}
            scored.append((25, 0.48))
        else:
            box = (float(face[0]) / w, float(face[1]) / h, (float(face[0]) + float(face[2])) / w, (float(face[1]) + float(face[3])) / h)
            inside = _inside(_centre(box), tpl["portrait_zone"], pad=0.08)
            findings["elements"]["portrait"] = {"found": True, "box": [round(v, 3) for v in box],
                                                "position_match": inside}
            scored.append((25, 1.0 if inside else 0.16))
    # --- expected labels ---
    labels = tpl.get("labels") or []
    if labels:
        up = (ocr_text or "").upper()
        found = []
        for lab in labels:
            aliases = _LABEL_ALIASES.get(lab, (lab,))
            if any(a in up for a in aliases):
                found.append(lab)
        findings["elements"]["labels"] = {"expected": labels, "found": found}
        scored.append((25, len(found) / len(labels)))
    # --- document-number zone read ---
    zone = tpl.get("number_zone")
    if zone:
        if words is None:
            words = VISION.ocr_words(image_path)
        hits = [wd["text"] for wd in (words or [])
                if _inside(_centre(wd["box"]), zone)
                and sum(ch.isalnum() for ch in wd["text"]) >= 5]
        findings["elements"]["number_zone"] = {"read": bool(hits), "tokens": hits[:4]}
        scored.append((15, 1.0 if hits else 0.0))
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
    findings["score"] = score
    findings["pass_threshold"] = PASS_SCORE
    if score >= PASS_SCORE:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if level == "full":
        return {"status": "fail", "findings": findings, "reason_codes": ["document_classification_mismatch"]}
    return {"status": "unclear", "findings": findings, "reason_codes": ["document_classification_mismatch"]}
