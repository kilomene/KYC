"""Per-country, per-document registry (owner specification, 2026-10-26).

Every supported document is described by FACTS, not just a name:

    {id, label, sides (1|2), has_expiry (bool), mrz (bool), aspect}

Those facts drive real behaviour:
  * session/document validation (a type not in the registry for the
    issuing country is rejected with 422),
  * the hosted live-scanner flow (a sides:2 document automatically
    prompts for the BACK scan after the front is accepted),
  * the expiry check (a has_expiry:False document — e.g. a Nigerian
    NIN slip, NIN card or voter's card — NEVER fails or goes unclear
    for a missing expiry date; it has none),
  * the live scanner's document detector: `aspect` is the document's
    width/height ratio (ISO/IEC 7810 ID-1 cards = 1.586, passport data
    page ~1.42, NIN slip / A-series paper ~1.41). The scanner only
    auto-captures when a detected quadrilateral matches this ratio —
    a still, textured room can no longer pass as a document.

Owner-specified facts (2026-10-26): Nigeria — passport, driver's
licence, voter's card (INEC PVC, no expiry), NIN card (no expiry),
NIN slip (no expiry). United States — passport, passport card,
driver's license, state ID. Passports are supported for every launch
country. Driver's licences are also listed for GB/CA/AU/DE/GH using
generic ID-1 card facts pending the Phase 4 WS1 per-country template
merge. A general national identity card is listed only where that
document class exists in the launch set (NG national ID, DE national
ID, GH Ghana Card). The United States, United Kingdom, Canada and
Australia do not get a generic "national_id" entry: US state IDs and
the other countries' state/provincial photo cards are distinct
document classes and must be added as researched types, not relabelled
as national IDs (WS0 claims audit, 2026-10-26).
"""

# Passport: the data page is what is scanned -> sides 1, MRZ True.
_PASSPORT = {"label": "Passport", "sides": 1, "has_expiry": True, "mrz": True, "aspect": 1.42}
_CARD_LICENCE = {"label": "Driver's licence", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586}
_CARD_ID = {"label": "National ID", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586}

DOCUMENT_REGISTRY = {
    "NG": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        "national_id": {"label": "National ID", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586},
        "voter_card": {"label": "Voter's card (INEC PVC)", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586},
        "nin_card": {"label": "NIN card", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586},
        "nin_slip": {"label": "NIN slip", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 1.41},
    },
    "US": {
        "passport": dict(_PASSPORT),
        "passport_card": {"label": "Passport card", "sides": 2, "has_expiry": True, "mrz": True, "aspect": 1.586},
        "drivers_license": {"label": "Driver's license", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586},
        # British-spelling alias kept for API backwards compatibility.
        "drivers_licence": {"label": "Driver's license", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586},
        "state_id": {"label": "State ID", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586},
    },
    "GB": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE)},
    "CA": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE)},
    "AU": {"passport": dict(_PASSPORT), "drivers_licence": dict(_CARD_LICENCE)},
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
