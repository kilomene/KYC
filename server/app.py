"""HTTP server: API + hosted flow + console, stdlib http.server (threaded).

Auth model:
  * Tenant APIs:  Authorization: Bearer <api_key>  (only the sha256 hash is stored)
  * Hosted flow:  Authorization: Bearer <flow_token> on /v1/flow/* (hash stored)
  * Tenant creation requires the platform operator token
    (KYC_PLATFORM_ADMIN_TOKEN env var, X-Platform-Admin header); with no
    token configured it is disabled entirely (WS0 audit fix, 2026-10-26).
"""
import hashlib, json, os, re, secrets
import threading, traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import CONSENT_TEXT_VERSION, RULES_VERSION
from .db import DB, new_id, now_iso, row_to_dict
from . import checks as C
from . import framing as FRAMING
from . import docregistry as DOCREG
from .engine import decide, required_for, verification_layers, biometric_evidence, document_evidence, face_match_applicable
from . import webhooks as WH
from . import face as FACE
from . import liveness as LV
from . import authenticity as AUTH
from . import risk as RISK
from . import screening as SCR
from . import credentials as CRED
from . import flowconfig as FC
from . import assist as ASSIST
from . import monitoring as MON
from . import vpncheck as VPN
from . import vision as VISION
from . import deepfake as DEEPFAKE
from . import facetrack as FACETRACK
from . import templates as TEMPLATES
from . import fieldtemplates as FIELDTEMPLATES
from . import storage as STORAGE
from . import mfa as MFA
from . import ratelimit as RL
from . import identity as IDENTITY

# KYB registry-number FORMAT rules per country (Phase 3). Format
# validation only — the local build has NO live government registry
# connection; a reviewer confirms the registry check (see /registry).
REGISTRY_FORMATS = {
    "NG": (r"^(RC)?\d{6,8}$", "RC + 6-8 digits (e.g. RC1234567)"),
    "US": (r"^\d{2}-\d{7}$", "EIN format NN-NNNNNNN"),
    "GB": (r"^[A-Z0-9]{8}$", "8-character company number"),
    "CA": (r"^\d{9}$", "9-digit business number"),
    "AU": (r"^\d{11}$", "11-digit ABN"),
    "DE": (r"^HRB\s?\d{4,6}$", "HRB + 4-6 digits"),
    "GH": (r"^[A-Z0-9]{8,12}$", "8-12 alphanumeric characters"),
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Settled, owner-expanded launch coverage (DECISIONS D3, 2026-10-26),
# refined 2026-10-26 by the owner's per-country document specification:
# the source of truth is now the per-country, per-document REGISTRY in
# server/docregistry.py — every document carries facts (sides,
# has_expiry, mrz) that drive validation, the live-scanner flow (back
# side prompt) and the expiry check. Passport is accepted for EVERY
# launch country (the MRZ is a worldwide standard).
LAUNCH_COUNTRIES = tuple(DOCREG.DOCUMENT_REGISTRY.keys())
LICENCE_ID_COUNTRIES = {"NG", "US", "GB", "CA", "AU", "DE", "GH"}
SUPPORTED_DOCUMENTS = DOCREG.supported_documents()
# Backwards-readable alias used by the flow endpoints.
ALLOWED_DOCS = SUPPORTED_DOCUMENTS

def parse_capture_meta(raw):
    """Parse the capture_meta multipart field (JSON) the live scanner
    sends. Client-claimed metadata: recorded as evidence, never trusted
    as proof on its own. Returns a dict (possibly empty)."""
    if not raw:
        return {}
    try:
        meta = json.loads(raw)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}

def _keep_client_signals(meta_in, capture_meta):
    """Carry the browser's client_signals (deepfake defence: camera
    track label + device-motion telemetry) from the client's
    capture_meta into the stored record — whitelisted and truncated;
    the values are evidence for server/deepfake.py, never trusted."""
    cs = meta_in.get("client_signals")
    if not isinstance(cs, dict):
        return
    clean = {}
    if isinstance(cs.get("track_label"), str):
        clean["track_label"] = cs["track_label"][:160]
    m = cs.get("motion")
    if isinstance(m, dict):
        clean["motion"] = {k: m[k] for k in ("sensor_present", "samples", "variance")
                           if isinstance(m.get(k), (int, float, bool))}
    if clean:
        capture_meta["client_signals"] = clean

def sha256(s): return hashlib.sha256(s.encode()).hexdigest()
def iso_in(hours): return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

# ---------------- multipart (minimal, stdlib-free-parser) ----------------
def parse_multipart(body, content_type):
    """Parse multipart/form-data into {name: {filename, content_type, data}}.
    Binary-safe for images: parts are split on the boundary bytes."""
    m = re.search(r"boundary=(.+)$", content_type or "")
    if not m: return {}
    boundary = ("--" + m.group(1).strip().strip('"')).encode()
    parts = {}
    for chunk in body.split(boundary):
        if not chunk or chunk in (b"--\r\n", b"--", b"\r\n"): continue
        if chunk.startswith(b"\r\n"): chunk = chunk[2:]
        if chunk.endswith(b"--"): chunk = chunk[:-2]
        if chunk.endswith(b"\r\n"): chunk = chunk[:-2]
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep: continue
        if data.endswith(b"\r\n"): data = data[:-2]
        headers = head.decode("utf-8", "replace")
        nm = re.search(r'name="([^"]+)"', headers)
        if not nm: continue
        fn = re.search(r'filename="([^"]*)"', headers)
        ct = re.search(r"Content-Type:\s*(\S+)", headers, re.I)
        parts[nm.group(1)] = {"filename": fn.group(1) if fn else None,
                              "content_type": ct.group(1) if ct else None, "data": data}
    return parts

def field_text(parts, name):
    p = parts.get(name)
    if p is None: return None
    return p["data"].decode("utf-8", "replace") if isinstance(p["data"], bytes) else p["data"]

def mask_ip(ip):
    """Partially mask an IP for display and check findings: an IPv4
    address keeps its first two octets (41.203.x.x); anything else
    keeps a short prefix. The full IP stays on the session row."""
    if not ip:
        return None
    parts = str(ip).split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{parts[1]}.x.x"
    s = str(ip)
    return s[:6] + "…" if len(s) > 6 else s

def _json_default(o):
    """json.dumps fallback for numpy-typed values in check findings.

    The face track's findings carry numpy scalars (float32 cosine
    scores, int64 counts): plain json.dumps raises TypeError on them,
    which killed the decision pipeline mid-pass in production
    (2026-10-26 16:57 PDT — record("face_track", ...) crashed and the
    session was orphaned in 'processing'). Duck-typed on purpose —
    numbers ABCs cover numpy's registered scalar types, .item()
    covers the rest (incl. np.bool_), .tolist() covers arrays — so
    app.py needs no numpy import.
    """
    import numbers
    if isinstance(o, bool):
        return bool(o)
    if isinstance(o, numbers.Integral):
        return int(o)
    if isinstance(o, numbers.Real):
        return float(o)
    item = getattr(o, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    tolist = getattr(o, "tolist", None)
    if callable(tolist):
        try:
            return tolist()
        except Exception:
            pass
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

class _SubmitRejected(Exception):
    """A pre-decision rejection raised inside the decision pipeline
    (HTTP status + message). The submit wrapper pre-checks these
    synchronously, so inside the background worker this is only a
    safety net; the worker treats it like any pipeline failure and
    reverts the session's claim to a retryable state."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

class Ctx:
    def __init__(self, db): self.db = db

def make_handler(db: DB, data_dir: str):
    limiter = RL.RateLimiter()
    rl_limits = RL.limits_from_env(os.environ)
    def max_body_bytes():
        try:
            return int(os.environ.get("KYC_MAX_BODY_BYTES") or 25 * 1024 * 1024)
        except ValueError:
            return 25 * 1024 * 1024
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # ---- plumbing ----
        def log_message(self, *a): pass
        def _send(self, code, body, ctype="application/json", headers=None):
            if isinstance(body, (dict, list)): body = json.dumps(body).encode()
            if isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(body)
        def _err(self, code, msg, code_str=None):
            self._send(code, {"error": {"code": code_str or str(code), "message": msg}})
        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""
        def _json(self):
            try: return json.loads(self._body() or b"{}")
            except Exception: return {}
        # ---- auth ----
        def _tenant(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "): return None
            key = auth[7:].strip()
            row = db.one("SELECT k.*, t.status AS tenant_status FROM api_keys k JOIN tenants t ON t.id=k.tenant_id WHERE k.key_hash=?", (sha256(key),))
            if not row or row["revoked_at"] or row["tenant_status"] != "active": return None
            db.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (now_iso(), row["id"]))
            return row
        def _reviewer(self, tid, env):
            """Reviewer identity from the X-Reviewer-Key header (a named
            per-user token issued by POST /v1/users). Falls back to the
            tenant API key itself as identity 'api-key' (Phase 1/2
            behaviour, kept so existing integrations keep working)."""
            token = self.headers.get("X-Reviewer-Key", "")
            if token:
                row = db.one("SELECT * FROM tenant_users WHERE token_hash=? AND tenant_id=? AND env=?", (sha256(token), tid, env))
                if row and not row["revoked_at"]:
                    keys = row.keys()
                    return {"identity": f"user:{row['id']}", "name": row["name"], "role": row["role"], "user_id": row["id"],
                            "mfa_enabled": bool(row["mfa_enabled"]) if "mfa_enabled" in keys else False,
                            "totp_secret": row["totp_secret"] if "totp_secret" in keys else None,
                            "mfa_last_counter": (row["mfa_last_counter"] if "mfa_last_counter" in keys else -1)}
                return None  # a presented-but-invalid reviewer token is an auth failure, not a fallback
            return {"identity": "api-key", "name": "tenant-api-key", "role": "admin", "user_id": None,
                    "mfa_enabled": False, "totp_secret": None, "mfa_last_counter": -1}

        def _mfa_gate(self, reviewer):
            """WS3 reviewer MFA gate for PRIVILEGED actions (case
            decide/confirm, hit disposition, KYB registry decision).
            Returns None when the action may proceed, else an error
            response. Policy (docs/SECURITY.md): MFA-enabled reviewers
            must present a valid, non-replayed X-Reviewer-TOTP code;
            when the operator sets KYC_REQUIRE_REVIEWER_MFA=1, reviewers
            who have not enrolled are refused until they enrol. The
            tenant API-key fallback identity is the tenant admin
            credential itself and is not TOTP-gated."""
            if not reviewer or reviewer.get("user_id") is None:
                return None
            if reviewer.get("mfa_enabled"):
                code = self.headers.get("X-Reviewer-TOTP", "")
                matched = MFA.verify(reviewer.get("totp_secret"), code,
                                     last_counter=reviewer.get("mfa_last_counter", -1))
                if matched is None:
                    return self._err(401, "a valid MFA code (X-Reviewer-TOTP) is required for this action", "mfa_required_or_invalid")
                db.execute("UPDATE tenant_users SET mfa_last_counter=? WHERE id=?", (matched, reviewer["user_id"]))
                return None
            if os.environ.get("KYC_REQUIRE_REVIEWER_MFA") in ("1", "true", "yes"):
                return self._err(403, "MFA enrolment is required before privileged reviewer actions on this deployment", "mfa_enrollment_required")
            return None
        def _flow_session(self):
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.startswith("Bearer ") else self.headers.get("X-Flow-Token", "")
            if not token: return None
            row = db.one("SELECT * FROM sessions WHERE token_hash=?", (sha256(token),))
            if not row: return None
            if row["expires_at"] < now_iso() and row["status"] in ("created", "in_progress"):
                db.execute("UPDATE sessions SET status='expired', updated_at=? WHERE id=?", (now_iso(), row["id"]))
                return None
            if row["status"] in ("cancelled", "expired"): return None
            return row
        def _client_geo(self):
            """Client IP + IP country for the location check (owner's
            order, 2026-10-26: 'apart from the camera we harvest their
            IP address'). Through the tunnel the Worker stamps
            X-Client-IP (from CF-Connecting-IP) and X-IP-Country (from
            request.cf.country); direct edge connections may carry
            CF-Connecting-IP / CF-IPCountry; a local/dev connection has
            only the socket peer and NO country — unknown, which the
            location check records honestly and never as a mismatch."""
            h = self.headers
            ip = (h.get("X-Client-IP") or h.get("CF-Connecting-IP")
                  or (h.get("X-Forwarded-For") or "").split(",")[0].strip()
                  or (self.client_address[0] if self.client_address else None))
            country = ((h.get("X-IP-Country") or h.get("CF-IPCountry") or "").strip().upper() or None)
            return {"ip": ip, "country": country, "user_agent": h.get("User-Agent", "")}

        # ---- WS3 gates: body size + rate limits ----
        def _preflight(self, p):
            """Returns an error response to send, or None to proceed.
            Body size is refused BEFORE the body is read into memory;
            rate limits are per-IP plus per-API-key / per-flow-token
            (identity = hash of the presented credential, so unknown
            keys are throttled too). 429s carry Retry-After."""
            if self.command in ("POST", "PUT"):
                try: n = int(self.headers.get("Content-Length") or 0)
                except ValueError: n = 0
                if n > max_body_bytes():
                    self.close_connection = True
                    return self._err(413, "request body too large", "body_too_large")
            if p.startswith("/v1/"):
                ip = self._client_geo()["ip"] or "unknown"
                ok, retry = limiter.check("ip:" + ip, rl_limits["ip_per_min"], rl_limits["window"])
                if not ok:
                    return self._send(429, {"error": {"code": "rate_limited", "message": "rate limit exceeded (per-IP)"}},
                                      headers={"Retry-After": retry})
                auth = self.headers.get("Authorization", "")
                cred = auth[7:].strip() if auth.startswith("Bearer ") else (self.headers.get("X-Flow-Token", "") or "anon")
                if p.startswith("/v1/flow/"):
                    ok, retry = limiter.check("flow:" + sha256(cred), rl_limits["flow_per_min"], rl_limits["window"])
                else:
                    ok, retry = limiter.check("key:" + sha256(cred), rl_limits["api_per_min"], rl_limits["window"])
                if not ok:
                    return self._send(429, {"error": {"code": "rate_limited", "message": "rate limit exceeded"}},
                                      headers={"Retry-After": retry})
            return None

        def _fs(self, rel):
            """Filesystem path holding PLAINTEXT for the check pipeline
            (WS3 encryption at rest): the real path for a plaintext
            file, a per-request decrypted temp copy for an encrypted
            one. Temp copies are deleted by do_POST's finally block."""
            path, is_temp = STORAGE.materialize(data_dir, rel)
            if is_temp:
                self._tmp_paths.append(path)
            return path

        # ================= GET =================
        def do_GET(self):
            p = urlparse(self.path).path
            try:
                gate = self._preflight(p)
                if gate is not None: return gate
                return self._get(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")
        def _get(self, p):
            if p == "/" or p == "/index.html": return self._static("index.html")
            if p == "/console": return self._static("console.html")
            if p.startswith("/flow/"): return self._static("flow.html")
            if p.startswith("/voice/"): return self._static(p)
            if p.startswith("/public/"): return self._static(p[len("/public/"):])
            if p == "/healthz": return self._send(200, {"ok": True})
            # flow info
            if p == "/v1/flow/session":
                s = self._flow_session()
                if not s: return self._err(401, "invalid or expired flow token")
                app = db.one("SELECT id,first_name,last_name,dob,country,identity_source FROM applicants WHERE id=?", (s["applicant_id"],))
                docs = db.all("SELECT id,kind,issuing_country, storage_path IS NOT NULL AS has_front, back_storage_path IS NOT NULL AS has_back, capture_meta FROM documents WHERE session_id=?", (s["id"],))
                bio = db.all("SELECT id, media_kind FROM biometric_captures WHERE session_id=?", (s["id"],))
                challenge = None
                try: challenge = json.loads(s["liveness_challenge"] or "null")
                except Exception: challenge = None
                issued = db.one("SELECT id FROM credentials WHERE session_id=? AND status='active'", (s["id"],))
                return self._send(200, {"session": {"id": s["id"], "level": s["level"], "status": s["status"], "env": s["env"],
                                                     "consent_at": s["consent_at"], "credential_session": bool(s["credential_id"]),
                                                     "vpn_status": (s["vpn_status"] if "vpn_status" in s.keys() else None)},
                                        "applicant": row_to_dict(app), "documents": [row_to_dict(d, ("capture_meta",)) for d in docs],
                                        "document_registry": DOCREG.registry_view(),
                                        "selfie_uploaded": any(b["media_kind"] == "selfie" for b in bio),
                                        "liveness_uploaded": any(b["media_kind"] == "liveness_video" for b in bio),
                                        "liveness_challenge": challenge,
                                        "poa_uploaded": any(d["kind"] == "proof_of_address" for d in docs),
                                        "credential_issued": bool(issued),
                                        "allowed_docs": {k: sorted(v) for k, v in ALLOWED_DOCS.items()},
                                        "consent_text_version": CONSENT_TEXT_VERSION})
            if p == "/v1/flow/credential":
                s = self._flow_session()
                if not s: return self._err(401, "invalid or expired flow token")
                row = db.one("SELECT * FROM credentials WHERE session_id=? AND applicant_id=? ORDER BY issued_at DESC LIMIT 1", (s["id"], s["applicant_id"]))
                if not row: return self._err(404, "no credential issued for this session")
                return self._send(200, {"credential": {"claims": json.loads(row["claims"]), "signature": row["signature"]},
                                        "status": row["status"]})
            # tenant APIs
            t = self._tenant()
            if p.startswith("/v1/"):
                if not t: return self._err(401, "bad, revoked, or missing API key")
                tid, env = t["tenant_id"], t["env"]
                if p == "/v1/keys":
                    rows = db.all("SELECT id,tenant_id,env,key_prefix,created_at,last_used_at,revoked_at FROM api_keys WHERE tenant_id=?", (tid,))
                    return self._send(200, {"keys": [row_to_dict(r) for r in rows]})
                if p == "/v1/webhooks":
                    rows = db.all("SELECT id,url,events,created_at FROM webhook_endpoints WHERE tenant_id=? AND env=?", (tid, env))
                    return self._send(200, {"endpoints": [row_to_dict(r, ("events",)) for r in rows]})
                if p == "/v1/webhooks/deliveries":
                    from urllib.parse import parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    status_filter = (q.get("status") or [None])[0]
                    if status_filter:
                        rows = db.all("SELECT d.* FROM webhook_deliveries d JOIN webhook_endpoints e ON e.id=d.endpoint_id "
                                      "WHERE d.tenant_id=? AND e.env=? AND d.status=? ORDER BY d.created_at DESC LIMIT 200",
                                      (tid, env, status_filter))
                    else:
                        rows = db.all("SELECT d.* FROM webhook_deliveries d JOIN webhook_endpoints e ON e.id=d.endpoint_id "
                                      "WHERE d.tenant_id=? AND e.env=? ORDER BY d.created_at DESC LIMIT 200", (tid, env))
                    return self._send(200, {"deliveries": [row_to_dict(r) for r in rows]})
                m = re.match(r"^/v1/applicants/([\w-]+)$", p)
                if m:
                    r = db.one("SELECT * FROM applicants WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                    if not r: return self._err(404, "not found")
                    db.audit("tenant", tid, tid, "applicant.view", "applicant", r["id"])
                    return self._send(200, row_to_dict(r))
                m = re.match(r"^/v1/sessions/([\w-]+)(/checks)?$", p)
                if m:
                    r = db.one("SELECT * FROM sessions WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                    if not r: return self._err(404, "not found")
                    if m.group(2):
                        rows = db.all("SELECT * FROM checks WHERE session_id=? ORDER BY created_at", (r["id"],))
                        return self._send(200, {"checks": [row_to_dict(x, ("findings", "reason_codes")) for x in rows]})
                    return self._send(200, self._session_view(r))
                if p == "/v1/sessions":
                    rows = db.all("SELECT * FROM sessions WHERE tenant_id=? AND env=? ORDER BY created_at DESC", (tid, env))
                    return self._send(200, {"sessions": [self._session_view(r) for r in rows]})
                if p == "/v1/config":
                    from urllib.parse import parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    try: level = int((q.get("level") or ["2"])[0])
                    except Exception: return self._err(422, "level must be 1, 2 or 3")
                    if level not in (1, 2, 3): return self._err(422, "level must be 1, 2 or 3")
                    cfg, version = FC.get_config(db, tid, env, level)
                    return self._send(200, {"level": level, "version": version, "config": cfg})
                if p == "/v1/users":
                    rows = db.all("SELECT id,name,role,token_prefix,created_at,revoked_at FROM tenant_users WHERE tenant_id=? AND env=? ORDER BY created_at", (tid, env))
                    return self._send(200, {"users": [row_to_dict(r) for r in rows]})
                if p == "/v1/businesses":
                    rows = db.all("SELECT * FROM businesses WHERE tenant_id=? AND env=? ORDER BY created_at DESC", (tid, env))
                    return self._send(200, {"businesses": [self._business_view(r, brief=True) for r in rows]})
                m = re.match(r"^/v1/businesses/([\w-]+)$", p)
                if m:
                    biz = db.one("SELECT * FROM businesses WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                    if not biz: return self._err(404, "not found")
                    return self._send(200, self._business_view(biz))
                if p == "/v1/monitoring/alerts":
                    rows = db.all("SELECT * FROM monitoring_alerts WHERE tenant_id=? AND env=? ORDER BY created_at DESC", (tid, env))
                    return self._send(200, {"alerts": [row_to_dict(r) for r in rows]})
                m = re.match(r"^/v1/sessions/([\w-]+)/credential$", p)
                if m:
                    r = db.one("SELECT * FROM sessions WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                    if not r: return self._err(404, "not found")
                    cred = db.one("SELECT * FROM credentials WHERE session_id=? ORDER BY issued_at DESC LIMIT 1", (r["id"],))
                    if not cred: return self._err(404, "no credential issued for this session")
                    return self._send(200, {"credential": {"claims": json.loads(cred["claims"]), "signature": cred["signature"]},
                                            "status": cred["status"]})
                if p == "/v1/cases":
                    # Queue sorts by SLA due time (soonest first), then age.
                    rows = db.all("SELECT * FROM cases WHERE tenant_id=? AND env=? ORDER BY (sla_due_at IS NULL), sla_due_at ASC, created_at DESC", (tid, env))
                    out = []
                    for c in rows:
                        s = db.one("SELECT level,status FROM sessions WHERE id=?", (c["session_id"],))
                        out.append({**row_to_dict(c), "level": s["level"] if s else None, "session_status": s["status"] if s else None})
                    return self._send(200, {"cases": out})
                m = re.match(r"^/v1/cases/([\w-]+)$", p)
                if m:
                    c = db.one("SELECT * FROM cases WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                    if not c: return self._err(404, "not found")
                    return self._send(200, self._case_view(c))
                m = re.match(r"^/v1/documents/([\w-]+)/image$", p)
                if m: return self._image("documents", m.group(1), tid, env)
                m = re.match(r"^/v1/biometrics/([\w-]+)/image$", p)
                if m: return self._image("biometric_captures", m.group(1), tid, env)
                return self._err(404, "not found")
            return self._err(404, "not found")

        def _static(self, name):
            name = os.path.basename(name)
            # Voice clips live one level down (public/voice/<key>.mp3);
            # they are the only subdirectory files served.
            if self.path.split("?")[0].startswith("/voice/") and name.endswith(".mp3"):
                fp = os.path.join(PUBLIC_DIR, "voice", name)
            else:
                fp = os.path.join(PUBLIC_DIR, name)
            if not os.path.isfile(fp): return self._err(404, "not found")
            ctype = "text/html" if name.endswith(".html") else "text/plain"
            if name.endswith(".js"): ctype = "application/javascript"
            if name.endswith(".css"): ctype = "text/css"
            if name.endswith(".mp3"): ctype = "audio/mpeg"
            with open(fp, "rb") as f: data = f.read()
            # HTML pages are never cached: the hosted flow must always run
            # the exact page version that matches the server's endpoints
            # (a stale cached flow page once called an endpoint the running
            # server did not have yet, mid-ship — owner's live test hit it).
            # Voice clips are immutable per key and cache hard.
            hdrs = {"Cache-Control": "no-store"} if ctype == "text/html" else \
                   {"Cache-Control": "public, max-age=86400"} if ctype == "audio/mpeg" else None
            self._send(200, data, ctype, headers=hdrs)

        def _session_view(self, s):
            d = db.one("SELECT * FROM decisions WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (s["id"],))
            rows = db.all("SELECT type,status FROM checks WHERE session_id=?", (s["id"],))
            summary = {}
            for r in rows: summary[r["type"]] = r["status"]
            dec = row_to_dict(d, ("reason_codes", "risk_contributions")) if d else None
            client_ip = s["client_ip"] if "client_ip" in s.keys() else None
            ip_country = s["ip_country"] if "ip_country" in s.keys() else None
            vpn_status = s["vpn_status"] if "vpn_status" in s.keys() else None
            app_src = db.one("SELECT identity_source FROM applicants WHERE id=?", (s["applicant_id"],))
            out = {"id": s["id"], "tenant_id": s["tenant_id"], "env": s["env"], "applicant_id": s["applicant_id"],
                   "identity_source": (app_src["identity_source"] if app_src and app_src["identity_source"] else "declared"),
                   "level": s["level"], "status": s["status"], "expires_at": s["expires_at"], "created_at": s["created_at"],
                   "client_ip_masked": mask_ip(client_ip), "ip_country": ip_country, "vpn_status": vpn_status,
                   "checks_summary": summary, "decision": dec}
            return out

        def _business_view(self, biz, brief=False):
            out = row_to_dict(biz)
            people = db.all("SELECT bp.*, a.first_name, a.last_name, a.country AS applicant_country FROM business_people bp JOIN applicants a ON a.id=bp.applicant_id WHERE bp.business_id=?", (biz["id"],))
            plist = []
            for per in people:
                best = db.one("SELECT status, level FROM sessions WHERE applicant_id=? ORDER BY level DESC, created_at DESC LIMIT 1", (per["applicant_id"],))
                approved_l2 = db.one("SELECT id FROM sessions WHERE applicant_id=? AND status='approved' AND level>=2 LIMIT 1", (per["applicant_id"],))
                plist.append({**row_to_dict(per), "verification": (row_to_dict(best) if best else None),
                              "verified_l2plus": bool(approved_l2)})
            out["people"] = plist
            if not brief:
                docs = db.all("SELECT id,kind,created_at, storage_path IS NOT NULL AS has_file FROM business_documents WHERE business_id=?", (biz["id"],))
                out["documents"] = [row_to_dict(d) for d in docs]
                hits = db.all("SELECT * FROM screening_hits WHERE business_id=? ORDER BY created_at", (biz["id"],))
                out["screening_hits"] = [row_to_dict(h) for h in hits]
            return out

        def _issue_credential_for(self, session_row):
            """Issue a reusable credential for an approved session (once)."""
            existing = db.one("SELECT id FROM credentials WHERE session_id=? AND status='active'", (session_row["id"],))
            if existing: return None
            app = db.one("SELECT * FROM applicants WHERE id=?", (session_row["applicant_id"],))
            if not app: return None
            passed = [r["type"] for r in db.all("SELECT DISTINCT type FROM checks WHERE session_id=? AND status='pass'", (session_row["id"],))]
            cred = CRED.issue_credential(db, data_dir, session_row["tenant_id"], session_row["env"], app, session_row, passed)
            db.audit("system", None, session_row["tenant_id"], "credential.issue", "credential", cred["claims"]["credential_id"],
                     metadata={"session_id": session_row["id"], "level": session_row["level"]})
            return cred

        def _case_view(self, c):
            # PII view: audited.
            db.audit("tenant", c["tenant_id"], c["tenant_id"], "case.view", "case", c["id"])
            s = db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],))
            app = db.one("SELECT * FROM applicants WHERE id=?", (s["applicant_id"],)) if s else None
            docs = db.all("SELECT id,kind,issuing_country,doc_first_name,doc_last_name,doc_dob,doc_number,doc_expiry,ocr_text,mrz_raw,capture_meta,storage_path IS NOT NULL AS has_front, back_storage_path IS NOT NULL AS has_back FROM documents WHERE session_id=?", (c["session_id"],))
            bio = db.all("SELECT id, media_kind, capture_meta, storage_path IS NOT NULL AS has_image FROM biometric_captures WHERE session_id=?", (c["session_id"],))
            chks = db.all("SELECT * FROM checks WHERE session_id=? ORDER BY created_at", (c["session_id"],))
            doc_list = []
            for d in docs:
                dd = row_to_dict(d, ("capture_meta",))
                dd["image_url"] = f"/v1/documents/{d['id']}/image"
                if d["has_back"]:
                    dd["back_image_url"] = f"/v1/documents/{d['id']}/image?side=back"
                doc_list.append(dd)
            bio_list = []
            for b in bio:
                bd = row_to_dict(b, ("capture_meta",))
                bio_list.append({"id": b["id"], "media_kind": b["media_kind"], "capture_meta": bd.get("capture_meta"),
                                 "has_image": bool(b["has_image"]), "image_url": f"/v1/biometrics/{b['id']}/image"})
            check_dicts = [row_to_dict(x, ("findings", "reason_codes")) for x in chks]
            results_map = {}
            for x in check_dicts:
                results_map[x["type"]] = {"status": x["status"], "reason_codes": x["reason_codes"], "findings": x["findings"]}
            hits = db.all("SELECT * FROM screening_hits WHERE session_id=? ORDER BY created_at", (c["session_id"],))
            pending_hits = sum(1 for h in hits if h["status"] == "pending")
            cfg, _ver = FC.get_config(db, c["tenant_id"], c["env"], s["level"] if s else 2)
            assist = ASSIST.build_assist(results_map, required_for(s["level"] if s else 2, cfg), pending_hits=pending_hits) if s else None
            cred = db.one("SELECT id,status,claims FROM credentials WHERE session_id=? ORDER BY issued_at DESC LIMIT 1", (c["session_id"],))
            return {"case": row_to_dict(c), "session": self._session_view(s) if s else None,
                    "applicant": row_to_dict(app), "documents": doc_list, "biometrics": bio_list,
                    "checks": check_dicts, "screening_hits": [row_to_dict(h) for h in hits],
                    "assist": assist,
                    "credential": ({"id": cred["id"], "status": cred["status"], "claims": json.loads(cred["claims"])} if cred else None)}

        def _image(self, table, rid, tid, env):
            from urllib.parse import parse_qs
            side = (parse_qs(urlparse(self.path).query).get("side") or ["front"])[0]
            r = db.one(f"SELECT * FROM {table} WHERE id=? AND tenant_id=? AND env=?", (rid, tid, env))
            if not r: return self._err(404, "not found")
            rel = r["back_storage_path"] if (table == "documents" and side == "back") else r["storage_path"]
            if not rel: return self._err(404, "not found")
            fp = os.path.join(data_dir, rel)
            if not os.path.isfile(fp): return self._err(404, "file gone")
            db.audit("tenant", tid, tid, "image.view", table, rid)  # audited view; served directly, no persistent URL
            try:
                data = STORAGE.read_file(data_dir, rel)  # decrypts transparently when WS3 encryption is on
            except STORAGE.StorageKeyMissing:
                return self._err(503, "stored file is encrypted and no master key is configured on this server", "storage_unavailable")
            except STORAGE.StorageError as e:
                return self._err(500, f"stored file cannot be decrypted: {e}", "storage_error")
            self._send(200, data, "image/jpeg")

        # ================= POST / DELETE =================
        def do_POST(self):
            p = urlparse(self.path).path
            self._tmp_paths = []
            try:
                gate = self._preflight(p)
                if gate is not None: return gate
                return self._post(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")
            finally:
                for t in getattr(self, "_tmp_paths", []):
                    try: os.remove(t)
                    except OSError: pass
                self._tmp_paths = []
        def do_DELETE(self):
            p = urlparse(self.path).path
            try:
                gate = self._preflight(p)
                if gate is not None: return gate
                return self._delete(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")
        def do_PUT(self):
            p = urlparse(self.path).path
            try:
                gate = self._preflight(p)
                if gate is not None: return gate
                return self._put(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")

        def _put(self, p):
            t = self._tenant()
            if not t: return self._err(401, "bad, revoked, or missing API key")
            tid, env = t["tenant_id"], t["env"]
            if p == "/v1/config":
                b = self._json()
                level = b.get("level")
                if level not in (1, 2, 3): return self._err(422, "level must be 1, 2 or 3")
                patch = b.get("config")
                clean, err = FC.validate_config_patch(patch if isinstance(patch, dict) else {})
                if err: return self._err(422, err)
                if not clean: return self._err(422, "empty config patch")
                cfg, version = FC.put_config(db, tid, env, level, clean)
                db.audit("tenant", tid, tid, "config.put", "flow_config", f"{level}@v{version}", metadata={"version": version})
                return self._send(200, {"level": level, "version": version, "config": cfg})
            return self._err(404, "not found")

        def _delete(self, p):
            t = self._tenant()
            if not t: return self._err(401, "bad, revoked, or missing API key")
            m = re.match(r"^/v1/applicants/([\w-]+)$", p)
            if not m: return self._err(404, "not found")
            tid, env = t["tenant_id"], t["env"]
            r = db.one("SELECT * FROM applicants WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
            if not r: return self._err(404, "not found")
            # Erasure: delete files for all sessions of this applicant, null PII.
            sessions = db.all("SELECT id FROM sessions WHERE applicant_id=?", (r["id"],))
            deleted_files = 0
            for s in sessions:
                for table in ("documents", "biometric_captures"):
                    for row in db.all(f"SELECT storage_path, back_storage_path FROM {table} WHERE session_id=?" if table == "documents" else f"SELECT storage_path, NULL AS back_storage_path FROM {table} WHERE session_id=?", (s["id"],)):
                        for col in ("storage_path", "back_storage_path"):
                            if row[col]:
                                fp = os.path.join(data_dir, row[col])
                                if os.path.isfile(fp): os.remove(fp); deleted_files += 1
                        db.execute(f"UPDATE {table} SET storage_path=NULL{', back_storage_path=NULL' if table=='documents' else ''} WHERE session_id=?", (s["id"],))
                db.execute("UPDATE documents SET ocr_text=NULL, mrz_raw=NULL, doc_first_name=NULL, doc_last_name=NULL, doc_dob=NULL, doc_number=NULL, doc_expiry=NULL WHERE session_id=?", (s["id"],))
            db.execute("UPDATE applicants SET first_name=NULL,last_name=NULL,dob=NULL,email=NULL,phone=NULL,external_ref=NULL,data_deleted_at=?,updated_at=? WHERE id=?",
                       (now_iso(), now_iso(), r["id"]))
            db.execute("INSERT INTO deletions(tenant_id,target_type,target_id,kind,detail,at) VALUES(?,?,?,?,?,?)",
                       (tid, "applicant", r["id"], "erasure", f"files_deleted={deleted_files}", now_iso()))
            db.audit("tenant", tid, tid, "applicant.erasure", "applicant", r["id"], metadata={"files_deleted": deleted_files})
            WH.fire(db, tid, env, "applicant.deleted", {"applicant_id": r["id"], "files_deleted": deleted_files})
            return self._send(200, {"deleted": True, "applicant_id": r["id"], "files_deleted": deleted_files})

        def _post(self, p):
            # --- tenant bootstrap (platform-operator gated) ---
            # WS0 audit fix (2026-10-26): this endpoint was unauthenticated
            # in the local MVP and stayed open after the service went live —
            # anyone could mint a tenant and live API keys. It now requires
            # the platform operator token from the KYC_PLATFORM_ADMIN_TOKEN
            # environment variable (X-Platform-Admin header). When the env
            # var is unset, tenant creation is disabled entirely (fail
            # closed). The token is never stored in the repo or database.
            if p == "/v1/tenants":
                admin_token = os.environ.get("KYC_PLATFORM_ADMIN_TOKEN", "")
                presented = self.headers.get("X-Platform-Admin", "")
                if not admin_token or not secrets.compare_digest(presented, admin_token):
                    return self._err(403, "tenant creation is restricted to the platform operator", "tenant_bootstrap_restricted")
                b = self._json()
                if not b.get("name"): return self._err(422, "name required")
                tid = new_id()
                db.execute("INSERT INTO tenants(id,name,country,created_at) VALUES(?,?,?,?)", (tid, b["name"], b.get("country"), now_iso()))
                out = {"tenant": {"id": tid, "name": b["name"]}, "keys": {}}
                for env in ("test", "live"):
                    raw = f"kyc_{env}_" + secrets.token_urlsafe(24)
                    kid = new_id()
                    db.execute("INSERT INTO api_keys(id,tenant_id,env,key_hash,key_prefix,created_at) VALUES(?,?,?,?,?,?)",
                               (kid, tid, env, sha256(raw), raw[:14], now_iso()))
                    out["keys"][env] = {"id": kid, "key": raw, "note": "shown once — store it now"}
                db.audit("platform", None, tid, "tenant.create", "tenant", tid)
                return self._send(201, out)
            # --- flow endpoints (flow-token auth) ---
            if p.startswith("/v1/flow/"):
                s = self._flow_session()
                if not s: return self._err(401, "invalid or expired flow token")
                return self._flow_post(p, s)
            # --- tenant-auth endpoints ---
            t = self._tenant()
            if not t: return self._err(401, "bad, revoked, or missing API key")
            tid, env = t["tenant_id"], t["env"]
            if p == "/v1/applicants":
                b = self._json()
                # Identity source (owner's order, 2026-10-26): with
                # identity_source="document" the tenant declares NO
                # name/DOB — the applicant only picks a document and
                # OCR reads the identity from it; the extracted fields
                # are adopted onto this record at decision time. The
                # declared path (default) is unchanged: name, DOB and
                # country are all required and the document is
                # cross-checked against them.
                identity_source = b.get("identity_source") or "declared"
                if identity_source not in IDENTITY.IDENTITY_SOURCES:
                    return self._err(422, "identity_source must be 'declared' or 'document'")
                if identity_source == "declared":
                    if not b.get("first_name") or not b.get("last_name") or not b.get("dob") or not b.get("country"):
                        return self._err(422, "first_name, last_name, dob, country required")
                elif not b.get("country"):
                    return self._err(422, "country required (name and date of birth are read from the document on the document path)")
                aid = new_id()
                db.execute("INSERT INTO applicants(id,tenant_id,env,external_ref,first_name,last_name,dob,country,email,phone,address_line,city,identity_source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (aid, tid, env, b.get("external_ref"), b.get("first_name"), b.get("last_name"), b.get("dob"), b["country"], b.get("email"), b.get("phone"), b.get("address_line"), b.get("city"), identity_source, now_iso(), now_iso()))
                db.audit("tenant", tid, tid, "applicant.create", "applicant", aid,
                         metadata={"identity_source": identity_source})
                return self._send(201, row_to_dict(db.one("SELECT * FROM applicants WHERE id=?", (aid,))))
            if p == "/v1/sessions":
                b = self._json()
                level = b.get("level")
                if level not in (1, 2, 3): return self._err(422, "level must be 1, 2 or 3")
                credential = b.get("credential")
                cred_claims = None; cred_id = None
                if credential is not None:
                    # Reusable verified credential path (Phase 3): the
                    # credential must verify live. Its inheritable checks
                    # are recorded as passed BY the credential at creation.
                    v = CRED.verify_credential(db, data_dir, credential)
                    if not v["valid"]: return self._err(422, f"credential not usable: {v['reason']}")
                    cred_claims = v["claims"]; cred_id = cred_claims["credential_id"]
                    if cred_claims["level"] < level:
                        return self._err(422, "credential level below requested level")
                app = None
                if b.get("applicant_id"):
                    app = db.one("SELECT * FROM applicants WHERE id=? AND tenant_id=? AND env=?", (b.get("applicant_id", ""), tid, env))
                    if not app: return self._err(404, "applicant not found")
                elif cred_claims:
                    # Selective disclosure: the presenting tenant learns
                    # only the claims; a local applicant shell is created.
                    aid = new_id()
                    db.execute("INSERT INTO applicants(id,tenant_id,env,external_ref,country,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                               (aid, tid, env, cred_claims["applicant_ref"], cred_claims["country"], now_iso(), now_iso()))
                    app = db.one("SELECT * FROM applicants WHERE id=?", (aid,))
                elif b.get("identity_source") == "document":
                    # Document-sourced session in one call (owner's
                    # order): NO pre-declared name/DOB exists to send —
                    # a document-sourced applicant shell is created
                    # (country = the jurisdiction whose document the
                    # applicant will pick) and the identity is read
                    # from the document during the flow.
                    if not b.get("country"):
                        return self._err(422, "country required for a document-sourced session (name and date of birth are read from the document)")
                    aid = new_id()
                    db.execute("INSERT INTO applicants(id,tenant_id,env,external_ref,country,identity_source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                               (aid, tid, env, b.get("external_ref"), b["country"], "document", now_iso(), now_iso()))
                    app = db.one("SELECT * FROM applicants WHERE id=?", (aid,))
                    db.audit("tenant", tid, tid, "applicant.create", "applicant", aid,
                             metadata={"identity_source": "document", "via": "session.create"})
                else:
                    return self._err(422, "applicant_id or credential required")
                if app["data_deleted_at"]: return self._err(422, "applicant erased")
                sid = new_id(); token = secrets.token_urlsafe(32)
                hours = int(b.get("expires_hours") or 24)
                db.execute("INSERT INTO sessions(id,tenant_id,env,applicant_id,level,status,token_hash,expires_at,credential_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (sid, tid, env, app["id"], level, "created", sha256(token), iso_in(hours), cred_id, now_iso(), now_iso()))
                inherited = []
                if cred_claims:
                    cfg, _v = FC.get_config(db, tid, env, level)
                    for ctype in CRED.inheritable_checks(cred_claims, cfg["required_checks"]):
                        db.execute("INSERT INTO checks(id,session_id,tenant_id,env,type,provider,status,findings,reason_codes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (new_id(), sid, tid, env, ctype, "verified_credential", "pass",
                                    json.dumps({"credential_id": cred_id, "note": "satisfied by verified credential; biometrics are never inherited"}),
                                    json.dumps([]), now_iso()))
                        inherited.append(ctype)
                db.audit("tenant", tid, tid, "session.create", "session", sid,
                         metadata={"credential_id": cred_id, "inherited_checks": inherited} if cred_id else None)
                return self._send(201, {"id": sid, "level": level, "env": env, "status": "created",
                                        "applicant_id": app["id"],
                                        "identity_source": (app["identity_source"] if "identity_source" in app.keys() else "declared"),
                                        "flow_url": f"/flow/{token}", "flow_token": token, "expires_at": iso_in(hours),
                                        "credential_id": cred_id, "inherited_checks": inherited})
            m = re.match(r"^/v1/sessions/([\w-]+)/cancel$", p)
            if m:
                r = db.one("SELECT * FROM sessions WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not r: return self._err(404, "not found")
                db.execute("UPDATE sessions SET status='cancelled', token_hash=NULL, updated_at=? WHERE id=?", (now_iso(), r["id"]))
                db.audit("tenant", tid, tid, "session.cancel", "session", r["id"])
                return self._send(200, {"cancelled": True})
            m = re.match(r"^/v1/keys/([\w-]+)/revoke$", p)
            if m:
                r = db.one("SELECT * FROM api_keys WHERE id=? AND tenant_id=?", (m.group(1), tid))
                if not r: return self._err(404, "not found")
                db.execute("UPDATE api_keys SET revoked_at=? WHERE id=?", (now_iso(), r["id"]))
                db.audit("tenant", tid, tid, "key.revoke", "api_key", r["id"])
                return self._send(200, {"revoked": True})
            if p == "/v1/webhooks":
                b = self._json()
                if not b.get("url"): return self._err(422, "url required")
                wid = new_id(); secret = "whsec_" + secrets.token_urlsafe(24)
                db.execute("INSERT INTO webhook_endpoints(id,tenant_id,env,url,secret,events,created_at) VALUES(?,?,?,?,?,?,?)",
                           (wid, tid, env, b["url"], secret, json.dumps(b.get("events") or []), now_iso()))
                db.audit("tenant", tid, tid, "webhook.create", "webhook_endpoint", wid)
                return self._send(201, {"id": wid, "url": b["url"], "secret": secret, "note": "secret shown once"})
            # --- tenant users / reviewer identities (Phase 3) ---
            if p == "/v1/users":
                b = self._json()
                if not b.get("name") or b.get("role") not in ("admin", "reviewer"):
                    return self._err(422, "name and role (admin|reviewer) required")
                uid = new_id(); raw = "kyc_user_" + secrets.token_urlsafe(24)
                db.execute("INSERT INTO tenant_users(id,tenant_id,env,name,role,token_hash,token_prefix,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (uid, tid, env, b["name"], b["role"], sha256(raw), raw[:16], now_iso()))
                db.audit("tenant", tid, tid, "user.create", "tenant_user", uid, metadata={"role": b["role"]})
                return self._send(201, {"id": uid, "name": b["name"], "role": b["role"], "token": raw,
                                        "note": "shown once — this token identifies the reviewer via the X-Reviewer-Key header"})
            m = re.match(r"^/v1/users/([\w-]+)/revoke$", p)
            if m:
                r = db.one("SELECT * FROM tenant_users WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not r: return self._err(404, "not found")
                db.execute("UPDATE tenant_users SET revoked_at=? WHERE id=?", (now_iso(), r["id"]))
                db.audit("tenant", tid, tid, "user.revoke", "tenant_user", r["id"])
                return self._send(200, {"revoked": True})
            # --- reviewer MFA enrolment / confirm / reset (WS3) ---
            # Tenant-admin (API key) managed. The secret is returned
            # ONCE at enrolment; MFA activates only after the user
            # proves possession with a valid code (confirm). Reset is
            # the recovery path and FAILS CLOSED: it clears the secret
            # and disables MFA — the user must re-enrol; there is no
            # bypass code and a reviewer token cannot reset its own MFA
            # (these endpoints require the tenant API key).
            m = re.match(r"^/v1/users/([\w-]+)/mfa/(enroll|confirm|reset)$", p)
            if m:
                r = db.one("SELECT * FROM tenant_users WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not r: return self._err(404, "not found")
                action = m.group(2)
                if action == "enroll":
                    if r["revoked_at"]: return self._err(409, "user is revoked")
                    secret = MFA.new_secret()
                    db.execute("UPDATE tenant_users SET totp_secret=?, mfa_enabled=0, mfa_last_counter=-1 WHERE id=?",
                               (secret, r["id"]))
                    db.audit("tenant", tid, tid, "user.mfa_enroll", "tenant_user", r["id"])
                    return self._send(200, {"user_id": r["id"], "mfa": "pending_confirmation",
                                            "secret": secret,
                                            "otpauth_uri": MFA.provisioning_uri(secret, r["name"]),
                                            "note": "secret shown once — confirm with a current TOTP code to activate MFA"})
                if action == "confirm":
                    if not r["totp_secret"]: return self._err(409, "no pending MFA enrolment — enrol first")
                    b = self._json()
                    matched = MFA.verify(r["totp_secret"], b.get("code") or "", last_counter=-1)
                    if matched is None: return self._err(401, "invalid MFA code", "mfa_invalid")
                    db.execute("UPDATE tenant_users SET mfa_enabled=1, mfa_last_counter=? WHERE id=?", (matched, r["id"]))
                    db.audit("tenant", tid, tid, "user.mfa_confirm", "tenant_user", r["id"])
                    return self._send(200, {"user_id": r["id"], "mfa": "enabled"})
                # reset (recovery)
                db.execute("UPDATE tenant_users SET totp_secret=NULL, mfa_enabled=0, mfa_last_counter=-1 WHERE id=?", (r["id"],))
                db.audit("tenant", tid, tid, "user.mfa_reset", "tenant_user", r["id"],
                         metadata={"note": "admin recovery — user must re-enrol; no bypass issued"})
                return self._send(200, {"user_id": r["id"], "mfa": "reset", "note": "MFA cleared by tenant admin; the user must re-enrol before MFA protects the account again"})
            # --- webhook deliveries: DLQ visibility + replay (WS3) ---
            m = re.match(r"^/v1/webhooks/deliveries/([\w-]+)/replay$", p)
            if m:
                row = db.one("SELECT * FROM webhook_deliveries WHERE id=? AND tenant_id=?", (m.group(1), tid))
                if not row: return self._err(404, "not found")
                ep = db.one("SELECT env FROM webhook_endpoints WHERE id=?", (row["endpoint_id"],))
                if ep is not None and ep["env"] != env: return self._err(404, "not found")
                updated = WH.replay(db, row["id"])
                if updated is None: return self._err(409, "endpoint is gone or revoked — cannot replay")
                db.audit("tenant", tid, tid, "webhook.replay", "webhook_delivery", row["id"],
                         metadata={"status": updated["status"]})
                return self._send(200, {"delivery": row_to_dict(updated)})
            # --- credentials (Phase 3) ---
            if p == "/v1/credentials/verify":
                b = self._json()
                v = CRED.verify_credential(db, data_dir, b.get("credential"))
                return self._send(200, v)  # claims only — never document data
            if p == "/v1/credentials/revoke":
                b = self._json()
                cred = db.one("SELECT * FROM credentials WHERE id=? AND tenant_id=? AND env=?", (b.get("credential_id", ""), tid, env))
                if not cred: return self._err(404, "credential not found for this tenant")
                db.execute("UPDATE credentials SET status='revoked', revoked_at=? WHERE id=?", (now_iso(), cred["id"]))
                db.audit("tenant", tid, tid, "credential.revoke", "credential", cred["id"])
                return self._send(200, {"revoked": True, "credential_id": cred["id"]})
            # --- ongoing monitoring (Phase 3) ---
            if p == "/v1/monitoring/rescreen":
                cfg, _v = FC.get_config(db, tid, env, 3)
                res = MON.run_rescreen(db, data_dir, tid, env, threshold=cfg["screening_threshold"])
                db.audit("tenant", tid, tid, "monitoring.rescreen", "tenant", tid, metadata={"new_hits": res["new_hits"]})
                return self._send(200, res)
            # --- KYB (Phase 3) ---
            if p == "/v1/businesses":
                b = self._json()
                name, reg, country = b.get("legal_name"), (b.get("registration_number") or "").strip(), (b.get("country") or "").upper()
                if not name or not reg or country not in REGISTRY_FORMATS:
                    return self._err(422, f"legal_name, registration_number and a supported country ({sorted(REGISTRY_FORMATS)}) are required")
                pat, hint = REGISTRY_FORMATS[country]
                if not re.match(pat, reg.upper()):
                    return self._err(422, f"registration_number format invalid for {country}: expected {hint} (format validation only — no live registry connection)")
                bid = new_id()
                db.execute("INSERT INTO businesses(id,tenant_id,env,legal_name,registration_number,country,status,registry_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (bid, tid, env, name, reg, country, "pending", "format_valid", now_iso(), now_iso()))
                db.audit("tenant", tid, tid, "business.create", "business", bid)
                return self._send(201, self._business_view(db.one("SELECT * FROM businesses WHERE id=?", (bid,))))
            m = re.match(r"^/v1/businesses/([\w-]+)/people$", p)
            if m:
                biz = db.one("SELECT * FROM businesses WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not biz: return self._err(404, "not found")
                b = self._json()
                if b.get("role") not in ("director", "ubo"): return self._err(422, "role must be director|ubo")
                app = db.one("SELECT * FROM applicants WHERE id=? AND tenant_id=? AND env=?", (b.get("applicant_id", ""), tid, env))
                if not app: return self._err(404, "applicant not found")
                try:
                    db.execute("INSERT INTO business_people(id,business_id,applicant_id,role,ownership_pct,created_at) VALUES(?,?,?,?,?,?)",
                               (new_id(), biz["id"], app["id"], b["role"], b.get("ownership_pct"), now_iso()))
                except Exception:
                    return self._err(409, "person already attached with that role")
                db.audit("tenant", tid, tid, "business.person_add", "business", biz["id"], metadata={"applicant_id": app["id"], "role": b["role"]})
                return self._send(201, self._business_view(db.one("SELECT * FROM businesses WHERE id=?", (biz["id"],))))
            m = re.match(r"^/v1/businesses/([\w-]+)/document$", p)
            if m:
                biz = db.one("SELECT * FROM businesses WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not biz: return self._err(404, "not found")
                parts = parse_multipart(self._body(), self.headers.get("Content-Type", ""))
                f = parts.get("document") or parts.get("front")
                if not f or not f["data"]: return self._err(422, "document file required")
                did = new_id(); rel_dir = os.path.join("files", tid, "businesses", biz["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                rel = os.path.join(rel_dir, f"{did}_registration.bin")
                STORAGE.write_file(data_dir, rel, f["data"])
                db.execute("INSERT INTO business_documents(id,business_id,storage_path,kind,created_at) VALUES(?,?,?,?,?)",
                           (did, biz["id"], rel, field_text(parts, "kind") or "registration", now_iso()))
                db.execute("UPDATE businesses SET registry_status='document_uploaded', updated_at=? WHERE id=?", (now_iso(), biz["id"]))
                db.audit("tenant", tid, tid, "business.document_upload", "business", biz["id"])
                return self._send(201, {"document_id": did, "registry_status": "document_uploaded"})
            m = re.match(r"^/v1/businesses/([\w-]+)/registry$", p)
            if m:
                biz = db.one("SELECT * FROM businesses WHERE id=? AND tenant_id=? AND env=?", (m.group(1), tid, env))
                if not biz: return self._err(404, "not found")
                reviewer = self._reviewer(tid, env)
                if reviewer is None: return self._err(401, "invalid reviewer token")
                gate = self._mfa_gate(reviewer)
                if gate is not None: return gate
                b = self._json()
                if b.get("status") not in ("confirmed", "rejected"): return self._err(422, "status must be confirmed|rejected")
                if not (b.get("reason") or "").strip(): return self._err(422, "reason is required for a registry decision")
                db.execute("UPDATE businesses SET registry_status=?, registry_reason=?, updated_at=? WHERE id=?",
                           (b["status"], b["reason"].strip(), now_iso(), biz["id"]))
                db.audit("reviewer", reviewer["identity"], tid, "business.registry_decide", "business", biz["id"], reason=b["reason"].strip(),
                         metadata={"registry_status": b["status"], "reviewer": reviewer["name"]})
                return self._send(200, {"business_id": biz["id"], "registry_status": b["status"],
                                        "note": "reviewer-confirmed format/document check — no live government registry connection in the local build"})
            m = re.match(r"^/v1/businesses/([\w-]+)/evaluate$", p)
            if m:
                return self._evaluate_business(m.group(1), tid, env)
            # --- case actions ---
            m = re.match(r"^/v1/cases/([\w-]+)/hits/([\w-]+)/dispose$", p)
            if m:
                return self._dispose_hit(m.group(1), m.group(2), tid, env, self._json())
            m = re.match(r"^/v1/cases/([\w-]+)/confirm$", p)
            if m:
                return self._confirm(m.group(1), tid, env, self._json())
            m = re.match(r"^/v1/cases/([\w-]+)/decide$", p)
            if m:
                return self._decide(m.group(1), tid, env, self._json())
            return self._err(404, "not found")

        # ---- KYB assembly ----
        def _evaluate_business(self, business_id, tid, env):
            biz = db.one("SELECT * FROM businesses WHERE id=? AND tenant_id=? AND env=?", (business_id, tid, env))
            if not biz: return self._err(404, "not found")
            reasons = []
            cfg, _v = FC.get_config(db, tid, env, 3)
            people = db.all("SELECT bp.*, a.* FROM business_people bp JOIN applicants a ON a.id=bp.applicant_id WHERE bp.business_id=?", (biz["id"],))
            if biz["registry_status"] == "rejected":
                reasons.append("registry_rejected")
            elif biz["registry_status"] != "confirmed":
                reasons.append("registry_not_confirmed")
            if not people:
                reasons.append("no_people_attached")
            for per in people:
                app = db.one("SELECT * FROM applicants WHERE id=?", (per["applicant_id"],))
                # Screening runs for KYB people (Phase 3 item 9).
                SCR.run_screening(db, data_dir, tid, env, app, origin="kyb", business_id=biz["id"], threshold=cfg["screening_threshold"])
                confirmed = db.one("SELECT id FROM screening_hits WHERE applicant_id=? AND status='confirmed'", (per["applicant_id"],))
                pending = db.one("SELECT id FROM screening_hits WHERE applicant_id=? AND status='pending'", (per["applicant_id"],))
                verified = db.one("SELECT id FROM sessions WHERE applicant_id=? AND status='approved' AND level>=2", (per["applicant_id"],))
                rejected = db.one("SELECT id FROM sessions WHERE applicant_id=? AND status='rejected'", (per["applicant_id"],))
                if confirmed: reasons.append(f"person_{per['applicant_id']}_screening_confirmed")
                elif pending: reasons.append(f"person_{per['applicant_id']}_screening_pending")
                if rejected and not verified: reasons.append(f"person_{per['applicant_id']}_verification_rejected")
                elif not verified: reasons.append(f"person_{per['applicant_id']}_not_verified_l2plus")
            if "registry_rejected" in reasons or any(r.endswith("_screening_confirmed") or r.endswith("_verification_rejected") for r in reasons):
                status = "rejected"
            elif reasons:
                status = "pending"
            else:
                status = "verified"
            db.execute("UPDATE businesses SET status=?, updated_at=? WHERE id=?", (status, now_iso(), biz["id"]))
            db.audit("tenant", tid, tid, "business.evaluate", "business", biz["id"], metadata={"status": status, "reasons": reasons})
            view = self._business_view(db.one("SELECT * FROM businesses WHERE id=?", (biz["id"],)))
            view["evaluation"] = {"status": status, "reasons": reasons,
                                  "note": "registry leg is format validation + uploaded document + reviewer confirmation — no live government registry connection in the local build"}
            return self._send(200, view)

        # ---- reviewer decisions (Phase 3: identities, four-eyes) ----
        def _apply_decision(self, c, action, reason, reviewer, four_eyes_note=None):
            """Write the decision, close the case, fire webhooks, and issue
            the reusable credential when the outcome is an approval."""
            outcome = {"approve": "approved", "reject": "rejected", "request_more": "needs_more_information"}[action]
            did = new_id()
            cfg, cfg_version = FC.get_config(db, c["tenant_id"], c["env"],
                                             (db.one("SELECT level FROM sessions WHERE id=?", (c["session_id"],)) or {"level": 2})["level"])
            db.execute("INSERT INTO decisions(id,session_id,tenant_id,env,outcome,decided_by,reason,reason_codes,rules_version,config_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (did, c["session_id"], c["tenant_id"], c["env"], outcome, "reviewer", reason,
                        json.dumps([f"reviewer_{action}"]), RULES_VERSION, f"v{cfg_version}", now_iso()))
            db.execute("UPDATE sessions SET status=?, decision_id=?, updated_at=? WHERE id=?", (outcome, did, now_iso(), c["session_id"]))
            db.execute("UPDATE cases SET status='decided', resolution=?, decision_id=?, decided_by_name=?, pending_action=NULL, pending_reason=NULL, pending_reviewer=NULL, updated_at=? WHERE id=?",
                       (outcome, did, reviewer["name"], now_iso(), c["id"]))
            db.audit("reviewer", reviewer["identity"], c["tenant_id"], "case.decide", "case", c["id"], reason=reason,
                     metadata={"outcome": outcome, "reviewer": reviewer["name"], "four_eyes": four_eyes_note})
            cred = None
            if outcome == "approved":
                srow = db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],))
                cred = self._issue_credential_for(srow)
            view = self._session_view(db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],)))
            WH.fire(db, c["tenant_id"], c["env"], "case.decided", {"case_id": c["id"], "session_id": c["session_id"], "outcome": outcome, "reason": reason})
            WH.fire(db, c["tenant_id"], c["env"], "session.completed", view)
            out = {"case_id": c["id"], "outcome": outcome, "decision_id": did}
            if cred: out["credential"] = cred
            return out

        def _decide(self, case_id, tid, env, b):
            c = db.one("SELECT * FROM cases WHERE id=? AND tenant_id=? AND env=?", (case_id, tid, env))
            if not c: return self._err(404, "not found")
            reviewer = self._reviewer(tid, env)
            if reviewer is None: return self._err(401, "invalid reviewer token")
            gate = self._mfa_gate(reviewer)
            if gate is not None: return gate
            if c["status"] == "awaiting_second": return self._err(409, "case is awaiting a second reviewer — use /confirm")
            if c["status"] != "open": return self._err(409, "case already decided")
            action, reason = b.get("action"), (b.get("reason") or "").strip()
            if action not in ("approve", "reject", "request_more"): return self._err(422, "action must be approve|reject|request_more")
            if not reason: return self._err(422, "reason is required for every reviewer decision")
            if action == "approve":
                pending = db.one("SELECT id FROM screening_hits WHERE session_id=? AND status='pending'", (c["session_id"],))
                if pending: return self._err(409, "screening hit(s) pending disposition — dispose them before approving")
            s = db.one("SELECT level FROM sessions WHERE id=?", (c["session_id"],))
            cfg, _v = FC.get_config(db, tid, env, s["level"] if s else 2)
            # Four-eyes (Phase 3): approving OVER an engine rejection, or
            # approving a case where a screening hit was disposed as a
            # false positive, needs a SECOND, distinct reviewer.
            needs_second = bool(cfg.get("four_eyes")) and action == "approve" and (
                c["origin_outcome"] == "rejected" or c["four_eyes_required"])
            if needs_second:
                db.execute("UPDATE cases SET status='awaiting_second', pending_action=?, pending_reason=?, pending_reviewer=?, updated_at=? WHERE id=?",
                           (action, reason, reviewer["identity"], now_iso(), c["id"]))
                db.audit("reviewer", reviewer["identity"], tid, "case.decide_first_of_two", "case", c["id"], reason=reason,
                         metadata={"pending_action": action, "reviewer": reviewer["name"]})
                return self._send(202, {"case_id": c["id"], "status": "awaiting_second",
                                        "note": "Four-eyes: a second, different reviewer must confirm this approval via POST /v1/cases/{id}/confirm"})
            out = self._apply_decision(c, action, reason, reviewer)
            return self._send(200, out)

        def _confirm(self, case_id, tid, env, b):
            c = db.one("SELECT * FROM cases WHERE id=? AND tenant_id=? AND env=?", (case_id, tid, env))
            if not c: return self._err(404, "not found")
            reviewer = self._reviewer(tid, env)
            if reviewer is None: return self._err(401, "invalid reviewer token")
            gate = self._mfa_gate(reviewer)
            if gate is not None: return gate
            if c["status"] != "awaiting_second": return self._err(409, "case is not awaiting a second reviewer")
            reason = (b.get("reason") or "").strip()
            if not reason: return self._err(422, "reason is required for the confirming decision")
            if reviewer["identity"] == c["pending_reviewer"]:
                return self._err(403, "four-eyes: the confirming reviewer must be different from the first reviewer")
            out = self._apply_decision(c, c["pending_action"], c["pending_reason"], reviewer,
                                        four_eyes_note={"first_reviewer": c["pending_reviewer"], "confirmed_by": reviewer["name"], "confirm_reason": reason})
            out["four_eyes"] = "confirmed"
            return self._send(200, out)

        def _dispose_hit(self, case_id, hit_id, tid, env, b):
            c = db.one("SELECT * FROM cases WHERE id=? AND tenant_id=? AND env=?", (case_id, tid, env))
            if not c: return self._err(404, "not found")
            reviewer = self._reviewer(tid, env)
            if reviewer is None: return self._err(401, "invalid reviewer token")
            gate = self._mfa_gate(reviewer)
            if gate is not None: return gate
            hit = db.one("SELECT * FROM screening_hits WHERE id=? AND session_id=? AND tenant_id=?", (hit_id, c["session_id"], tid))
            if not hit: return self._err(404, "hit not found on this case")
            if hit["status"] != "pending": return self._err(409, "hit already disposed")
            disposition, reason = b.get("disposition"), (b.get("reason") or "").strip()
            if disposition not in ("confirmed", "false_positive"): return self._err(422, "disposition must be confirmed|false_positive")
            if not reason: return self._err(422, "reason is required to disposition a screening hit")
            db.execute("UPDATE screening_hits SET status=?, disposed_by=?, disposed_reason=?, updated_at=? WHERE id=?",
                       (disposition, reviewer["name"], reason, now_iso(), hit_id))
            db.audit("reviewer", reviewer["identity"], tid, "screening.dispose", "screening_hit", hit_id, reason=reason,
                     metadata={"disposition": disposition, "reviewer": reviewer["name"]})
            if disposition == "confirmed":
                # A confirmed sanctions hit rejects the session outright.
                did = new_id()
                db.execute("INSERT INTO decisions(id,session_id,tenant_id,env,outcome,decided_by,reason,reason_codes,rules_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (did, c["session_id"], tid, env, "rejected", "reviewer", reason,
                            json.dumps(["sanctions_hit_confirmed"]), RULES_VERSION, now_iso()))
                db.execute("UPDATE sessions SET status='rejected', decision_id=?, updated_at=? WHERE id=?", (did, now_iso(), c["session_id"]))
                db.execute("UPDATE cases SET status='decided', resolution='rejected', decision_id=?, decided_by_name=?, updated_at=? WHERE id=?",
                           (did, reviewer["name"], now_iso(), c["id"]))
                view = self._session_view(db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],)))
                WH.fire(db, tid, env, "session.completed", view)
                return self._send(200, {"case_id": c["id"], "hit_id": hit_id, "disposition": "confirmed",
                                        "outcome": "rejected", "reason_codes": ["sanctions_hit_confirmed"]})
            # False positive: the case may proceed — but approving it now
            # requires four-eyes (see _decide).
            db.execute("UPDATE cases SET four_eyes_required=1, updated_at=? WHERE id=?", (now_iso(), c["id"]))
            return self._send(200, {"case_id": c["id"], "hit_id": hit_id, "disposition": "false_positive",
                                    "note": "hit cleared as false positive; approving this case now requires a second reviewer (four-eyes)"})

        # ---- hosted flow ----
        def _read_document(self, doc, always_read=False):
            """The document READING pipeline, shared by the flow
            read-back endpoint and submit: framing + multi-pass OCR +
            MRZ + template field extraction, merged into ONE identity
            by server/identity.py (check-digit-valid MRZ > template
            extraction > uploaded doc_* fields).

            The merged read is persisted onto the documents row —
            doc_* becomes the SERVER's read of the document, not the
            client's typing (the hosted flow collects no typed fields
            at all since the identity-from-document build). When
            framing FAILS the read is NOT persisted: a non-document
            must not write garbage identity fields onto the record.
            With always_read=False (the submit path) a framing failure
            also skips the deep read entirely — the submit fail-fast
            is preserved; the read-back endpoint passes True because
            showing what could be read is its whole job. Authenticity
            / classification / face checks are NOT part of reading —
            they stay at submit, where they are recorded as checks."""
            front_path = self._fs(doc["storage_path"]) if doc["storage_path"] else None
            entry = DOCREG.get_document(doc["issuing_country"], doc["kind"]) or {}
            framing_front = FRAMING.check_document_framing(
                path=front_path, expected_aspect_range=FRAMING.expected_range_from_entry(entry))
            framing_back = None
            if doc["back_storage_path"]:
                framing_back = FRAMING.check_document_framing(
                    path=self._fs(doc["back_storage_path"]), expected_aspect_range=FRAMING.expected_range_from_entry(entry))
            framing = FRAMING.combine_framing(framing_front, framing_back)
            uploaded = {"doc_first_name": doc["doc_first_name"], "doc_last_name": doc["doc_last_name"],
                        "doc_dob": doc["doc_dob"], "doc_number": doc["doc_number"],
                        "doc_expiry": doc["doc_expiry"]}
            if framing["status"] == "fail" and not always_read:
                ident = IDENTITY.derive_document_identity(None, None, uploaded)
                return {"framing": framing, "ocr": None, "ocr_text": "",
                        "mrz_check": None, "mrz_parsed": None,
                        "extraction": None, "extracted_fields": {},
                        "identity": ident,
                        "merged_doc_fields": dict(uploaded), "entry": entry}
            ocr = C.check_ocr(front_path, expect_mrz=bool(entry.get("mrz")))
            ocr_text = ocr.get("text", "")
            mrz_check = C.check_mrz(ocr_text)
            parsed = mrz_check.get("parsed")
            extraction = FIELDTEMPLATES.extract_fields(front_path, doc["issuing_country"], doc["kind"],
                                                       ocr_text=ocr_text,
                                                       ocr_texts=ocr.get("pass_texts"))
            fields = (extraction.get("findings") or {}).get("fields") or {}
            ident = IDENTITY.derive_document_identity(fields, parsed, uploaded, ocr_text=ocr_text)
            merged = {"doc_first_name": ident["first_name"] or doc["doc_first_name"],
                      "doc_last_name": ident["last_name"] or doc["doc_last_name"],
                      "doc_dob": ident["dob"] or doc["doc_dob"],
                      "doc_number": ident["number"] or doc["doc_number"],
                      "doc_expiry": ident["expiry"] or doc["doc_expiry"]}
            if framing["status"] != "fail":
                db.execute("UPDATE documents SET ocr_text=?, mrz_raw=?, doc_first_name=?, doc_last_name=?, doc_dob=?, doc_number=?, doc_expiry=? WHERE id=?",
                           (ocr_text[:8000], (parsed or {}).get("line2"),
                            merged["doc_first_name"], merged["doc_last_name"], merged["doc_dob"],
                            merged["doc_number"], merged["doc_expiry"], doc["id"]))
            return {"framing": framing, "ocr": ocr, "ocr_text": ocr_text,
                    "mrz_check": mrz_check, "mrz_parsed": parsed,
                    "extraction": extraction, "extracted_fields": fields,
                    "identity": ident, "merged_doc_fields": merged, "entry": entry}

        def _flow_post(self, p, s):
            tid, env = s["tenant_id"], s["env"]
            if p == "/v1/flow/consent":
                b = self._json()
                db.execute("INSERT INTO consents(id,tenant_id,applicant_id,session_id,text_version,locale,granted_at) VALUES(?,?,?,?,?,?,?)",
                           (new_id(), tid, s["applicant_id"], s["id"], b.get("text_version") or CONSENT_TEXT_VERSION, b.get("locale") or "en", now_iso()))
                db.execute("UPDATE sessions SET consent_at=?, status='in_progress', updated_at=? WHERE id=?", (now_iso(), now_iso(), s["id"]))
                # Harvest the client IP + IP country at flow start
                # (disclosed in consent text v2): the raw material of
                # the location check at submit.
                geo = self._client_geo()
                if geo["ip"] and not s["client_ip"]:
                    db.execute("UPDATE sessions SET client_ip=?, ip_country=?, updated_at=? WHERE id=?",
                               (geo["ip"], geo["country"], now_iso(), s["id"]))
                elif geo["country"] and not s["ip_country"]:
                    db.execute("UPDATE sessions SET ip_country=?, updated_at=? WHERE id=?",
                               (geo["country"], now_iso(), s["id"]))
                db.audit("applicant", s["applicant_id"], tid, "consent.grant", "session", s["id"],
                         metadata={"client_ip": geo["ip"], "ip_country": geo["country"]})
                # Client corroboration signals from the flow page
                # (record-only): device timezone + WebRTC candidates.
                device_tz = b.get("device_tz") if isinstance(b.get("device_tz"), str) else None
                webrtc_ips = b.get("webrtc_ips") if isinstance(b.get("webrtc_ips"), list) else None
                db.execute("UPDATE sessions SET device_tz=?, webrtc_ips=?, updated_at=? WHERE id=?",
                           (device_tz, json.dumps(webrtc_ips) if webrtc_ips is not None else None, now_iso(), s["id"]))
                # VPN / proxy HARD GATE at flow start (owner's order):
                # detected -> the flow blocks here; the scanner never
                # starts. The verdict is stored on the session and
                # re-checked at submit.
                app_row = db.one("SELECT country FROM applicants WHERE id=?", (s["applicant_id"],))
                vpn = VPN.check_ip(db, geo["ip"], device_tz=device_tz,
                                   declared_country=(app_row["country"] if app_row else None))
                db.execute("UPDATE sessions SET vpn_status=?, updated_at=? WHERE id=?", (vpn["verdict"], now_iso(), s["id"]))
                if vpn.get("ip_country") and not s["ip_country"] and not geo["country"]:
                    db.execute("UPDATE sessions SET ip_country=?, updated_at=? WHERE id=?", (vpn["ip_country"], now_iso(), s["id"]))
                if vpn["verdict"] == "detected":
                    db.audit("system", None, tid, "flow.vpn_blocked", "session", s["id"],
                             metadata={"client_ip": geo["ip"], "findings": vpn["findings"]})
                    return self._err(403, "VPN or proxy detected. Turn off your VPN or proxy and try again.", "vpn_proxy_detected")
                return self._send(200, {"consented": True, "vpn_status": vpn["verdict"]})
            if p == "/v1/flow/document":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body()
                parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                kind = field_text(parts, "kind") or ""
                country = (field_text(parts, "issuing_country") or "").upper()
                front = parts.get("front"); back = parts.get("back")
                if country not in ALLOWED_DOCS or kind not in ALLOWED_DOCS[country]:
                    return self._err(422, f"document type {kind} not supported for {country or '?'} (see the per-country document registry: GET /v1/flow/session -> document_registry)")
                if not front or not front["data"]: return self._err(422, "front image required")
                did = new_id()
                rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                def save(part, tag):
                    ext = ".jpg" if "jpeg" in (part["content_type"] or "") or (part["filename"] or "").lower().endswith((".jpg", ".jpeg")) else ".png"
                    rel = os.path.join(rel_dir, f"{did}_{tag}{ext}")
                    return STORAGE.write_file(data_dir, rel, part["data"])
                front_rel = save(front, "front")
                back_rel = save(back, "back") if back and back["data"] else None
                meta_in = parse_capture_meta(field_text(parts, "capture_meta"))
                capture_meta = {"front": {"method": (meta_in.get("front") or {}).get("method") or meta_in.get("method") or "not_declared", "side": "front"}}
                if back_rel:
                    capture_meta["back"] = {"method": (meta_in.get("back") or {}).get("method") or meta_in.get("method") or "not_declared", "side": "back"}
                entry = DOCREG.get_document(country, kind) or {}
                db.execute("INSERT INTO documents(id,tenant_id,env,session_id,kind,issuing_country,storage_path,back_storage_path,doc_first_name,doc_last_name,doc_dob,doc_number,doc_expiry,capture_meta,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (did, tid, env, s["id"], kind, country, front_rel, back_rel,
                            field_text(parts, "doc_first_name"), field_text(parts, "doc_last_name"),
                            field_text(parts, "doc_dob"), field_text(parts, "doc_number"), field_text(parts, "doc_expiry"),
                            json.dumps(capture_meta), now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "document.upload", "document", did,
                         metadata={"capture": capture_meta})
                return self._send(201, {"document_id": did, "kind": kind, "issuing_country": country,
                                        "sides": entry.get("sides", 1), "has_expiry": entry.get("has_expiry", True),
                                        "back_uploaded": bool(back_rel)})
            if p == "/v1/flow/document/back":
                # Second side of a two-sided document, scanned after the
                # front was accepted (live-scanner flow). Attaches to the
                # existing document row — one document, two images.
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body()
                parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                doc_id = field_text(parts, "document_id") or ""
                back = parts.get("back") or parts.get("front")
                doc = db.one("SELECT * FROM documents WHERE id=? AND session_id=?", (doc_id, s["id"]))
                if not doc: return self._err(404, "document not found for this session")
                entry = DOCREG.get_document(doc["issuing_country"], doc["kind"]) or {}
                if entry.get("sides", 1) < 2: return self._err(422, f"{doc['kind']} has no back side")
                if not back or not back["data"]: return self._err(422, "back image required")
                rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                ext = ".jpg" if "jpeg" in (back["content_type"] or "") or (back["filename"] or "").lower().endswith((".jpg", ".jpeg")) else ".png"
                rel = os.path.join(rel_dir, f"{doc['id']}_back{ext}")
                STORAGE.write_file(data_dir, rel, back["data"])
                meta_in = parse_capture_meta(field_text(parts, "capture_meta"))
                try: capture_meta = json.loads(doc["capture_meta"] or "{}")
                except Exception: capture_meta = {}
                capture_meta["back"] = {"method": (meta_in.get("back") or {}).get("method") or meta_in.get("method") or "not_declared", "side": "back"}
                db.execute("UPDATE documents SET back_storage_path=?, capture_meta=? WHERE id=?",
                           (rel, json.dumps(capture_meta), doc["id"]))
                db.audit("applicant", s["applicant_id"], tid, "document.back_upload", "document", doc["id"],
                         metadata={"capture": capture_meta.get("back")})
                return self._send(201, {"document_id": doc["id"], "back_uploaded": True})
            if p == "/v1/flow/selfie":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body(); parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                f = parts.get("selfie") or parts.get("front")
                if not f or not f["data"]: return self._err(422, "selfie image required")
                bid = new_id(); rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                rel = os.path.join(rel_dir, f"{bid}_selfie.jpg")
                STORAGE.write_file(data_dir, rel, f["data"])
                meta_in = parse_capture_meta(field_text(parts, "capture_meta"))
                capture_meta = {"method": meta_in.get("method") or "not_declared"}
                _keep_client_signals(meta_in, capture_meta)
                db.execute("INSERT INTO biometric_captures(id,tenant_id,env,session_id,storage_path,liveness_method,media_kind,capture_meta,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (bid, tid, env, s["id"], rel, "none", "selfie", json.dumps(capture_meta), now_iso()))
                # Selfie burst frames (continuous face tracking): the
                # scanner sends ~4 extra frames from the same second;
                # they join the selfie in the face track at submit.
                for i in range(5):
                    bf = parts.get(f"burst_{i}")
                    if bf and bf["data"]:
                        brid = new_id(); brel = os.path.join(rel_dir, f"{brid}_burst{i}.jpg")
                        STORAGE.write_file(data_dir, brel, bf["data"])
                        db.execute("INSERT INTO biometric_captures(id,tenant_id,env,session_id,storage_path,liveness_method,media_kind,capture_meta,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                   (brid, tid, env, s["id"], brel, "none", "selfie_burst", json.dumps({"method": "live_camera_burst"}), now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "selfie.upload", "biometric_capture", bid,
                         metadata={"capture": capture_meta})
                return self._send(201, {"biometric_id": bid})
            if p == "/v1/flow/liveness/challenge":
                # Server-generated active-liveness challenge (Phase 2):
                # the movements come from the server, never the client.
                if not s["consent_at"]: return self._err(422, "consent required")
                challenge = LV.new_challenge()
                db.execute("UPDATE sessions SET liveness_challenge=?, updated_at=? WHERE id=?",
                           (json.dumps(challenge), now_iso(), s["id"]))
                db.audit("applicant", s["applicant_id"], tid, "liveness.challenge_issued", "session", s["id"],
                         metadata={"movements": challenge["movements"]})
                return self._send(201, {"challenge": challenge,
                                        "instructions": "Record a short video: start looking at the camera, then move your head: " + ", then ".join(challenge["movements"]) + "."})
            if p == "/v1/flow/liveness":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                if not s["liveness_challenge"]: return self._err(422, "request a liveness challenge first")
                body = self._body(); parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                f = parts.get("video") or parts.get("file")
                if not f or not f["data"]: return self._err(422, "liveness video required")
                bid = new_id(); rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                fname = (f["filename"] or "").lower()
                ext = ".webm" if fname.endswith(".webm") else (".mp4" if fname.endswith(".mp4") else ".bin")
                rel = os.path.join(rel_dir, f"{bid}_liveness{ext}")
                STORAGE.write_file(data_dir, rel, f["data"])
                meta_in = parse_capture_meta(field_text(parts, "capture_meta"))
                capture_meta = {"method": meta_in.get("method") or "not_declared"}
                _keep_client_signals(meta_in, capture_meta)
                db.execute("INSERT INTO biometric_captures(id,tenant_id,env,session_id,storage_path,liveness_method,media_kind,capture_meta,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (bid, tid, env, s["id"], rel, "active_challenge", "liveness_video", json.dumps(capture_meta), now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "liveness.upload", "biometric_capture", bid)
                return self._send(201, {"biometric_id": bid, "method": "active_challenge"})
            if p == "/v1/flow/poa":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body(); parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                f = parts.get("document") or parts.get("front")
                if not f or not f["data"]: return self._err(422, "proof-of-address document required")
                app = db.one("SELECT country FROM applicants WHERE id=?", (s["applicant_id"],))
                did = new_id(); rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                rel = os.path.join(rel_dir, f"{did}_poa.jpg")
                STORAGE.write_file(data_dir, rel, f["data"])
                db.execute("INSERT INTO documents(id,tenant_id,env,session_id,kind,issuing_country,storage_path,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (did, tid, env, s["id"], "proof_of_address", (app["country"] if app else None) or "NG", rel, now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "poa.upload", "document", did)
                return self._send(201, {"document_id": did, "kind": "proof_of_address"})
            if p == "/v1/flow/credential/revoke":
                # The applicant can revoke their own issued credential.
                b = self._json()
                cred = db.one("SELECT * FROM credentials WHERE id=? AND applicant_id=?", (b.get("credential_id", ""), s["applicant_id"]))
                if not cred: return self._err(404, "credential not found for this applicant")
                db.execute("UPDATE credentials SET status='revoked', revoked_at=? WHERE id=?", (now_iso(), cred["id"]))
                db.audit("applicant", s["applicant_id"], tid, "credential.revoke_by_applicant", "credential", cred["id"])
                return self._send(200, {"revoked": True, "credential_id": cred["id"]})
            if p == "/v1/flow/document/process":
                # Read-back step (identity-from-document build): the
                # server READS the uploaded document and returns what
                # it read, so the flow can show the applicant their
                # identity as read ("We read: …") and let them confirm
                # or rescan. There is NO form and no typing anywhere
                # in the flow — rescan is the only correction path, so
                # an unreadable required field is reported by name
                # here and the flow asks for a closer, sharper rescan.
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                b = self._json()
                doc = None
                if b.get("document_id"):
                    doc = db.one("SELECT * FROM documents WHERE id=? AND session_id=?", (b["document_id"], s["id"]))
                if not doc:
                    doc = db.one("SELECT * FROM documents WHERE session_id=? AND kind!='proof_of_address' ORDER BY created_at DESC LIMIT 1", (s["id"],))
                if not doc: return self._err(404, "document not found for this session")
                read = self._read_document(doc, always_read=True)
                ident = read["identity"]
                entry = read["entry"]
                missing = IDENTITY.missing_read_fields(ident, entry)
                framing_status = read["framing"]["status"]
                complete = framing_status == "pass" and not missing
                db.audit("applicant", s["applicant_id"], tid, "document.process", "document", doc["id"],
                         metadata={"framing": framing_status, "missing": missing,
                                   "identity_sources": ident["sources"]})
                return self._send(200, {"document_id": doc["id"], "kind": doc["kind"],
                                        "issuing_country": doc["issuing_country"],
                                        "document_label": entry.get("label") or doc["kind"],
                                        "framing": framing_status,
                                        "read": {"first_name": ident["first_name"],
                                                 "last_name": ident["last_name"],
                                                 "dob": ident["dob"],
                                                 "number": ident["number"],
                                                 "expiry": ident["expiry"]},
                                        "missing": missing, "complete": complete})
            if p == "/v1/flow/submit":
                return self._submit(s, self._client_geo())
            return self._err(404, "not found")

        def _decided_view(self, sid):
            """The submit response for a session that already has a
            decision — the same shape the old synchronous submit
            returned (session view, credential attached when issued)."""
            if not db.one("SELECT id FROM decisions WHERE session_id=? LIMIT 1", (sid,)):
                return None
            row = db.one("SELECT * FROM sessions WHERE id=?", (sid,))
            view = self._session_view(row)
            if row["status"] == "approved":
                cred = db.one("SELECT claims, signature FROM credentials WHERE session_id=? AND status='active' ORDER BY issued_at DESC LIMIT 1", (sid,))
                if cred: view["credential"] = {"claims": json.loads(cred["claims"]), "signature": cred["signature"]}
            case = db.one("SELECT id FROM cases WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (sid,))
            if case: view["case_id"] = case["id"]
            return view

        def _submit(self, s, req_info=None):
            """POST /v1/flow/submit — asynchronous and idempotent.

            The decision pipeline takes 60-120s on a real session while
            the tunnel caps a single request at ~30s, so the old
            synchronous submit died as HTTP 502 while the pipeline kept
            running behind it — and a re-tap started a SECOND pass over
            the same session. Now:
              * a session that already has a decision gets it back at
                once (200, the old response shape);
              * otherwise the session is claimed with ONE atomic
                UPDATE: a submit that finds a fresh claim already
                running gets 202 {"status":"processing"} and starts
                nothing; a claim older than 10 minutes is stale (its
                worker died) and may be reclaimed;
              * the pipeline runs on ONE background thread
                (_submit_worker). This call waits a bounded grace
                (KYC_SUBMIT_GRACE_SEC, default 180s — above the
                pipeline's 60-120s envelope) for it: sessions that
                decide within the grace answer 200 with the decision
                exactly as before. Through the tunnel the request is
                cut at ~30-60s regardless of the grace: the client's
                retry then finds the fresh claim, gets the 202 at
                once, and the flow polls GET /v1/flow/session until
                the worker lands the decision.
            """
            sid = s["id"]
            view = self._decided_view(sid)
            if view: return self._send(200, view)
            # The old in-line submit's synchronous rejections, unchanged.
            if not s["consent_at"]: return self._err(422, "consent required")
            doc = db.one("SELECT id FROM documents WHERE session_id=? AND kind!='proof_of_address' LIMIT 1", (sid,))
            if not doc and not s["credential_id"]: return self._err(422, "document required before submit")
            now = now_iso()
            stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            cur = db.execute(
                "UPDATE sessions SET status='processing', processing_started_at=?, submitted_at=?, updated_at=? "
                "WHERE id=? AND (status='in_progress' OR (status='processing' AND (processing_started_at IS NULL OR processing_started_at<?)))",
                (now, now, now, sid, stale))
            if cur.rowcount != 1:
                # Lost the claim race: a fresh pass is already running
                # (or the session was decided a moment ago — re-check).
                view = self._decided_view(sid)
                if view: return self._send(200, view)
                return self._send(202, {"status": "processing", "session_id": sid})
            claimed = db.one("SELECT * FROM sessions WHERE id=?", (sid,))
            done = threading.Event()
            out = {}
            t = threading.Thread(target=self._submit_worker, args=(claimed, req_info, done, out),
                                 daemon=True, name="submit-" + sid[:8])
            t.start()
            try:
                grace = float(os.environ.get("KYC_SUBMIT_GRACE_SEC") or 180)
            except ValueError:
                grace = 180.0
            if done.wait(grace):
                # The pipeline's OWN return value is the response —
                # byte-for-byte the shape the synchronous submit
                # produced, case_id and credential included.
                if "view" in out: return self._send(200, out["view"])
                view = self._decided_view(sid)
                if view: return self._send(200, view)
                # The worker finished without a decision: it failed and
                # reverted the claim — say so, and the submit is safe
                # to retry (the session is back to 'in_progress').
                return self._err(500, "the decision pipeline failed — please submit again")
            return self._send(202, {"status": "processing", "session_id": sid})

        def _submit_worker(self, s, req_info, done, out):
            """The ONE background decision pass for a claimed session.

            Runs the pipeline on its OWN DB connection (a fresh DB for
            the data dir; DB connections are lock-guarded, and every
            direct statement of the pipeline goes through this one —
            the handler helpers it calls, e.g. document reading and
            credential issuance, use the server's shared lock-guarded
            DB as elsewhere in this codebase). The pipeline itself
            marks the session terminal on success. On ANY exception
            the claim is reverted to a retryable state and the failure
            is logged and audited, so a later submit can run again.
            """
            sid = s["id"]
            wdb = None
            try:
                wdb = DB(data_dir)
                srow = wdb.one("SELECT * FROM sessions WHERE id=?", (sid,)) or s
                out["view"] = self._run_decision_pipeline(srow, wdb, req_info)
            except Exception:
                traceback.print_exc()
                try:
                    rdb = wdb if wdb is not None else db
                    rdb.execute("UPDATE sessions SET status='in_progress', processing_started_at=NULL, updated_at=? WHERE id=? AND status='processing'",
                                (now_iso(), sid))
                    rdb.audit("system", None, s["tenant_id"], "decision.failed", "session", sid,
                              metadata={"error": "pipeline exception; claim reverted for retry"})
                except Exception:
                    traceback.print_exc()
            finally:
                done.set()

        def _run_decision_pipeline(self, s, db, req_info=None):
            tid, env = s["tenant_id"], s["env"]
            req_info = req_info or {}
            if not s["consent_at"]: raise _SubmitRejected(422, "consent required")
            cfg, cfg_version = FC.get_config(db, tid, env, s["level"])
            required = cfg["required_checks"]
            app = db.one("SELECT * FROM applicants WHERE id=?", (s["applicant_id"],))
            # Location evidence: the submit request's own IP wins when
            # it differs from the one harvested at flow start — a VPN
            # switched on mid-flow must not hide behind the old IP.
            # Persisted on the session with the submission.
            submit_ip = req_info.get("ip")
            if submit_ip and s["client_ip"] and submit_ip != s["client_ip"]:
                client_ip = submit_ip
                ip_country = req_info.get("country")
                db.execute("UPDATE sessions SET client_ip=?, ip_country=?, updated_at=? WHERE id=?",
                           (client_ip, ip_country, now_iso(), s["id"]))
            else:
                client_ip = s["client_ip"] or submit_ip
                ip_country = s["ip_country"] or req_info.get("country")
                if client_ip and not s["client_ip"]:
                    db.execute("UPDATE sessions SET client_ip=?, ip_country=?, updated_at=? WHERE id=?",
                               (client_ip, ip_country, now_iso(), s["id"]))
            doc = db.one("SELECT * FROM documents WHERE session_id=? AND kind!='proof_of_address' ORDER BY created_at DESC LIMIT 1", (s["id"],))
            is_credential_session = bool(s["credential_id"])
            if not doc and not is_credential_session: raise _SubmitRejected(422, "document required before submit")
            # No claim UPDATE here: _submit already claimed the session
            # atomically (status='processing' + processing_started_at)
            # before this pass was started on the worker thread.
            results = {}
            def record(ctype, res, provider="local"):
                results[ctype] = {"status": res["status"], "reason_codes": res.get("reason_codes", [])}
                db.execute("INSERT INTO checks(id,session_id,tenant_id,env,type,provider,status,findings,reason_codes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (new_id(), s["id"], tid, env, ctype, provider, res["status"], json.dumps(res.get("findings", {}), default=_json_default), json.dumps(res.get("reason_codes", []), default=_json_default), now_iso()))
            # Checks already recorded for this session (credential inheritance).
            inherited = {}
            for row in db.all("SELECT type,status,reason_codes FROM checks WHERE session_id=? AND provider='verified_credential'", (s["id"],)):
                inherited[row["type"]] = {"status": row["status"], "reason_codes": json.loads(row["reason_codes"] or "[]")}
            results.update(inherited)
            selfie = db.one("SELECT * FROM biometric_captures WHERE session_id=? AND media_kind='selfie' ORDER BY created_at DESC LIMIT 1", (s["id"],))
            selfie_path = self._fs(selfie["storage_path"]) if selfie and selfie["storage_path"] else None
            front_path = self._fs(doc["storage_path"]) if doc and doc["storage_path"] else None
            ocr_text = ""
            parsed = None
            doc_entry = {}
            code_found = False
            auth_findings = {}
            df_client = None
            # Effective applicant for the checks that consume identity
            # (expiry/age, PoA name match, screening): the declared
            # fields where the tenant declared them; on the document
            # path the fields READ from the document fill the gaps
            # once the document is read below (server/identity.py).
            app_eff = dict(app)
            doc_read = None
            if doc:
                # Fresh evidence beats credential inheritance: if a
                # document was uploaded in this session, its checks run
                # and replace any inherited rows of the same type.
                record("capture_quality", C.check_capture_quality(path=front_path))
                # Document framing (live-scanner build): a card-like
                # quadrilateral must roughly fill each captured side.
                # Framing + the whole reading pipeline (multi-pass OCR,
                # MRZ, template field extraction, identity derivation)
                # run through _read_document — the same reader the
                # flow's read-back endpoint uses, so what the applicant
                # was shown is exactly what the decision reads.
                doc_read = self._read_document(doc)
                record("document_framing", doc_read["framing"], provider="opencv-framing")
                framing_failed = results.get("document_framing", {}).get("status") == "fail"
                if framing_failed:
                    # Fail-fast (2026-10-26): no document was detected in the
                    # frame, so deep analysis of a non-document is meaningless
                    # and slow (multi-pass OCR on noise) — the decision is
                    # already an automatic rejection on framing. The remaining
                    # document checks are recorded as not_run so the case shows
                    # exactly what did and did not run, and why.
                    for _ct in ("ocr", "mrz", "expiry_age", "consistency", "authenticity",
                                "code_decode", "document_classification", "data_consistency"):
                        record(_ct, {"status": "not_run", "findings": {"reason": "framing_failed"},
                                     "reason_codes": ["framing_failed"]})
                    if "face_match" in required:
                        record("face_track", {"status": "not_run", "findings": {"reason": "framing_failed"}, "reason_codes": ["framing_failed"]}, provider="yunet-sface-track")
                        record("face_match", {"status": "not_run", "findings": {"reason": "framing_failed"}, "reason_codes": ["framing_failed"]}, provider="yunet-sface")
                if not framing_failed:
                    doc_entry = doc_read["entry"]
                    ocr = doc_read["ocr"]
                    record("ocr", ocr, provider="tesseract")
                    ocr_text = doc_read["ocr_text"]
                    record("mrz", doc_read["mrz_check"], provider="local-mrz")
                    parsed = doc_read["mrz_parsed"]
                    # The document row AS READ (doc_* merged from the
                    # server's own reads — see _read_document): every
                    # downstream check consumes the read, not the
                    # client's typing.
                    docm = dict(doc)
                    docm.update(doc_read["merged_doc_fields"])
                    # Session identity: declared fields win where the
                    # tenant declared them; the document read fills
                    # the rest (the whole identity, on the document
                    # path).
                    _ident = doc_read["identity"]
                    for _col, _val in (("first_name", _ident["first_name"]),
                                       ("last_name", _ident["last_name"]),
                                       ("dob", _ident["dob"])):
                        if _val and not app_eff.get(_col):
                            app_eff[_col] = _val
                    # Field extraction (Phase 4 WS1): template-guided,
                    # zone-first extraction for the claimed document
                    # type, with the per-field source (zone / label /
                    # text fallback) and format validation recorded as
                    # evidence on the case. Recorded here, with the
                    # reading it belongs to (it used to be recorded
                    # after data_consistency; it IS a read, and the
                    # consistency semantics below consume it).
                    record("field_extraction", doc_read["extraction"], provider="local-fieldtemplates")
                    record("expiry_age", C.check_expiry_age(parsed if parsed and parsed.get("valid") else None,
                                                            doc_expiry=docm["doc_expiry"], doc_dob=docm["doc_dob"], applicant_dob=app_eff["dob"],
                                                            has_expiry=doc_entry.get("has_expiry", True),
                                                            validity_end=doc_entry.get("validity_end"),
                                                            prints_dob=doc_entry.get("prints_dob", True)))
                    if app["first_name"] or app["last_name"]:
                        # Declared path: tenant-declared identity is
                        # present -> cross-check exactly as before.
                        record("consistency", C.check_consistency(app["first_name"], app["last_name"], app["dob"],
                                                                  mrz_parsed=parsed, doc_first=docm["doc_first_name"], doc_last=docm["doc_last_name"],
                                                                  doc_dob=docm["doc_dob"], ocr_text=ocr_text))
                    else:
                        # Document path: NOTHING was declared, so
                        # consistency is evaluated across the
                        # document's own reads (extraction vs MRZ vs
                        # OCR text). An applicant mismatch is
                        # impossible here by construction.
                        record("consistency", C.check_document_self_consistency(
                            doc_read["extracted_fields"], mrz_parsed=parsed, ocr_text=ocr_text,
                            ocr_passes=(ocr.get("findings") or {}).get("passes")))
                    # Document authenticity signals (Phase 2 + screen/portrait
                    # evidence, 2026-10-26).
                    _auth = AUTH.check_authenticity(front_path, kind=doc["kind"], country=doc["issuing_country"],
                                                    doc_number=docm["doc_number"], ocr_text=ocr_text,
                                                    mrz_found=bool(parsed))
                    auth_findings = _auth.get("findings") or {}
                    record("authenticity", _auth, provider="local-authenticity")
                    # Vision layer (2026-10-26): MRZ <-> visual-zone cross-
                    # validation — a forged document must fool BOTH zones —
                    # and machine-readable code decoding (QR via OpenCV,
                    # PDF417/barcodes via zxing when installed) whose
                    # structured payload must AGREE with the printed fields.
                    if parsed and parsed.get("valid"):
                        record("mrz_viz_consistency", VISION.cross_check_mrz_viz(ocr_text, parsed), provider="local-vision")
                    _code = VISION.decode_codes(front_path,
                                                self._fs(doc["back_storage_path"]) if doc["back_storage_path"] else None,
                                                doc_fields=docm,
                                                country=doc["issuing_country"], kind=doc["kind"])
                    code_found = bool(_code["findings"].get("found_any"))
                    record("code_decode", _code, provider="local-vision")
                    # Document classification (Addition 9): the image must
                    # classify AS the claimed type by layout — template
                    # aspect, portrait position, printed labels, number
                    # zone, MRZ zone — not merely be a rectangle.
                    record("document_classification",
                           TEMPLATES.check_classification(front_path, doc["issuing_country"], doc["kind"],
                                                          ocr_text=ocr_text,
                                                          mrz_parsed=parsed if parsed and parsed.get("valid") else None),
                           provider="local-templates")
                    # Data-consistency matrix (Addition 10A): every data
                    # source present, pairwise, per field. Any DISAGREE is
                    # a named finding and fails the check — no disagreement
                    # may exist among available pairs for auto-approval.
                    # The applicant source of the matrix is the
                    # DECLARED profile and the printed source is built
                    # from the UPLOADED doc fields, exactly as before.
                    # On the document path both are empty — the matrix
                    # instead receives the field EXTRACTION as its own
                    # source, so the verdict rests on the document's
                    # own reads (extraction vs printed-zone dates vs
                    # MRZ vs payload) and no applicant pair exists that
                    # could ever disagree.
                    _declared = bool(app["first_name"] or app["last_name"])
                    record("data_consistency",
                           VISION.build_data_consistency(doc_fields=dict(doc), applicant=dict(app),
                                                         mrz_parsed=parsed if parsed and parsed.get("valid") else None,
                                                         ocr_text=ocr_text,
                                                         aamva=_code["findings"].get("aamva"),
                                                         extracted=None if _declared else doc_read["extracted_fields"]),
                           provider="local-vision")
                    # Face match (Phase 2 + continuous tracking, 2026-10-26):
                    # the liveness frames + selfie + burst frames form a
                    # TRACK (presence, trajectory, identity continuity);
                    # the match itself compares the document portrait with
                    # the track's AGGREGATE embedding — never one frame.
                    if "face_match" in required:
                        if not selfie_path:
                            record("face_track", {"status": "not_run", "findings": {"reason": "selfie_missing"}, "reason_codes": ["face_track_not_run"]}, provider="yunet-sface-track")
                            record("face_match", {"status": "not_run", "findings": {"reason": "selfie_missing"}, "reason_codes": ["face_match_not_run"]}, provider="yunet-sface")
                        else:
                            vid_row = db.one("SELECT * FROM biometric_captures WHERE session_id=? AND media_kind='liveness_video' ORDER BY created_at DESC LIMIT 1", (s["id"],))
                            burst_rows = db.all("SELECT * FROM biometric_captures WHERE session_id=? AND media_kind='selfie_burst' ORDER BY created_at ASC", (s["id"],))
                            track = FACETRACK.check_face_track(
                                self._fs(vid_row["storage_path"]) if vid_row else None,
                                extra_image_paths=[selfie_path] + [self._fs(b["storage_path"]) for b in burst_rows],
                                pass_threshold=cfg["face_pass_threshold"], margin=cfg["face_margin"])
                            record("face_track", track, provider="yunet-sface-track")
                            agg = track.get("aggregate_embedding")
                            if not face_match_applicable(doc["issuing_country"], doc["kind"]):
                                # The document type carries no portrait
                                # (single source of truth: the full
                                # classification template) — face match is
                                # not applicable; identity rests on the
                                # document, liveness and track continuity.
                                record("face_match", {"status": "not_applicable",
                                                      "findings": {"applicability": "document type carries no portrait",
                                                                   "template_source": "server/templates.py"},
                                                      "reason_codes": []}, provider="yunet-sface")
                            elif agg:
                                # Portrait comes from the WARPED rendition
                                # (the geometrically true document), never
                                # the raw frame.
                                portrait_path = FRAMING.warped_rendition(front_path) or front_path
                                portrait_source = "warped" if portrait_path != front_path else "raw"
                                doc_feat, doc_face, ferr = FACE.extract_face_feature(portrait_path)
                                if ferr:
                                    record("face_match", ferr, provider="yunet-sface")
                                elif doc_face is None:
                                    record("face_match", {"status": "unclear",
                                                          "findings": {"face_in_document": False, "portrait_source": portrait_source,
                                                                       "rescan": "document"},
                                                          "reason_codes": ["document_portrait_not_detected_rescan"]}, provider="yunet-sface")
                                else:
                                    sim = FACE.cosine_similarity(doc_feat, agg)
                                    mstatus, mreasons = FACE.similarity_decision(sim, cfg["face_pass_threshold"], cfg["face_margin"])
                                    record("face_match", {"status": mstatus,
                                                          "findings": {"similarity": round(float(sim), 4), "method": "document_vs_track_median_embedding",
                                                                       "portrait_source": portrait_source,
                                                                       "track_frames": track["findings"].get("frames_with_face")},
                                                          "reason_codes": mreasons}, provider="yunet-sface")
                            else:
                                # No track could be built (e.g. no video):
                                # fall back to the still-vs-still comparison,
                                # still against the warped portrait source.
                                portrait_path = FRAMING.warped_rendition(front_path) or front_path
                                record("face_match", FACE.check_face_match(portrait_path, selfie_path,
                                                                           pass_threshold=cfg["face_pass_threshold"], margin=cfg["face_margin"]),
                                       provider="yunet-sface")
            # Liveness (Phase 2): active challenge video. Never inherited
            # from a credential — a past verification is not a live human.
            if "liveness" in required:
                video = db.one("SELECT * FROM biometric_captures WHERE session_id=? AND media_kind='liveness_video' ORDER BY created_at DESC LIMIT 1", (s["id"],))
                if not video:
                    record("liveness", {"status": "not_run", "findings": {"reason": "liveness_video_missing"}, "reason_codes": ["liveness_not_run"]}, provider="active-challenge")
                else:
                    challenge = None
                    try: challenge = json.loads(s["liveness_challenge"] or "null")
                    except Exception: challenge = None
                    record("liveness", LV.check_liveness(self._fs(video["storage_path"]), challenge), provider="active-challenge")
                # Deepfake / fake-camera defence (2026-10-26): rPPG pulse,
                # generation-artifact FFT, motion trajectory, and the
                # client capture signals sent with the uploads. A known
                # virtual-camera label or no-pulse + high artifacts is a
                # decisive machine failure — never a human task.
                df_client = None
                for _cap in (video, selfie):
                    if df_client or not _cap:
                        continue
                    try:
                        df_client = (json.loads(_cap["capture_meta"] or "{}") or {}).get("client_signals")
                    except Exception:
                        df_client = None
                record("deepfake", DEEPFAKE.check_deepfake(self._fs(video["storage_path"]) if video else None,
                                                           selfie_path, client_signals=df_client), provider="local-deepfake")
            # Proof of address (Phase 3, Level 3).
            if "poa" in required:
                poa_doc = db.one("SELECT * FROM documents WHERE session_id=? AND kind='proof_of_address' ORDER BY created_at DESC LIMIT 1", (s["id"],))
                if not poa_doc:
                    record("poa", {"status": "not_run", "findings": {"reason": "poa_document_missing"}, "reason_codes": ["poa_not_run"]}, provider="local-poa")
                else:
                    poa_ocr = C.check_ocr(self._fs(poa_doc["storage_path"]))
                    db.execute("UPDATE documents SET ocr_text=? WHERE id=?", ((poa_ocr.get("text") or "")[:8000], poa_doc["id"]))
                    if poa_ocr["status"] == "error":
                        record("poa", {"status": "error", "findings": poa_ocr["findings"], "reason_codes": ["poa_ocr_unavailable"]}, provider="local-poa")
                    else:
                        record("poa", C.check_poa(poa_ocr.get("text", ""), applicant_first=app_eff["first_name"],
                                                  applicant_last=app_eff["last_name"], address=app["address_line"],
                                                  window_days=cfg["poa_window_days"]), provider="local-poa")
            # Screening (Phase 3, Level 3): pending hits block approval.
            if "screening_sanctions" in required:
                # Screen the SESSION identity: on the document path
                # the declared record has no name yet (adoption writes
                # it at decision time, below) — the name read from the
                # document is what must be screened.
                scr = SCR.run_screening(db, data_dir, tid, env, app_eff, origin="submit", session_id=s["id"], threshold=cfg["screening_threshold"])
                record("screening_sanctions", {"status": scr["status"], "findings": scr["findings"], "reason_codes": scr["reason_codes"]}, provider="local-lists")
            # VPN / proxy HARD GATE — re-check at submit (owner's
            # order, 2026-10-26). Detection ran at flow start; the
            # cached lookup makes this cheap. Detected -> fail with the
            # hard-fail reason vpn_proxy_detected, and the engine
            # rejects outright whatever else the checks say. Unknown is
            # recorded honestly as unclear — never a fake pass.
            declared_country = (app["country"] or "").upper() if app else ""
            vpn = VPN.check_ip(db, client_ip,
                               device_tz=(s["device_tz"] if "device_tz" in s.keys() else None),
                               declared_country=declared_country or None)
            if vpn.get("ip_country") and not ip_country:
                ip_country = vpn["ip_country"]
                db.execute("UPDATE sessions SET ip_country=?, updated_at=? WHERE id=?", (ip_country, now_iso(), s["id"]))
            db.execute("UPDATE sessions SET vpn_status=?, updated_at=? WHERE id=?", (vpn["verdict"], now_iso(), s["id"]))
            if vpn["verdict"] == "detected":
                record("vpn_proxy", {"status": "fail", "findings": vpn["findings"], "reason_codes": ["vpn_proxy_detected"]}, provider="ip-intel")
            elif vpn["verdict"] == "clean":
                record("vpn_proxy", {"status": "pass", "findings": vpn["findings"], "reason_codes": []}, provider="ip-intel")
            else:
                record("vpn_proxy", {"status": "unclear", "findings": vpn["findings"], "reason_codes": ["vpn_check_unknown"]}, provider="ip-intel")
            # Location consistency (2026-10-26): IP country vs the
            # applicant's DECLARED country. Match -> pass. Unknown (no
            # geo header — local/dev) -> honest unclear. Mismatch ->
            # unclear with reason ip_country_mismatch: a RISK signal
            # (+15 in server/risk.py), never an auto-reject on its own
            # (VPNs and travel exist); it is stored on the session and
            # shown masked in the console.
            loc_findings = {"ip": mask_ip(client_ip), "ip_country": ip_country, "declared_country": declared_country or None}
            if not ip_country:
                record("location_consistency", {"status": "unclear",
                                                "findings": {**loc_findings, "note": "IP country unknown (local/dev or no geo header) — not treated as a mismatch"},
                                                "reason_codes": ["ip_country_unknown"]}, provider="ip-geo")
            elif declared_country and ip_country == declared_country:
                record("location_consistency", {"status": "pass", "findings": loc_findings, "reason_codes": []}, provider="ip-geo")
            else:
                record("location_consistency", {"status": "unclear",
                                                "findings": {**loc_findings, "note": "IP country differs from the declared country — risk signal only (VPN/travel possible), never an auto-reject on its own"},
                                                "reason_codes": ["ip_country_mismatch"]}, provider="ip-geo")
            # --- Proportionate risk / injection signals (AMBITION) ---
            # Signals only: stored structured, never a silent auto-reject.
            ip = client_ip; ua = (req_info.get("user_agent") or "")[:200]
            doc_country = doc["issuing_country"] if doc else (app["country"] if app else None)
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            velocity = db.one("SELECT COUNT(*) AS n FROM sessions WHERE tenant_id=? AND created_at>=?", (tid, one_hour_ago))["n"]
            sig_reasons = []
            mismatch = bool(ip_country and doc_country and ip_country.upper() != doc_country)
            if mismatch: sig_reasons.append("ip_document_country_mismatch")
            if velocity > 20: sig_reasons.append("velocity_high")
            # Injection / virtual-camera signals (Phase 2 item 7): editor
            # or screen-recording fingerprints in the selfie/liveness
            # metadata, and a "captured" JPEG with no camera EXIF at all.
            injection = []
            if selfie_path:
                meta = AUTH.metadata_signal(selfie_path)
                if meta.get("editor_hits"):
                    injection.append({"signal": "selfie_editor_metadata", "hits": meta["editor_hits"]})
                # 'No camera EXIF' applies to real JPEG bytes only (magic
                # FF D8) — a PNG in a .jpg filename proves nothing.
                is_jpeg = False
                try:
                    with open(selfie_path, "rb") as fh: is_jpeg = fh.read(2) == b"\xff\xd8"
                except Exception:
                    pass
                if is_jpeg and not meta.get("has_camera_make_model") and meta.get("strength") != "unavailable":
                    injection.append({"signal": "selfie_no_camera_exif", "detail": "weak signal only — many pipelines strip EXIF"})
                if injection:
                    sig_reasons.append("injection_signal_present")
            record("fraud_signals", {
                "status": "unclear" if sig_reasons else "pass",
                "findings": {"ip": mask_ip(ip), "ip_country": ip_country or "unknown_no_geoip_in_local_build",
                             "document_country": doc_country, "ip_document_country_mismatch": mismatch,
                             "user_agent_summary": ua, "device_class": "mobile" if any(k in ua.lower() for k in ("android", "iphone", "mobile")) else "desktop_or_unknown",
                             "tenant_sessions_last_hour": velocity, "velocity_threshold": 20,
                             "injection_signals": injection,
                             "note": "signals inform review routing only; never auto-reject"},
                "reason_codes": sig_reasons}, provider="local-signals")
            # --- Explainable risk + decision (Phases 2/3) ---
            risk = RISK.compute_risk(results)
            # Verification layers (owner's "beyond" doctrine, 2026-10-26):
            # surface / text / internal recorded with the case, and the
            # internal layer is decision-bearing — where the document
            # type carries internal data (registry MRZ, or a code was
            # decoded from the image), unreadable or disagreeing
            # internal data auto-rejects; it is never silently approved
            # on surface + text alone.
            layers, internal_forced = verification_layers(results, doc_entry=doc_entry, code_found=code_found)
            _lvals = [layers["surface"], layers["text"], layers["internal"]]
            _lstatus = "fail" if (internal_forced or "fail" in _lvals) else (
                "pass" if all(v in ("pass", "not_available") for v in _lvals) else "unclear")
            record("verification_layers", {"status": _lstatus, "findings": layers,
                                           "reason_codes": [internal_forced] if internal_forced else []}, provider="local-engine")
            outcome, reasons = decide(s["level"], results, config=cfg, risk_score=risk)
            if internal_forced:
                outcome = "rejected"
                if internal_forced not in reasons:
                    reasons = sorted(set(reasons) | {internal_forced})
            # Document evidence combination (Addition 10C): the
            # auditable record of the combined document evidence —
            # classification, text, machine-readable, portrait,
            # quality, security features — mirroring the biometric
            # evidence block below.
            if doc:
                _de = document_evidence(results, auth_findings)
                record("document_evidence",
                       {"status": "fail" if _de["any_failed"] else ("pass" if _de["all_passing"] else "unclear"),
                        "findings": _de, "reason_codes": []}, provider="local-engine")
            # Biometric combination gate (2026-10-26): an automatic
            # approval must be a COMBINATION — continuous face track,
            # liveness, track-based face match, capture quality, device
            # signals and the deepfake check, ALL present and passing
            # together. The evidence block is recorded with the case so
            # the decision visibly rests on the combination. A failed
            # component has already rejected via the required checks; a
            # merely ABSENT one (e.g. no device signals recorded)
            # blocks auto-approval and routes the case to a human.
            if s["level"] >= 2 and doc:
                bio = biometric_evidence(results, DEEPFAKE.client_signal_findings(df_client))
                record("biometric_evidence", {"status": "pass" if bio["all_passing"] else ("fail" if bio["any_failed"] else "unclear"),
                                              "findings": bio,
                                              "reason_codes": [] if bio["all_passing"] else ["biometric_evidence_incomplete"]},
                       provider="local-engine")
                if outcome == "approved" and not bio["all_passing"]:
                    outcome = "needs_review"
                    reasons = sorted(set(reasons) | {"biometric_evidence_incomplete"})
            did = new_id()
            db.execute("INSERT INTO decisions(id,session_id,tenant_id,env,outcome,decided_by,reason_codes,rules_version,risk_score,risk_band,risk_contributions,config_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (did, s["id"], tid, env, outcome, "engine", json.dumps(reasons, default=_json_default), RULES_VERSION,
                        risk["score"], risk["band"], json.dumps(risk["contributions"], default=_json_default), f"v{cfg_version}", now_iso()))
            db.execute("UPDATE sessions SET status=?, decision_id=?, updated_at=? WHERE id=?", (outcome, did, now_iso(), s["id"]))
            db.audit("system", None, tid, "decision.engine", "session", s["id"],
                     metadata={"outcome": outcome, "reasons": reasons, "risk_score": risk["score"], "risk_band": risk["band"], "config_version": cfg_version})
            # Identity adoption (document path, owner's order): the
            # identity READ from the document is written to the
            # applicant record as the verified identity. Only EMPTY
            # fields are filled from the read — a field the tenant
            # declared is never overwritten by a read, and when the
            # declared identity CONTRADICTED the document
            # (name_mismatch / dob_mismatch decided this session) the
            # declared record stands untouched: the contradiction is
            # the finding, not something to silently paper over.
            if doc_read and (app["identity_source"] if "identity_source" in app.keys() else "declared") == "document":
                _ident = doc_read["identity"]
                if _ident.get("any") and not ({"name_mismatch", "dob_mismatch"} & set(reasons)):
                    _updates = {}
                    for _col, _val in (("first_name", _ident["first_name"]),
                                       ("last_name", _ident["last_name"]),
                                       ("dob", _ident["dob"])):
                        if _val and not app[_col]:
                            _updates[_col] = _val
                    if _updates:
                        _sets = ", ".join(f"{k}=?" for k in _updates)
                        db.execute(f"UPDATE applicants SET {_sets}, identity_document_id=?, updated_at=? WHERE id=?",
                                   (*_updates.values(), doc["id"], now_iso(), app["id"]))
                        db.audit("system", None, tid, "identity.adopt", "applicant", app["id"],
                                 metadata={"document_id": doc["id"], "session_id": s["id"],
                                           "fields": sorted(_updates), "sources": _ident["sources"]})
            cred = None
            if outcome == "approved":
                srow = db.one("SELECT * FROM sessions WHERE id=?", (s["id"],))
                cred = self._issue_credential_for(srow)
            view = self._session_view(db.one("SELECT * FROM sessions WHERE id=?", (s["id"],)))
            if cred: view["credential"] = cred
            WH.fire(db, tid, env, "session.completed", view)
            if outcome in ("needs_review", "rejected"):
                # Rejected sessions also get a case: a reviewer may
                # override an engine rejection — with four-eyes (Phase 3).
                cid = new_id()
                sla = (datetime.now(timezone.utc) + timedelta(hours=cfg["sla_hours"])).isoformat()
                db.execute("INSERT INTO cases(id,session_id,tenant_id,env,status,origin_outcome,sla_due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (cid, s["id"], tid, env, "open", outcome, sla, now_iso(), now_iso()))
                db.audit("system", None, tid, "case.open", "case", cid, metadata={"origin_outcome": outcome})
                WH.fire(db, tid, env, "case.opened", {"case_id": cid, "session_id": s["id"], "reason_codes": reasons})
                view["case_id"] = cid
            return view
    return H

def serve(port=8765, data_dir="data"):
    db = DB(data_dir)
    handler = make_handler(db, data_dir)
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    # Webhook retry sweeper (WS3): drives webhook_deliveries retries /
    # dead-letter transitions in the background. The DB object is
    # lock-guarded and shared safely with the handler threads.
    import threading, time as _time
    try:
        sweep_sec = float(os.environ.get("KYC_WEBHOOK_SWEEP_SEC") or 15)
    except ValueError:
        sweep_sec = 15.0
    def _sweeper():
        while True:
            _time.sleep(max(1.0, sweep_sec))
            try:
                WH.process_due(db)
            except Exception:
                pass  # a failed sweep must never kill the server; next sweep retries
    threading.Thread(target=_sweeper, daemon=True, name="webhook-sweeper").start()
    enc = "enabled" if STORAGE.encryption_enabled() else "DISABLED (no KYC_MASTER_KEY — legacy plaintext storage)"
    print(f"KYC service on http://127.0.0.1:{port}  (data: {data_dir})  media encryption at rest: {enc}")
    srv.serve_forever()
