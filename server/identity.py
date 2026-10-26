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
  3. the doc_* fields uploaded with the document (the hosted flow no
     longer collects them — the form is gone — but API clients may
     still send them; they are the weakest source, a claim).

Every returned field records which source it came from, so the case
shows WHY the identity says what it says.
"""
from . import checks as C

IDENTITY_SOURCES = ("declared", "document")


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


def derive_document_identity(extracted_fields=None, mrz_parsed=None, uploaded=None, ocr_text=""):
    """Merge the document reads into one identity.

    extracted_fields: field_extraction findings["fields"] (or None).
    mrz_parsed: checks.parse_mrz output (used only when valid).
    uploaded: the documents row's client-sent doc_* fields (or None).
    ocr_text: the multi-pass OCR text, used to corroborate MRZ name
    tokens against the visual zone (see _corroborated_given_names).

    -> {"first_name", "last_name", "dob", "number", "expiry",
        "sources": {field: "mrz"|"extraction"|"upload"|None},
        "any": bool}
    Values are ISO dates / printed-case names, or None when no source
    read them — nothing is ever invented."""
    extracted_fields = extracted_fields or {}
    uploaded = uploaded or {}
    mrz = mrz_parsed if (mrz_parsed and mrz_parsed.get("valid")) else None
    out = {"first_name": None, "last_name": None, "dob": None,
           "number": None, "expiry": None, "sources": {}}

    # ---- names ----
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
    elif ext_num and num_field.get("format_valid") is True:
        out["number"] = ext_num
        out["sources"]["number"] = "extraction"
    elif ext_num:
        out["number"] = ext_num
        out["sources"]["number"] = "extraction"
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
    if not out["expiry"] and uploaded.get("doc_expiry"):
        out["expiry"] = uploaded["doc_expiry"]
        out["sources"]["expiry"] = "upload"

    out["any"] = any(out[k] for k in ("first_name", "last_name", "dob", "number", "expiry"))
    return out


def missing_read_fields(identity, doc_entry=None):
    """The read-back contract for the hosted flow: which REQUIRED
    identity fields the document reads did not produce. Name and
    document number are always required. DOB is required only where
    the document type carries an MRZ — the MRZ always encodes a DOB,
    so a missing DOB there means the read failed; paper types that
    print no DOB (the standard NG NIN slip) must never be faulted
    for not having one."""
    missing = []
    if not (identity.get("first_name") or identity.get("last_name")):
        missing.append("name")
    if not identity.get("number"):
        missing.append("number")
    if (doc_entry or {}).get("mrz") and not identity.get("dob"):
        missing.append("dob")
    return missing
