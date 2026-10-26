"""Per-country, per-document registry (owner specification, 2026-10-26).

Every supported document is described by FACTS, not just a name:

    {id, label, sides (1|2), has_expiry (bool), mrz (bool)}

Those facts drive real behaviour:
  * session/document validation (a type not in the registry for the
    issuing country is rejected with 422),
  * the hosted live-scanner flow (a sides:2 document automatically
    prompts for the BACK scan after the front is accepted),
  * the expiry check (a has_expiry:False document — e.g. a Nigerian
    NIN slip, NIN card or voter's card — NEVER fails or goes unclear
    for a missing expiry date; it has none).

Owner-specified facts (2026-10-26): Nigeria — passport, driver's
licence, voter's card (INEC PVC, no expiry), NIN card (no expiry),
NIN slip (no expiry). United States — passport, passport card,
driver's license, state ID. For the other launch countries the
passport / drivers_licence / national_id entries carry best-known
facts (cards: sides 2, has_expiry True; passport data page: sides 1,
MRZ True) pending the owner's per-country research merge.
"""

# Passport: the data page is what is scanned -> sides 1, MRZ True.
_PASSPORT = {"label": "Passport", "sides": 1, "has_expiry": True, "mrz": True}
_CARD_LICENCE = {"label": "Driver's licence", "sides": 2, "has_expiry": True, "mrz": False}
_CARD_ID = {"label": "National ID", "sides": 2, "has_expiry": True, "mrz": False}

DOCUMENT_REGISTRY = {
    "NG": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        "national_id": {"label": "National ID", "sides": 2, "has_expiry": False, "mrz": False},
        "voter_card": {"label": "Voter's card (INEC PVC)", "sides": 2, "has_expiry": False, "mrz": False},
        "nin_card": {"label": "NIN card", "sides": 2, "has_expiry": False, "mrz": False},
        "nin_slip": {"label": "NIN slip", "sides": 1, "has_expiry": False, "mrz": False},
    },
    "US": {
        "passport": dict(_PASSPORT),
        "passport_card": {"label": "Passport card", "sides": 2, "has_expiry": True, "mrz": True},
        "drivers_license": {"label": "Driver's license", "sides": 2, "has_expiry": True, "mrz": False},
        # British-spelling alias kept for API backwards compatibility.
        "drivers_licence": {"label": "Driver's license", "sides": 2, "has_expiry": True, "mrz": False},
        "state_id": {"label": "State ID", "sides": 2, "has_expiry": True, "mrz": False},
        "national_id": dict(_CARD_ID),
    },
    "GB": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE), "national_id": dict(_CARD_ID)},
    "CA": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE), "national_id": dict(_CARD_ID)},
    "AU": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE), "national_id": dict(_CARD_ID)},
    "DE": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE), "national_id": dict(_CARD_ID)},
    "GH": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE), "national_id": dict(_CARD_ID)},
    # Passport-only launch countries (passport accepted everywhere in the
    # launch list — the MRZ is a worldwide standard).
    "KE": {"passport": dict(_PASSPORT)},
    "ZA": {"passport": dict(_PASSPORT)},
    "IN": {"passport": dict(_PASSPORT)},
    "PH": {"passport": dict(_PASSPORT)},
    "SG": {"passport": dict(_PASSPORT)},
    "AE": {"passport": dict(_PASSPORT)},
    "FR": {"passport": dict(_PASSPORT)},
    "NL": {"passport": dict(_PASSPORT)},
    "IE": {"passport": dict(_PASSPORT)},
}

def get_document(country, kind):
    """-> registry entry dict (with 'id') or None."""
    entry = DOCUMENT_REGISTRY.get((country or "").upper(), {}).get(kind or "")
    if entry is None:
        return None
    return {"id": kind, **entry}

def supported_documents():
    """-> {country: set(document_ids)} — the validation view."""
    return {c: set(docs) for c, docs in DOCUMENT_REGISTRY.items()}

def registry_view():
    """-> {country: [entry, ...]} — the flow/UI view (JSON-safe)."""
    return {c: [{"id": k, **v} for k, v in docs.items()] for c, docs in DOCUMENT_REGISTRY.items()}
