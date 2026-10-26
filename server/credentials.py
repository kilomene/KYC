"""Reusable verified credential (Phase 3, the AMBITION differentiator).

On approval the platform issues a signed credential: JSON claims plus an
HMAC-SHA256 signature under a platform secret that lives ONLY in
<data_dir>/platform_secret.key (generated on first use, mode 0600,
inside gitignored data/). Claims carry NO document data:

    {credential_id, applicant_ref, level, country, over_18,
     issued_at, expires_at, checks_passed[]}

applicant_ref is the issuing tenant's own applicant id (an opaque UUID —
tenant-scoped, meaningless outside that tenant). Any tenant can VERIFY
a credential (signature + live status in our DB + expiry) and receives
only the claims — selective disclosure by construction.
face_match and liveness are NEVER inherited from a credential: even when
listed in checks_passed they are excluded from inheritance, because a
credential proves a past verification, not a present live human.
"""
import hashlib, hmac, json, os, secrets
from datetime import datetime, timedelta, timezone

from .db import new_id, now_iso

# document_framing joins the biometrics here: it is evidence about ONE
# capture in ONE session (a card filled that frame), not a portable
# fact about the person — a credential must never satisfy it for a new
# session. It is likewise excluded from the claims' checks_passed at
# issuance (see NON_PORTABLE below).
NEVER_INHERITED = {"face_match", "liveness", "document_framing"}
NON_PORTABLE = {"document_framing"}
DEFAULT_TTL_DAYS = 180

def platform_secret(data_dir):
    path = os.path.join(data_dir, "platform_secret.key")
    if os.path.isfile(path):
        with open(path) as f:
            return f.read().strip()
    os.makedirs(data_dir, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret)
    return secret

def _sign(secret, claims):
    body = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def issue_credential(db, data_dir, tenant_id, env, applicant, session, checks_passed, ttl_days=DEFAULT_TTL_DAYS, expires_at=None):
    """Create + store a credential for an approved session. Returns the
    credential object {"claims": {...}, "signature": ...}."""
    now = datetime.now(timezone.utc)
    exp = expires_at or (now + timedelta(days=ttl_days)).isoformat()
    dob = applicant["dob"]
    over_18 = None
    if dob:
        try:
            y, m, d = (int(x) for x in dob.split("-"))
            age = now.year - y - ((now.month, now.day) < (m, d))
            over_18 = age >= 18
        except Exception:
            over_18 = None
    claims = {"credential_id": new_id(), "applicant_ref": applicant["id"],
              "level": session["level"], "country": applicant["country"],
              "over_18": over_18, "issued_at": now.isoformat(), "expires_at": exp,
              "checks_passed": sorted(set(checks_passed) - NON_PORTABLE)}
    secret = platform_secret(data_dir)
    sig = _sign(secret, claims)
    db.execute("INSERT INTO credentials(id,tenant_id,env,applicant_id,session_id,claims,signature,status,issued_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
               (claims["credential_id"], tenant_id, env, applicant["id"], session["id"],
                json.dumps(claims), sig, "active", claims["issued_at"], exp))
    return {"claims": claims, "signature": sig}

def verify_credential(db, data_dir, credential):
    """-> {valid, reason, claims}. Checks structure, signature, DB status
    (exists + not revoked) and expiry. Deliberately env-agnostic: a
    credential issued in test is stamped with its claims; DB lookup is by
    credential_id either way."""
    if not isinstance(credential, dict) or "claims" not in credential or "signature" not in credential:
        return {"valid": False, "reason": "malformed_credential", "claims": None}
    claims = credential["claims"]
    secret = platform_secret(data_dir)
    expected = _sign(secret, claims)
    if not hmac.compare_digest(expected, str(credential["signature"])):
        return {"valid": False, "reason": "bad_signature", "claims": None}
    row = db.one("SELECT * FROM credentials WHERE id=?", (claims.get("credential_id", ""),))
    if not row:
        return {"valid": False, "reason": "unknown_credential", "claims": None}
    if row["status"] != "active":
        return {"valid": False, "reason": "revoked", "claims": None}
    if row["expires_at"] < now_iso():
        return {"valid": False, "reason": "expired", "claims": None}
    return {"valid": True, "reason": None, "claims": json.loads(row["claims"])}

def inheritable_checks(claims, required):
    """Checks a valid credential can satisfy for a new session: those it
    lists as passed, minus biometrics (never inherited)."""
    passed = set(claims.get("checks_passed") or [])
    return [c for c in required if c in passed and c not in NEVER_INHERITED]
