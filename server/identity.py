"""Document-sourced identity (owner's order, 2026-10-26).

The user is "not even supposed to fill my name my date of birth and
all that… i'm only supposed to choose the kind of document i want" —
"OCR fills everything in that's part of what OCR does."

An applicant therefore carries an `identity_source`:

  * "declared" (default, the original behaviour): the tenant declares
    name / DOB up front and the document is CROSS-CHECKED against the
    declaration (server/checks.check_consistency + the data-consistency
    matrix, exactly as before).
  * "document": the tenant declares nothing but the jurisdiction. The
    document itself is the source of identity: the fields read from it
    (template extraction + the check-digit-validated MRZ) become the
    session identity, and at decision time they are written back to
    the applicant record as the verified identity (adoption, in
    server/app.py). Consistency on this path is evaluated across the
    document's OWN reads (server/checks.check_document_self_consistency)
    — an applicant mismatch is impossible because there is no declared
    applicant identity to mismatch.

derive_document_identity() is the single place where the reads are
merged into one identity, with an explicit trust order:

  1. a check-digit-VALID MRZ (mathematically verified, ICAO 9303);
  2. template field extraction (zone / label / text reads of the
     printed zone; a document number only outranks the upload when
     its format/check digit validated);
  3. the document's own machine-readable payload (AAMVA PDF417,
     INEC PVC code, structured QR) — structured data the issuing
     authority encoded on the document itself; it fills only slots
     the printed reads left empty (and, for the number, slots whose
     extraction read failed format validation), and the code_decode
     cross-check still judges it against the printed reads;
  4. the doc_* fields uploaded with the document (the hosted flow no
     longer collects them — the form is gone — but API clients may
     still send them; they are the weakest source, a claim).

Every returned field records which source it came from, so the case
shows WHY the identity says what it says.
"""
import re

from . import checks as C

IDENTITY_SOURCES = ("declared", "document")


def corroborate_name_tokens(value, witness_groups):
    """Drop adopted-name tokens that only ONE reading engine ever saw.

    `witness_groups` is a list of token iterables, one per INDEPENDENT
    reading family (e.g. all Tesseract evidence in one group, all
    Paddle evidence in another). A token survives when at least two
    groups witnessed it — as a whole token, or, for tokens of 4+
    letters, inside a fused token (Paddle systematically fuses
    'Name:VALUE' into one token on form documents).

    Why (owner session 16, 2026-10-29): the adopted given names came
    back 'ZENAS OLATUNDE SSR SAK' — both real names plus two stamp
    glyphs that rode the printed name line. Each stray was seen by
    exactly one engine ('SSR' Tesseract-only, 'SAK' Paddle-only);
    every real name token was seen by both. Ink-verification cannot
    separate them (the stamp IS ink on the line); cross-engine
    corroboration can.

    Conservative by construction: single-token values are untouched
    (a surname stands or falls whole), with fewer than two witness
    groups nothing is dropped (no corroboration exists to appeal
    to), and if dropping would empty the value the original stands.
    """
    if not value:
        return value
    toks = str(value).split()
    if len(toks) < 2:
        return value
    groups = []
    for g in witness_groups or []:
        norm = set()
        for t in g or []:
            nt = re.sub(r"[^A-ZÀ-Þ]", "", str(t).upper())
            if nt:
                norm.add(nt)
        if norm:
            groups.append(norm)
    if len(groups) < 2:
        return value

    def _witnessed(tok):
        nt = re.sub(r"[^A-ZÀ-Þ]", "", str(tok).upper())
        if not nt:
            return 0
        n = 0
        for g in groups:
            if nt in g or (len(nt) >= 4 and any(nt in w for w in g if len(w) > len(nt))):
                n += 1
        return n

    kept = [t for t in toks if _witnessed(t) >= 2]
    if not kept or len(kept) == len(toks):
        return value
    return " ".join(kept)


def _ext(fields, name):
    """One extracted field's value from a field_extraction findings
    dict ({field: {value, source, format_valid?}})."""
    f = (fields or {}).get(name) or {}
    return f.get("value") or None


def _viz_tokens(ocr_text):
    """Tokens of the VISUAL zone only (MRZ lines excluded) — the
    printed name a human reads, as opposed to the machine zone."""
    if not ocr_text:
        return set()
    l1, l2 = C.find_mrz_lines(ocr_text)
    mrz_lines = {C.clean_mrz_line(l1 or ""), C.clean_mrz_line(l2 or "")}
    viz = "\n".join(l for l in ocr_text.splitlines()
                    if C.clean_mrz_line(l) not in mrz_lines and l.strip())
    return C._tokens(viz)


def _corroborated_given_names(value, viz_tokens):
    """Filter an MRZ given-names string to the tokens the VISUAL zone
    corroborates. OCR routinely garbles the MRZ '<' padding run that
    follows the given names into junk letter tokens; adopting those
    would write garbage into the applicant's identity. Tokens the
    printed zone never shows are dropped — but if NONE survive, the
    MRZ value stands as read (transliteration/truncation can make a
    genuine MRZ name differ from the printed one)."""
    if not value or not viz_tokens:
        return value
    toks = value.split()
    keep = [t for t in toks if t.upper() in viz_tokens]
    return " ".join(keep) if keep else value


def derive_document_identity(extracted_fields=None, mrz_parsed=None, uploaded=None, ocr_text="", payload_fields=None):
    """Merge the document reads into one identity.

    extracted_fields: field_extraction findings["fields"] (or None).
    mrz_parsed: checks.parse_mrz output (used only when valid).
    payload_fields: parsed machine-readable payload fields (or None)
    with keys among first_name / surname|last_name / dob / number /
    expiry, dates ISO — see the trust order in the module docstring.
    uploaded: the documents row's client-sent doc_* fields (or None).
    ocr_text: the multi-pass OCR text, used to corroborate MRZ name
    tokens against the visual zone (see _corroborated_given_names).

    -> {"first_name", "last_name", "dob", "number", "expiry",
        "sources": {field: "mrz"|"extraction"|"payload"|"upload"|None},
        "number_format_valid": True|False|None,
        "name_fields_carried": [field names the read was expected to
        produce — the extraction template's name fields, or both when
        a valid MRZ carried the names],
        "any": bool}
    Values are ISO dates / printed-case names, or None when no source
    read them — nothing is ever invented.

    The read-back contract (missing_read_fields) judges the identity
    BY THIS EVIDENCE, not by presence alone: a number the extraction
    read but whose format FAILED validation is stamped
    number_format_valid=False here, so presence of a string in
    "number" can never again masquerade as a successful read (the
    Session-5 diagnosis: the read-back said 'complete' over a number
    that was a format-invalid header token)."""
    extracted_fields = extracted_fields or {}
    uploaded = uploaded or {}
    payload = {}
    if payload_fields:
        payload = {"first_name": payload_fields.get("first_name") or None,
                   "last_name": payload_fields.get("last_name") or payload_fields.get("surname") or None,
                   "dob": payload_fields.get("dob") or None,
                   "number": payload_fields.get("number") or None,
                   "expiry": payload_fields.get("expiry") or None}
    mrz = mrz_parsed if (mrz_parsed and mrz_parsed.get("valid")) else None
    out = {"first_name": None, "last_name": None, "dob": None,
           "number": None, "expiry": None, "sources": {},
           "number_format_valid": None, "name_fields_carried": []}
    # Which name fields was this read expected to produce? The
    # extraction findings carry one entry per template field, so their
    # keys ARE the template's field set; a valid MRZ always encodes
    # surname + given names.
    carried = [f for f in ("surname", "given_names") if f in extracted_fields]
    if mrz and mrz.get("names"):
        carried = ["surname", "given_names"]
    out["name_fields_carried"] = carried

    # ---- names ----
    # Fragment completion: an extraction name that is a strict
    # substring of the payload's name is a PARTIAL read of the same
    # print, not a competing read — the payload completes it below.
    # A genuinely different extraction value stands, and the
    # code_decode cross-check judges the disagreement. (Measured on
    # the genuine INEC card: front OCR kept only the surname's tail
    # fragment while the card's own back code carried it in full.)
    for _field, _pkey in (("surname", "last_name"), ("given_names", "first_name")):
        _ev = _ext(extracted_fields, _field)
        _pv = payload.get(_pkey)
        if _ev and _pv and _ev.upper() != _pv.upper() and _ev.upper() in _pv.upper():
            extracted_fields = dict(extracted_fields)
            _entry = dict(extracted_fields.get(_field) or {})
            _entry["value"] = None
            _entry["fragment_of_payload"] = True
            extracted_fields[_field] = _entry
    if mrz and mrz.get("names"):
        names = mrz["names"]
        if names.get("surname"):
            out["last_name"] = names["surname"]
            out["sources"]["last_name"] = "mrz"
        if names.get("given_names"):
            out["first_name"] = _corroborated_given_names(names["given_names"], _viz_tokens(ocr_text))
            out["sources"]["first_name"] = "mrz"
    if not out["last_name"] and _ext(extracted_fields, "surname"):
        out["last_name"] = _ext(extracted_fields, "surname")
        out["sources"]["last_name"] = "extraction"
    if not out["first_name"] and _ext(extracted_fields, "given_names"):
        out["first_name"] = _ext(extracted_fields, "given_names")
        out["sources"]["first_name"] = "extraction"
    if not out["last_name"] and payload.get("last_name"):
        out["last_name"] = payload["last_name"]
        out["sources"]["last_name"] = "payload"
    if not out["first_name"] and payload.get("first_name"):
        out["first_name"] = payload["first_name"]
        out["sources"]["first_name"] = "payload"
    if not out["last_name"] and uploaded.get("doc_last_name"):
        out["last_name"] = uploaded["doc_last_name"]
        out["sources"]["last_name"] = "upload"
    if not out["first_name"] and uploaded.get("doc_first_name"):
        out["first_name"] = uploaded["doc_first_name"]
        out["sources"]["first_name"] = "upload"

    # ---- date of birth ----
    if mrz:
        d = C.yymmdd_to_date(mrz["dob_yymmdd"], is_dob=True)
        if d:
            out["dob"] = d.isoformat()
            out["sources"]["dob"] = "mrz"
    if not out["dob"] and _ext(extracted_fields, "dob"):
        out["dob"] = _ext(extracted_fields, "dob")
        out["sources"]["dob"] = "extraction"
    if not out["dob"] and payload.get("dob"):
        out["dob"] = payload["dob"]
        out["sources"]["dob"] = "payload"
    if not out["dob"] and uploaded.get("doc_dob"):
        out["dob"] = uploaded["doc_dob"]
        out["sources"]["dob"] = "upload"

    # ---- document number ----
    # A format-validated extraction outranks an unvalidated one; the
    # MRZ number is check-digit validated by construction.
    num_field = (extracted_fields.get("number") or {})
    ext_num = num_field.get("value") or None
    if mrz and mrz.get("document_number"):
        out["number"] = mrz["document_number"]
        out["sources"]["number"] = "mrz"
        out["number_format_valid"] = True   # check-digit validated by construction
    elif ext_num and num_field.get("format_valid") is True:
        out["number"] = ext_num
        out["sources"]["number"] = "extraction"
        out["number_format_valid"] = True
    elif payload.get("number"):
        # Structured payload data outranks a format-INVALID OCR read
        # of the number (and an absent one): the read-back contract
        # already treats a format-failed string as not read. The
        # payload carries no check digit of its own here, so the
        # stamp stays None — presence is not validation.
        out["number"] = payload["number"]
        out["sources"]["number"] = "payload"
        out["number_format_valid"] = None
    elif ext_num:
        # Adopted (it is the only read there is) but stamped with the
        # validation verdict the extraction actually reached — False
        # when the type's format rejected it, None when the type
        # defines no format to judge it by. missing_read_fields
        # treats a False stamp as NOT read.
        out["number"] = ext_num
        out["sources"]["number"] = "extraction"
        out["number_format_valid"] = num_field.get("format_valid")
    elif uploaded.get("doc_number"):
        out["number"] = uploaded["doc_number"]
        out["sources"]["number"] = "upload"

    # ---- expiry ----
    if mrz:
        d = C.yymmdd_to_date(mrz["expiry_yymmdd"])
        if d:
            out["expiry"] = d.isoformat()
            out["sources"]["expiry"] = "mrz"
    if not out["expiry"] and _ext(extracted_fields, "expiry"):
        out["expiry"] = _ext(extracted_fields, "expiry")
        out["sources"]["expiry"] = "extraction"
    if not out["expiry"] and payload.get("expiry"):
        out["expiry"] = payload["expiry"]
        out["sources"]["expiry"] = "payload"
    if not out["expiry"] and uploaded.get("doc_expiry"):
        out["expiry"] = uploaded["doc_expiry"]
        out["sources"]["expiry"] = "upload"

    out["any"] = any(out[k] for k in ("first_name", "last_name", "dob", "number", "expiry"))
    return out


def missing_read_fields(identity, doc_entry=None):
    """The read-back contract for the hosted flow: which REQUIRED
    identity fields the document reads did not produce.

    Name: when the read was expected to produce BOTH name fields
    (identity["name_fields_carried"] — the extraction template
    carries surname AND given_names, or a valid MRZ carried the
    names), BOTH must be present; one name alone is a partial read
    and the applicant rescans. Identity dicts without that evidence
    (hand-built, pre-contract) keep the legacy rule: either name
    satisfies the name requirement.

    Number: presence is not a read. A number stamped
    number_format_valid=False (the type HAS a format/validator and
    the read failed it) is reported missing — the Session-5 defect
    was this function calling a format-invalid header token a
    completed read because a string was present.

    DOB is required only where the document type carries an MRZ —
    the MRZ always encodes a DOB, so a missing DOB there means the
    read failed; paper types that print no DOB (the standard NG NIN
    slip) must never be faulted for not having one."""
    missing = []
    carried = set(identity.get("name_fields_carried") or [])
    if {"surname", "given_names"} <= carried:
        if not identity.get("last_name") or not identity.get("first_name"):
            missing.append("name")
    elif not (identity.get("first_name") or identity.get("last_name")):
        missing.append("name")
    if not identity.get("number") or identity.get("number_format_valid") is False:
        missing.append("number")
    if (doc_entry or {}).get("mrz") and not identity.get("dob"):
        missing.append("dob")
    return missing
