"""Authoritative-data adapters (Phase 4 WS4) — "stop grading our
own homework": where an official registry offers authorised
access, verify against the SOURCE instead of our own format
rules.

Contract for every adapter: lookup(...) -> {
  "status": "verified" | "not_found" | "name_mismatch" |
            "unavailable" | "not_configured",
  "source": <adapter name>, "checked_at": <iso>,
  "details": {...} }

Fail-closed honesty rules:
  * No credentials configured -> "not_configured". NEVER a
    fabricated "verified".
  * A registry that cannot be reached -> "unavailable", which
    is an availability fact, not a verdict on the business.
  * Only a registry record that exists AND whose name matches
    the claimed legal name earns "verified".

Configured by environment (credentials never in the repo):
  KYC_REGISTRY_GB_KEY   Companies House API key (free, official)
  KYC_REGISTRY_AU_GUID  ABN Lookup GUID (free, official)
NG CAC and NG NIMC have no public self-serve API — access is by
partner/licence agreement; their adapters report not_configured
with that stated plainly until the owner authorises credentials.
"""
import base64
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

COMPANIES_HOUSE_URL = "https://api.company-information.service.gov.uk/company/"
ABN_LOOKUP_URL = "https://abr.business.gov.au/json/AbnDetails.aspx"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _result(status, source, details=None):
    return {"status": status, "source": source, "checked_at": _now(),
            "details": details or {}}


def _norm_name(s):
    return " ".join(str(s or "").upper().replace(".", " ").replace(",", " ").split())


def _name_matches(claimed, official):
    a, b = _norm_name(claimed), _norm_name(official)
    if not a or not b:
        return False
    if a == b:
        return True
    # corporate-suffix tolerance: LTD/LIMITED/PLC/INC/LLC endings
    suffixes = {"LTD", "LIMITED", "PLC", "INC", "LLC", "CO", "COMPANY"}
    ta = [t for t in a.split() if t not in suffixes]
    tb = [t for t in b.split() if t not in suffixes]
    return bool(ta) and ta == tb


def _http_get_json(url, headers=None, timeout=20, fetcher=None):
    """fetcher(url, headers) -> (status, parsed_json) is injectable
    for tests; the default does a real HTTPS GET."""
    if fetcher is not None:
        return fetcher(url, headers or {})
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


# --- business registries -------------------------------------------

def lookup_gb_companies_house(registration_number, legal_name, fetcher=None):
    key = os.environ.get("KYC_REGISTRY_GB_KEY", "").strip()
    if not key:
        return _result("not_configured", "companies_house",
                       {"note": "no Companies House API key configured "
                                "(KYC_REGISTRY_GB_KEY) — the registry is "
                                "not being consulted"})
    auth = base64.b64encode((key + ":").encode()).decode()
    st, body = _http_get_json(COMPANIES_HOUSE_URL + str(registration_number).strip(),
                              {"Authorization": "Basic " + auth}, fetcher=fetcher)
    if st == 404:
        return _result("not_found", "companies_house",
                       {"company_number": registration_number})
    if st != 200 or not body:
        return _result("unavailable", "companies_house", {"http_status": st})
    official = body.get("company_name")
    details = {"company_number": body.get("company_number"),
               "official_name": official,
               "company_status": body.get("company_status"),
               "incorporated": (body.get("date_of_creation"))}
    if not _name_matches(legal_name, official):
        return _result("name_mismatch", "companies_house", details)
    if str(body.get("company_status") or "").lower() not in ("active", ""):
        details["note"] = "company is not in active status at the registry"
        return _result("name_mismatch", "companies_house", details)
    return _result("verified", "companies_house", details)


def lookup_au_abn(registration_number, legal_name, fetcher=None):
    guid = os.environ.get("KYC_REGISTRY_AU_GUID", "").strip()
    if not guid:
        return _result("not_configured", "abn_lookup",
                       {"note": "no ABN Lookup GUID configured "
                                "(KYC_REGISTRY_AU_GUID)"})
    abn = "".join(ch for ch in str(registration_number) if ch.isdigit())
    url = f"{ABN_LOOKUP_URL}?abn={abn}&guid={guid}"
    st, body = _http_get_json(url, fetcher=fetcher)
    if st != 200 or not body:
        return _result("unavailable", "abn_lookup", {"http_status": st})
    if body.get("AbnStatus") != "Active" or not body.get("EntityName"):
        return _result("not_found", "abn_lookup", {"abn": abn})
    details = {"abn": abn, "official_name": body.get("EntityName"),
               "entity_type": body.get("EntityTypeName")}
    if not _name_matches(legal_name, body.get("EntityName")):
        return _result("name_mismatch", "abn_lookup", details)
    return _result("verified", "abn_lookup", details)


def lookup_not_configured(source, note):
    return _result("not_configured", source, {"note": note})


_BUSINESS_ADAPTERS = {
    "GB": lookup_gb_companies_house,
    "AU": lookup_au_abn,
}

_NOT_CONFIGURED_NOTES = {
    "NG": ("cac_nigeria", "the Corporate Affairs Commission offers no public "
           "self-serve API; registry access is by partner agreement — "
           "not authorised yet"),
    "US": ("us_state_registries", "US business registration is state-level "
           "with no single federal API; no state adapter authorised yet"),
    "CA": ("ca_registries", "Canadian federal/provincial registry access "
           "not authorised yet"),
}


def lookup_business(country, registration_number, legal_name, fetcher=None):
    """Route to the country's authoritative adapter. Countries
    without one get an honest not_configured, never a guess."""
    cc = str(country or "").upper()
    fn = _BUSINESS_ADAPTERS.get(cc)
    if fn is not None:
        return fn(registration_number, legal_name, fetcher=fetcher)
    source, note = _NOT_CONFIGURED_NOTES.get(
        cc, ("none", f"no authoritative business registry adapter for {cc or '??'}"))
    return lookup_not_configured(source, note)


# --- national identity ----------------------------------------------

def verify_national_id(country, kind, number, fetcher=None):
    """National-ID verification where authorised. Nigeria first
    per the plan: NIMC verification is licensed-partner only —
    until the owner authorises a partner integration this
    reports not_configured, plainly."""
    cc = str(country or "").upper()
    if cc == "NG":
        return lookup_not_configured(
            "nimc", "NIMC verification is available only through licensed "
                    "partners; no partner integration authorised yet")
    return lookup_not_configured(
        "national_id", f"no national-ID verification integration for {cc or '??'}")
