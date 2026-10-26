"""Machine-readable payload semantics (Phase 4 WS1, 2026-10-26).

server/vision.py decodes the codes (QR via OpenCV, PDF417/barcodes
via zxing-cpp); THIS module understands what the payloads MEAN:

  * AAMVA (US/CA licence & ID PDF417): the payload is a sequence of
    3-character element IDs (DA*, DB*, DC*, DD*) with values, usually
    anchored by the "@" / "ANSI " compliance header. We parse ALL
    elements present, expose the identity elements as typed fields,
    and validate element formats (DBB/DBA issue/expiry dates are
    MMDDYYYY, DBC sex is in {1,2,9}, DAU height is a 3-digit inch
    count or an imperial F'I" string, DAJ is a 2-letter jurisdiction).
  * NG NIN-slip QR: NIMC does not publish a payload grammar in the
    research corpus (research/docs-africa.md records only that the
    slip carries a QR verifiable via the NIMC MWS app). The parser
    therefore accepts the field shapes seen on printed slips (JSON,
    key:value lines, delimited text) and validates STRUCTURE: an
    11-digit NIN passing NIN format validation, plus surname/DOB
    cross-checks where the payload carries them. Findings label the
    depth honestly as "structural" — semantic verification against
    NIMC is NOT performed (no NIMC integration exists).
  * Aadhaar secure QR (UIDAI): the payload is a big integer whose
    byte form is a zlib-compressed XML demographic record
    (<PrintLetterBarcodeData uid="..." name="..." dob="..." .../>),
    optionally preceded by indicator bytes for email/mobile hashes.
    We decompress (scanning for the zlib stream), parse the XML,
    extract name/DOB and the last 4 of the UID, and cross-check.
    The XML in a genuine secure QR is accompanied by a UIDAI digital
    signature segment; we hold no UIDAI certificate, so signature
    verification is NOT performed — findings state this; validation
    depth is "structural+consistency".
  * PhilID QR (PhilSys): the back-of-card QR is a digitally signed
    payload that reveals the PSN; its full grammar is not published
    in the research corpus. The parser accepts JSON / delimited
    shapes, extracts PCN (16 digits), PSN (12 digits), name and DOB
    where present, and cross-checks. Depth labelled "structural";
    PhilSys signature verification is NOT performed.

Cross-check rule (unchanged from the vision layer's contract):
decoded content is evidence, never truth — a material disagreement
with the printed document fails with code_decode_mismatch.
"""
import io, json, re, zlib
import xml.etree.ElementTree as ET
from datetime import date

from . import fieldtemplates as FT

# ---------------- AAMVA ----------------
# Element IDs (AAMVA DL/ID standard, Annex D). We parse whatever is
# present; the identity subset is typed below.
AAMVA_ELEMENTS = {
    "DAQ": "document_number", "DCS": "surname", "DDE": "surname_truncation",
    "DAC": "first_name", "DDF": "first_name_truncation", "DAD": "middle_names",
    "DDG": "middle_truncation", "DCA": "vehicle_class", "DCB": "restrictions",
    "DCD": "endorsements", "DBD": "issue_date", "DBB": "dob", "DBA": "expiry",
    "DBL": "name_suffix", "DBM": "former_surname", "DBN": "alias",
    "DBC": "sex", "DBP": "alias_suffix", "DBR": "alias_given", "DBS": "suffix2",
    "DCU": "name_suffix2", "DAU": "height", "DAW": "weight_lb", "DAX": "weight_kg",
    "DAY": "eye_colour", "DAZ": "hair_colour", "DAE": "suffix3", "DAF": "prefix",
    "DAG": "address_street", "DAH": "address_street2", "DAI": "address_city",
    "DAJ": "address_state", "DAK": "address_postal", "DCE": "weight_range",
    "DCF": "document_discriminator", "DCG": "country", "DCH": "federal_commercial",
    "DCI": "place_of_birth", "DCJ": "audit_information", "DCK": "inventory_control",
    "DBN2": "alias2", "DDH": "under_18_until", "DDI": "under_19_until",
    "DDJ": "under_21_until", "DDK": "organ_donor", "DDL": "veteran",
    "DAA": "full_name_legacy", "DAB": "surname_legacy", "DAC2": "given_legacy",
    "DAL": "address_legacy", "DAM": "address2_legacy", "DAN": "city_legacy",
    "DAO": "state_legacy", "DAP": "postal_legacy", "DAV": "height_in",
    "DAX2": "x2", "PAF": "x3",
}
_AAMVA_ID_SET = {k for k in AAMVA_ELEMENTS if len(k) == 3}

def _aamva_date(mmddyyyy):
    try:
        return date(int(mmddyyyy[4:8]), int(mmddyyyy[0:2]), int(mmddyyyy[2:4]))
    except Exception:
        return None

def parse_aamva(text):
    """Parse an AAMVA PDF417 payload. -> dict with `elements` (raw
    element-id -> value), typed `fields`, and `format` findings per
    validated element; or None when the text is not AAMVA-shaped."""
    if not text:
        return None
    raw = text.replace("\r", "\n")
    elements = {}
    # Elements are separated by newlines / segment terminators in the
    # decoded text zxing returns. Scan line-wise first.
    for line in raw.split("\n"):
        line = line.strip()
        m = re.match(r"^([A-Z]{3})(.+)$", line)
        if m and m.group(1) in _AAMVA_ID_SET:
            elements[m.group(1)] = m.group(2).strip()
    if len(elements) < 3:
        # Dense single-line form: anchor on known IDs in sequence.
        elements = {}
        ids = sorted(_AAMVA_ID_SET)
        pattern = re.compile(r"(DAQ|DCS|DDE|DAC|DDF|DAD|DDG|DBD|DBB|DBA|DBC|DAU|DAG|DAH|DAI|DAJ|DAK|DCF|DCG|DCB|DCD|DCA|DBL|DAY|DAZ|DCU|DCI)\s*")
        parts = pattern.split(raw)
        # split yields [prefix, id, value, id, value, ...]
        for i in range(1, len(parts) - 1, 2):
            elements[parts[i]] = parts[i + 1].strip().strip("\x1e\x1d")
    if "DAQ" not in elements and "DCS" not in elements:
        return None
    fields = {}
    if elements.get("DAQ"):
        fields["number"] = elements["DAQ"]
    if elements.get("DCS"):
        fields["surname"] = elements["DCS"]
    if elements.get("DAC"):
        fields["first_name"] = elements["DAC"]
    if elements.get("DAD"):
        fields["middle_names"] = elements["DAD"]
    for key, eid in (("dob", "DBB"), ("expiry", "DBA"), ("issue_date", "DBD")):
        if elements.get(eid):
            d = _aamva_date(elements[eid])
            fields[key] = d.isoformat() if d else None
            fields[key + "_raw"] = elements[eid]
    if elements.get("DBC"):
        fields["sex"] = {"1": "male", "2": "female", "9": "not_specified"}.get(elements["DBC"], "invalid")
    fmt = {}
    for eid in ("DBB", "DBA", "DBD"):
        if eid in elements:
            fmt[eid] = bool(re.fullmatch(r"\d{8}", elements[eid]) and _aamva_date(elements[eid]))
    if "DBC" in elements:
        fmt["DBC"] = elements["DBC"] in ("1", "2", "9")
    if "DAU" in elements:
        fmt["DAU"] = bool(re.fullmatch(r"\d{3}", elements["DAU"]) or
                          re.fullmatch(r"\d{1,2}'-?\d{1,2}\"", elements["DAU"]))
    if "DAJ" in elements:
        fmt["DAJ"] = bool(re.fullmatch(r"[A-Z]{2}", elements["DAJ"]))
    if "DAK" in elements:
        fmt["DAK"] = bool(re.fullmatch(r"[A-Z0-9 -]{3,11}", elements["DAK"]))
    return {"standard": "AAMVA", "elements": elements, "fields": fields,
            "format": fmt, "format_valid": all(fmt.values()) if fmt else None,
            "validation_depth": "semantic"}

# ---------------- shared delimited/JSON payload reading ----------------

def _payload_fields(text):
    """Best-effort field extraction from a QR text payload: JSON
    object, key:value / key=value lines, or delimited fields.
    Returns a lower-cased key -> value dict (possibly empty)."""
    out = {}
    t = (text or "").strip()
    if not t:
        return out
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                return {str(k).lower().strip(): str(v).strip() for k, v in obj.items()}
        except Exception:
            pass
    for chunk in re.split(r"[\n;|]", t):
        m = re.match(r"\s*([A-Za-z _/]{2,30})\s*[:=]\s*(.+?)\s*$", chunk)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out

def _pick(fields, *keys):
    for k in keys:
        for fk, fv in fields.items():
            if k in fk and fv:
                return fv
    return None

# ---------------- NG NIN-slip QR ----------------

def parse_nin_qr(text):
    """Structural parse of a NIN-slip QR payload. See module docstring
    for the honesty label: NIMC publishes no grammar in the research
    corpus, so this validates structure + the NIN itself."""
    if not text:
        return None
    fields_in = _payload_fields(text)
    flat = re.sub(r"\s+", "", text.upper())
    nin = None
    cand = _pick(fields_in, "nin", "national identification number", "id number")
    if cand:
        d = re.sub(r"\D", "", cand)
        if len(d) == 11:
            nin = d
    if nin is None:
        m = re.search(r"\b(\d{11})\b", re.sub(r"[ ]", "", text))
        if m:
            nin = m.group(1)
    if nin is None and "NIN" not in text.upper():
        return None
    out = {"standard": "NG-NIN-QR", "validation_depth": "structural",
           "depth_note": "NIMC payload grammar is not published in the research corpus; structure + NIN format validated, NIMC semantic verification NOT performed.",
           "fields": {}}
    if nin:
        out["fields"]["nin"] = nin
        out["fields"]["nin_format_valid"] = FT.validate_number("NG", "nin_slip", nin) is True
    surname = _pick(fields_in, "surname", "last name", "lastname")
    given = _pick(fields_in, "first name", "given", "firstname", "other name")
    dob = _pick(fields_in, "dob", "date of birth", "birth")
    if surname:
        out["fields"]["surname"] = surname.upper()
    if given:
        out["fields"]["first_name"] = given.upper()
    if dob:
        d = FT.parse_date_value(dob)
        out["fields"]["dob"] = d.isoformat() if d else None
    return out

# ---------------- Aadhaar secure QR ----------------

def _aadhaar_from_bytes(raw):
    """Find the zlib stream inside the payload bytes and parse the
    XML demographic record. -> fields dict or None."""
    if not raw:
        return None
    xml_bytes = None
    for off in range(0, min(len(raw), 64)):
        if raw[off:off + 1] == b"\x78":
            try:
                xml_bytes = zlib.decompress(raw[off:])
                break
            except Exception:
                continue
    if xml_bytes is None:
        try:
            xml_bytes = zlib.decompress(raw)
        except Exception:
            return None
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", "replace"))
    except Exception:
        return None
    attrs = {k.lower(): (v or "").strip() for k, v in root.attrib.items()}
    fields = {}
    uid = re.sub(r"\D", "", attrs.get("uid", ""))
    if len(uid) == 12:
        fields["uid_last4"] = uid[-4:]
        fields["uid_format_valid"] = FT.aadhaar_valid(uid)
    if attrs.get("name"):
        fields["name"] = attrs["name"].upper()
    dob_raw = attrs.get("dob") or attrs.get("yob")
    if dob_raw:
        d = FT.parse_date_value(dob_raw)
        fields["dob"] = d.isoformat() if d else None
        fields["dob_raw"] = dob_raw
    if attrs.get("gender"):
        fields["gender"] = attrs["gender"].upper()
    return fields or None

def parse_aadhaar_qr(data):
    """Parse an Aadhaar secure-QR payload (digit string, raw bytes
    from a binary-safe decoder, or the XML itself). UIDAI signature
    verification is NOT performed (no UIDAI certificate held)."""
    if data is None:
        return None
    fields = None
    if isinstance(data, (bytes, bytearray)):
        fields = _aadhaar_from_bytes(bytes(data))
    else:
        t = str(data).strip()
        if t.startswith("<"):
            try:
                root = ET.fromstring(t)
                attrs = {k.lower(): (v or "").strip() for k, v in root.attrib.items()}
                fields = {}
                uid = re.sub(r"\D", "", attrs.get("uid", ""))
                if len(uid) == 12:
                    fields["uid_last4"] = uid[-4:]
                    fields["uid_format_valid"] = FT.aadhaar_valid(uid)
                if attrs.get("name"):
                    fields["name"] = attrs["name"].upper()
                dob_raw = attrs.get("dob") or attrs.get("yob")
                if dob_raw:
                    d = FT.parse_date_value(dob_raw)
                    fields["dob"] = d.isoformat() if d else None
            except Exception:
                fields = None
        elif re.fullmatch(r"\d{100,}", t):
            try:
                raw = int(t).to_bytes((int(t).bit_length() + 7) // 8, "big")
                fields = _aadhaar_from_bytes(raw)
            except Exception:
                fields = None
    if not fields:
        return None
    return {"standard": "AADHAAR-SECURE-QR", "fields": fields,
            "validation_depth": "structural+consistency",
            "depth_note": "UIDAI digital signature NOT verified (no UIDAI certificate held); decompressed XML structure + field consistency validated."}

def build_aadhaar_payload(uid, name, dob, gender="M"):
    """Fixture builder: the documented secure-QR construction —
    XML demographic record, zlib-compressed, encoded as the decimal
    big integer the QR carries. Used by tests and the benchmark."""
    root = ET.Element("PrintLetterBarcodeData", {
        "uid": uid, "name": name, "dob": dob, "gender": gender})
    xml = ET.tostring(root, encoding="utf-8")
    comp = zlib.compress(xml)
    return str(int.from_bytes(comp, "big"))

# ---------------- PhilID QR ----------------

def parse_philid_qr(text):
    """Structural parse of a PhilSys QR payload (see docstring for
    the honesty label)."""
    if not text:
        return None
    fields_in = _payload_fields(text)
    flat = re.sub(r"[\s-]", "", text)
    pcn = psn = None
    cand = _pick(fields_in, "pcn", "card number", "card no")
    if cand:
        d = re.sub(r"\D", "", cand)
        if len(d) == 16:
            pcn = d
    cand = _pick(fields_in, "psn", "philsys number", "philsys no")
    if cand:
        d = re.sub(r"\D", "", cand)
        if len(d) == 12:
            psn = d
    if pcn is None:
        m = re.search(r"\b(\d{16})\b", flat)
        if m:
            pcn = m.group(1)
    if psn is None:
        m = re.search(r"\b(\d{12})\b", flat)
        if m:
            psn = m.group(1)
    if pcn is None and psn is None and "PHILSYS" not in text.upper() and "PHILID" not in text.upper():
        return None
    out = {"standard": "PHILID-QR", "validation_depth": "structural",
           "depth_note": "PhilSys QR grammar is not published in the research corpus; structure validated, PhilSys signature verification NOT performed.",
           "fields": {}}
    if pcn:
        out["fields"]["pcn"] = pcn
    if psn:
        out["fields"]["psn"] = psn
    surname = _pick(fields_in, "surname", "last name", "lastname")
    given = _pick(fields_in, "first name", "given", "firstname")
    name = _pick(fields_in, "full name", "name")
    dob = _pick(fields_in, "dob", "date of birth", "birth")
    if surname:
        out["fields"]["surname"] = surname.upper()
    if given:
        out["fields"]["first_name"] = given.upper()
    if name and not surname:
        out["fields"]["name"] = name.upper()
    if dob:
        d = FT.parse_date_value(dob)
        out["fields"]["dob"] = d.isoformat() if d else None
    return out

# ---------------- cross-checking ----------------

def cross_check_payload(parsed, doc_fields, country=None, kind=None):
    """Compare a parsed payload against the printed/submitted document
    fields. -> (mismatches[list], compared[int]). Only fields present
    on BOTH sides are compared; absence is not a disagreement."""
    doc_fields = doc_fields or {}
    mismatches, compared = [], 0
    if not parsed:
        return mismatches, compared
    f = parsed.get("fields") or {}
    def _alnum(s):
        return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())
    def _name_tokens(s):
        return set(re.sub(r"[^A-Z ]", " ", str(s or "").upper()).split())
    checks = []
    std = parsed.get("standard")
    if std == "AAMVA":
        if f.get("number") and doc_fields.get("doc_number"):
            checks.append(("number", _alnum(f["number"]) == _alnum(doc_fields["doc_number"])))
        if f.get("dob") and doc_fields.get("doc_dob"):
            checks.append(("dob", f["dob"] == doc_fields["doc_dob"]))
        if f.get("expiry") and doc_fields.get("doc_expiry"):
            checks.append(("expiry", f["expiry"] == doc_fields["doc_expiry"]))
        if f.get("surname") and doc_fields.get("doc_last_name"):
            checks.append(("surname", _alnum(f["surname"]) == _alnum(doc_fields["doc_last_name"])))
    elif std == "NG-NIN-QR":
        if f.get("nin") and doc_fields.get("doc_number"):
            checks.append(("number", _alnum(f["nin"]) == _alnum(doc_fields["doc_number"])))
        if f.get("dob") and doc_fields.get("doc_dob"):
            checks.append(("dob", f["dob"] == doc_fields["doc_dob"]))
        if f.get("surname") and doc_fields.get("doc_last_name"):
            checks.append(("surname", _alnum(f["surname"]) == _alnum(doc_fields["doc_last_name"])))
    elif std == "AADHAAR-SECURE-QR":
        if f.get("uid_last4") and doc_fields.get("doc_number"):
            checks.append(("number_last4", _alnum(doc_fields["doc_number"])[-4:] == f["uid_last4"]))
        if f.get("dob") and doc_fields.get("doc_dob"):
            checks.append(("dob", f["dob"] == doc_fields["doc_dob"]))
        if f.get("name") and (doc_fields.get("doc_first_name") or doc_fields.get("doc_last_name")):
            want = _name_tokens(f"{doc_fields.get('doc_first_name', '')} {doc_fields.get('doc_last_name', '')}")
            checks.append(("name", bool(want) and want.issubset(_name_tokens(f["name"]))))
    elif std == "PHILID-QR":
        if f.get("pcn") and doc_fields.get("doc_number"):
            checks.append(("number", _alnum(f["pcn"]) == _alnum(doc_fields["doc_number"])))
        if f.get("dob") and doc_fields.get("doc_dob"):
            checks.append(("dob", f["dob"] == doc_fields["doc_dob"]))
        if f.get("surname") and doc_fields.get("doc_last_name"):
            checks.append(("surname", _alnum(f["surname"]) == _alnum(doc_fields["doc_last_name"])))
    for name_, ok in checks:
        compared += 1
        if not ok:
            mismatches.append(name_)
    return mismatches, compared
