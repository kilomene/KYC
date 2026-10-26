"""Per-country, per-document registry (owner specification, 2026-10-26).

Every supported document is described by FACTS, not just a name:

    {id, label, sides (1|2), has_expiry (bool), mrz (bool), aspect}

plus, where the research supports them, honest extra facts:
    validity_end  ISO date after which the document TYPE stops being
                  legally valid even though no expiry is printed on it
                  (ZA green ID book: invalid after 2028-03-31). The
                  expiry/validity check honours it.
    note          a researched caveat the code or a reviewer must know
                  (holder-dependent expiry branches, MRZ-on-the-back,
                  printed dates that understate validity, ...). Notes
                  are evidence labelling, never silently enforced rules
                  the pipeline cannot actually evaluate.

Those facts drive real behaviour:
  * session/document validation (a type not in the registry for the
    issuing country is rejected with 422),
  * the hosted live-scanner flow (a sides:2 document automatically
    prompts for the BACK scan after the front is accepted),
  * the expiry check (a has_expiry:False document — e.g. a Nigerian
    NIN slip, NIN card or voter's card — NEVER fails or goes unclear
    for a missing expiry date; it has none; a validity_end, where
    present, IS enforced as a document-validity window),
  * the live scanner's document detector: `aspect` is the document's
    width/height ratio (ISO/IEC 7810 ID-1 cards = 1.586, passport data
    page ~1.42, NIN slip / A-series paper ~1.41). The scanner only
    auto-captures when a detected quadrilateral matches this ratio —
    a still, textured room can no longer pass as a document.

Facts come from research/*.md (researched 2026-10-26, sources named
there); nothing in this registry is invented. `mrz` means "an MRZ is
read from the FRONT capture the pipeline OCRs" — documents whose MRZ
lives on the BACK (DE/NL identity cards, GH Ghana Card, KE 2nd-gen ID,
IE passport card) carry mrz:False here with a note, because claiming
the front pipeline reads a back-side MRZ would be false. (The US
passport card predates this convention in the registry; its entry is
unchanged from the Phase 1-3 build.)

Owner-specified facts (2026-10-26): Nigeria — passport, driver's
licence, voter's card (INEC PVC, no expiry), NIN card (no expiry),
NIN slip (no expiry). United States — passport, passport card,
driver's license, state ID. Passports are supported for every launch
country. A general national identity card is listed only where that
document class exists (NG, DE, GH, NL, FR, KE, ZA, IN, PH, SG, AE);
the US/GB/CA/AU get their researched state/provincial photo cards as
distinct types instead (WS0 claims audit, 2026-10-26). Phase 4 WS1
(2026-10-26) merged the researched types for KE/ZA/IN/PH/SG/AE/FR/NL/IE
and the AU/CA photo cards from research/*.md.
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
    "GB": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        # PASS proof-of-age card (CitizenCard): cards issued before
        # 2021-01-07 do NOT expire; later cards expire 3 years after
        # issue. The printed date governs where one is printed.
        "pass_card": {"label": "PASS proof-of-age card", "sides": 1, "has_expiry": True, "mrz": False, "aspect": 1.586,
                      "note": "Cards issued before 2021-01-07 do not expire; later cards expire 3 years after issue."},
    },
    "CA": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        "photo_card": {"label": "Provincial photo card", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                       "note": "Provincial non-driver photo card (e.g. Ontario Photo Card, BCID); typically 5-year validity, New Brunswick 4 years."},
    },
    "AU": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        "photo_card": {"label": "State photo card", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                       "note": "State/territory photo card; validity varies by state (NSW 5/10y, QLD 10y, NT/TAS/WA 5y); VIC Proof of Age, SA Proof of Age and ACT Proof of Identity cards carry NO expiry."},
    },
    "DE": {
        "passport": dict(_PASSPORT),
        "drivers_licence": {**_CARD_LICENCE, "note": "EU card licence document valid 15 years; pre-2013 paper/card licences carry no printed expiry (mandatory exchange by 2033-01-19)."},
        "national_id": {**_CARD_ID, "note": "Personalausweis: TD1 MRZ and address are on the BACK; the front pipeline does not read the back MRZ."},
    },
    "GH": {
        "passport": dict(_PASSPORT),
        "drivers_licence": dict(_CARD_LICENCE),
        # Ghana Card: citizens 10 years; the non-citizen FIMS card is
        # 1 year — the printed expiry governs either way.
        "national_id": {**_CARD_ID, "label": "Ghana Card (National ID)",
                        "note": "Ghana Card: chip + MRZ + 2D barcode are on the BACK; citizen cards valid 10 years, non-citizen (FIMS) cards 1 year — the printed expiry governs."},
        "voter_card": {"label": "Voter ID card", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 1.46,
                       "note": "EC voter ID: no printed expiry (register-dependent validity); laminated paper card ~95x65mm."},
    },
    "KE": {
        "passport": dict(_PASSPORT),
        # Two generations in parallel with OPPOSITE expiry logic
        # (research/docs-africa.md) — keyed as separate types.
        "national_id": {"label": "National ID (2nd generation)", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                        "note": "2nd-generation card: NO expiry date; an MRZ is printed on the BACK (not read by the front pipeline)."},
        "maisha_card": {"label": "Maisha Card (3rd generation ID)", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                        "note": "3rd-generation Maisha Card: 10-year validity, chip-based."},
        "drivers_licence": {"label": "Smart driving licence", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                            "note": "NTSA smart driving licence: standard validity 3 years, chip on card."},
    },
    "ZA": {
        "passport": dict(_PASSPORT),
        # Smart ID: research finds NO printed expiry (the widely
        # repeated '10 years' is the card's physical lifespan) — so
        # has_expiry is False until a specimen/DHA ruling says else.
        "smart_id": {"label": "Smart ID card", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                     "note": "No expiry date is printed on the card; DHA publishes no renewal cycle (secondary '10-year' claims appear to be physical lifespan)."},
        # Green ID book: no printed expiry BUT legally invalid after
        # 2028-03-31 (DHA phase-out) — a document-type validity window,
        # enforced by the expiry/validity check via validity_end.
        "green_id_book": {"label": "Green ID book", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 1.42,
                          "validity_end": "2028-03-31",
                          "note": "Bar-coded green ID book: no printed expiry, but not recognised as valid ID after 2028-03-31 (DHA phase-out; production ends 2027-03-31)."},
        "drivers_licence": {"label": "Driving licence card", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                            "note": "Licence CARD valid 5 years (the underlying licence itself does not expire)."},
    },
    "IN": {
        "passport": dict(_PASSPORT),
        "aadhaar": {"label": "Aadhaar", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                    "note": "Valid for life; no expiry exists or is printed. Carries a UIDAI-signed secure QR (offline structural validation only — see server/payloads.py)."},
        "pan_card": {"label": "PAN card", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 1.586,
                     "note": "Valid for lifetime per the Income Tax Department; may become inoperative if unlinked from Aadhaar (a status, not an expiry)."},
        "drivers_licence": dict(_CARD_LICENCE),
        "voter_id": {"label": "Voter ID (EPIC)", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586},
    },
    "PH": {
        "passport": dict(_PASSPORT),
        # PhilID holder branch (research/docs-asia-pacific.md): citizens
        # = lifetime (no expiry printed); resident aliens = 1 year with
        # a printed expiry. The registry default is the citizen rule;
        # a printed expiry, where one exists, is still validated by the
        # expiry check's date logic — recorded here as the honest fact.
        "philid": {"label": "PhilID (National ID)", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                   "note": "Citizens: lifetime validity, no expiry printed. Resident aliens: 1-year validity with a printed expiry — the branch is holder-dependent and cannot be told from the card type alone."},
        "umid": {"label": "UMID", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                 "note": "Unified Multi-Purpose ID: lifetime validity while membership is active; chip + magnetic stripe."},
        "drivers_licence": {"label": "Driver's license", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                            "note": "LTO licence: 5 years on first issuance, 10 years on renewal with no recorded violations."},
    },
    "SG": {
        "passport": dict(_PASSPORT),
        "nric": {"label": "NRIC", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                 "note": "No expiry date is printed; holders re-register at age 30 and 55 (a duty, not an expiry). Pink = citizen, blue = permanent resident."},
        "drivers_licence": {"label": "Driving licence", "sides": 2, "has_expiry": False, "mrz": False, "aspect": 1.586,
                            "note": "Citizens/PRs: valid for life, no expiry date. Foreigners: up to 5 years — holder-dependent branch."},
    },
    "AE": {
        "passport": dict(_PASSPORT),
        "emirates_id": {"label": "Emirates ID", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                        "note": "Always expires: citizens 21+ 10 years, under-21 5 years, resident expatriates tied to the residence visa (typically 2-3 years). 15-digit ID number is permanent across renewals."},
        "drivers_licence": dict(_CARD_LICENCE),
    },
    "FR": {
        "passport": dict(_PASSPORT),
        "national_id": {**_CARD_ID, "label": "National ID card (CNI)",
                        "note": "Old-format CNI issued 2004-2013 to adults was automatically extended +5 years beyond the PRINTED expiry; the new CNIe (since 2021) prints a reliable 10-year expiry and carries a TD1 MRZ on the back."},
        "drivers_licence": {**_CARD_LICENCE, "label": "Driver's licence",
                            "note": "Card licence (since 2013): 15 years for categories A/B. The old pink paper licence has NO expiry (lifetime; mandatory replacement by 2033-01-19) — a pink-paper holder must not be failed for a missing expiry date."},
    },
    "NL": {
        "passport": dict(_PASSPORT),
        "national_id": {**_CARD_ID, "note": "Identiteitskaart: TD1 MRZ and BSN are on the BACK; the front pipeline does not read the back MRZ."},
        "drivers_licence": {**_CARD_LICENCE, "note": "Rijbewijs: 10 years under 65; shorter cycles at older ages (70+ 5 years)."},
    },
    "IE": {
        "passport": dict(_PASSPORT),
        "passport_card": {"label": "Passport card", "sides": 2, "has_expiry": True, "mrz": False, "aspect": 1.586,
                          "note": "MRZ is on the BACK. Valid at most 5 years and never beyond the linked passport book's expiry."},
        "drivers_licence": dict(_CARD_LICENCE),
        "age_card": {"label": "National Age Card", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 1.586,
                     "note": "Garda Age Card: NO expiry date by design; proof-of-age document (lower assurance)."},
    },
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
