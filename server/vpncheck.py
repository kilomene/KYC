"""VPN / proxy hard gate (owner's order, 2026-10-26: "VPN or proxy
won't work").

Detection source: ip-api.com IP intelligence (keyless JSON endpoint:
status, countryCode, proxy, hosting, mobile, isp, org, as), cached
per IP in the DB (ip_intel_cache, 24h) so a session costs at most one
lookup. The lookup itself is isolated in _fetch_ip_api so tests mock
it — no test ever touches the network.

Verdicts:
  detected — proxy=true, OR hosting=true on a non-mobile connection.
             The flow BLOCKS at start ("VPN or proxy detected. Turn
             off your VPN or proxy and try again.") and the engine
             hard-rejects any submission under it (reason
             vpn_proxy_detected, server/engine.py HARD_FAIL_REASONS).
  clean    — the lookup ran and neither signal fired.
  unknown  — private/local IP, lookup unreachable, or the service
             answered non-success. NEVER a fake pass: submit records
             vpn_proxy=unclear / vpn_check_unknown. The standard path
             may proceed (a free intel endpoint being down must not
             mass-block applicants), but nobody claims it passed.

Corroboration, recorded but never independently fatal: the device
timezone the flow page reports (Intl.DateTimeFormat) is mapped to a
country and compared with the IP country and the declared country.
Travel makes timezone/IP disagreement legitimate, so a mismatch is
evidence in the case file — not a block. The flow's WebRTC local-IP
probe is likewise recorded only (and modern browsers usually mask it
behind an mDNS name anyway).

Honest limit: IP intelligence is a database, not ground truth —
residential proxies and fresh VPN ranges can evade it.
"""
import json, urllib.request
from datetime import datetime, timedelta, timezone

from .db import now_iso

FIELDS = "status,countryCode,proxy,hosting,mobile,isp,org,as,query"
CACHE_TTL = timedelta(hours=24)

# Device-timezone -> country for the launch set (+ common zones).
# Corroboration only; see module docstring.
TZ_COUNTRY = {
    "Africa/Lagos": "NG", "Africa/Accra": "GH", "Africa/Nairobi": "KE",
    "Africa/Johannesburg": "ZA",
    "Europe/London": "GB", "Europe/Berlin": "DE", "Europe/Munich": "DE",
    "Europe/Paris": "FR", "Europe/Amsterdam": "NL", "Europe/Dublin": "IE",
    "America/New_York": "US", "America/Detroit": "US", "America/Chicago": "US",
    "America/Denver": "US", "America/Phoenix": "US", "America/Los_Angeles": "US",
    "America/Anchorage": "US", "Pacific/Honolulu": "US",
    "America/Toronto": "CA", "America/Vancouver": "CA", "America/Winnipeg": "CA",
    "America/Halifax": "CA", "America/St_Johns": "CA", "America/Montreal": "CA",
    "Australia/Sydney": "AU", "Australia/Melbourne": "AU", "Australia/Brisbane": "AU",
    "Australia/Perth": "AU", "Australia/Adelaide": "AU", "Australia/Hobart": "AU",
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Manila": "PH",
    "Asia/Singapore": "SG", "Asia/Dubai": "AE",
}

def tz_to_country(tz):
    return TZ_COUNTRY.get(tz or "")

def _is_private(ip):
    if not ip:
        return True
    s = str(ip)
    if s in ("::1", "localhost"):
        return True
    parts = s.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10 or a == 127 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254):
            return True
    return False

def _fetch_ip_api(ip):
    """The ONLY network call in this module (mocked in tests)."""
    url = f"http://ip-api.com/json/{ip}?fields={FIELDS}"
    req = urllib.request.Request(url, headers={"User-Agent": "kyc-local/0.4 (vpn-proxy-check)"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def verdict_from_intel(d):
    """Pure: intel dict -> 'detected' | 'clean' | 'unknown'."""
    if not isinstance(d, dict) or d.get("status") != "success":
        return "unknown"
    if d.get("proxy"):
        return "detected"
    if d.get("hosting") and not d.get("mobile"):
        return "detected"
    return "clean"

def check_ip(db, ip, device_tz=None, declared_country=None, fetcher=None):
    """-> {"verdict", "ip_country", "findings"}.

    Uses the per-IP DB cache (24h) before any network call. `fetcher`
    is injectable for tests; production uses _fetch_ip_api."""
    tz_country = tz_to_country(device_tz)
    findings = {"source": None, "device_tz": device_tz, "tz_country": tz_country}
    if _is_private(ip):
        findings["source"] = "private_or_missing_ip"
        return {"verdict": "unknown", "ip_country": None, "findings": findings}
    intel = None
    row = db.one("SELECT * FROM ip_intel_cache WHERE ip=?", (ip,))
    fresh = False
    if row:
        try:
            fresh = (datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])) < CACHE_TTL
        except Exception:
            fresh = False
    if row and fresh:
        intel = {"status": row["status"], "countryCode": row["country"], "proxy": bool(row["proxy"]),
                 "hosting": bool(row["hosting"]), "mobile": bool(row["mobile"]),
                 "isp": row["isp"], "org": row["org"], "as": row["asn"]}
        findings["source"] = "ip-api.com (cached)"
    else:
        fetch = fetcher or _fetch_ip_api
        try:
            intel = fetch(ip)
        except Exception as e:
            findings["source"] = "ip-api.com"
            findings["lookup_error"] = str(e)[:120]
            return {"verdict": "unknown", "ip_country": None, "findings": findings}
        findings["source"] = "ip-api.com"
        if isinstance(intel, dict) and intel.get("status") == "success":
            db.execute("INSERT OR REPLACE INTO ip_intel_cache(ip,status,country,proxy,hosting,mobile,isp,org,asn,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (ip, intel.get("status"), intel.get("countryCode"), 1 if intel.get("proxy") else 0,
                        1 if intel.get("hosting") else 0, 1 if intel.get("mobile") else 0,
                        intel.get("isp"), intel.get("org"), intel.get("as"), now_iso()))
    verdict = verdict_from_intel(intel)
    ip_country = intel.get("countryCode") if isinstance(intel, dict) else None
    if isinstance(intel, dict):
        findings.update({"intel_country": ip_country, "isp": intel.get("isp"), "org": intel.get("org"),
                         "asn": intel.get("as"), "proxy": bool(intel.get("proxy")),
                         "hosting": bool(intel.get("hosting")), "mobile": bool(intel.get("mobile"))})
    findings["tz_mismatch_ip"] = bool(tz_country and ip_country and tz_country != ip_country)
    findings["tz_mismatch_declared"] = bool(tz_country and declared_country and tz_country != declared_country.upper())
    return {"verdict": verdict, "ip_country": ip_country, "findings": findings}
