"""HTTP server: API + hosted flow + console, stdlib http.server (threaded).

Auth model:
  * Tenant APIs:  Authorization: Bearer <api_key>  (only the sha256 hash is stored)
  * Hosted flow:  Authorization: Bearer <flow_token> on /v1/flow/* (hash stored)
  * Tenant creation is unauthenticated ONLY because this is the local MVP
    bootstrap (a real deployment gates it behind platform admin). Noted in README.
"""
import hashlib, json, os, re, secrets
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import CONSENT_TEXT_VERSION, RULES_VERSION
from .db import DB, new_id, now_iso, row_to_dict
from . import checks as C
from .engine import decide, required_for
from . import webhooks as WH

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Settled, owner-expanded launch coverage (DECISIONS D3, 2026-10-26).
# Design rule: passport is accepted for EVERY country in the launch list
# (the MRZ is a worldwide standard); drivers_licence / national_id start
# with the named set below and expand country-by-country with tests.
# To add a country: add its ISO alpha-2 code to LAUNCH_COUNTRIES (passport
# comes with it) and, once its licence/ID is tested, to LICENCE_ID_COUNTRIES.
LAUNCH_COUNTRIES = (
    "NG",  # Nigeria
    "GB",  # United Kingdom (ISO code is GB, not UK)
    "US",  # United States
    "CA",  # Canada
    "AU",  # Australia
    "DE",  # Germany
    "GH",  # Ghana
    "KE",  # Kenya
    "ZA",  # South Africa
    "IN",  # India
    "PH",  # Philippines
    "SG",  # Singapore
    "AE",  # United Arab Emirates
    "FR",  # France
    "NL",  # Netherlands
    "IE",  # Ireland
)
LICENCE_ID_COUNTRIES = {"NG", "US", "GB", "CA", "AU", "DE", "GH"}
SUPPORTED_DOCUMENTS = {
    c: ({"passport", "drivers_licence", "national_id"} if c in LICENCE_ID_COUNTRIES else {"passport"})
    for c in LAUNCH_COUNTRIES
}
# Backwards-readable alias used by the flow endpoints.
ALLOWED_DOCS = SUPPORTED_DOCUMENTS

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

class Ctx:
    def __init__(self, db): self.db = db

def make_handler(db: DB, data_dir: str):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # ---- plumbing ----
        def log_message(self, *a): pass
        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)): body = json.dumps(body).encode()
            if isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
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

        # ================= GET =================
        def do_GET(self):
            p = urlparse(self.path).path
            try: return self._get(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")
        def _get(self, p):
            if p == "/" or p == "/index.html": return self._static("index.html")
            if p == "/console": return self._static("console.html")
            if p.startswith("/flow/"): return self._static("flow.html")
            if p.startswith("/public/"): return self._static(p[len("/public/"):])
            if p == "/healthz": return self._send(200, {"ok": True})
            # flow info
            if p == "/v1/flow/session":
                s = self._flow_session()
                if not s: return self._err(401, "invalid or expired flow token")
                app = db.one("SELECT id,first_name,last_name,dob,country FROM applicants WHERE id=?", (s["applicant_id"],))
                docs = db.all("SELECT id,kind,issuing_country FROM documents WHERE session_id=?", (s["id"],))
                bio = db.all("SELECT id FROM biometric_captures WHERE session_id=?", (s["id"],))
                return self._send(200, {"session": {"id": s["id"], "level": s["level"], "status": s["status"], "env": s["env"],
                                                     "consent_at": s["consent_at"]},
                                        "applicant": row_to_dict(app), "documents": [row_to_dict(d) for d in docs],
                                        "selfie_uploaded": len(bio) > 0,
                                        "allowed_docs": {k: sorted(v) for k, v in ALLOWED_DOCS.items()},
                                        "consent_text_version": CONSENT_TEXT_VERSION})
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
                if p == "/v1/cases":
                    rows = db.all("SELECT * FROM cases WHERE tenant_id=? AND env=? ORDER BY created_at DESC", (tid, env))
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
            fp = os.path.join(PUBLIC_DIR, name)
            if not os.path.isfile(fp): return self._err(404, "not found")
            ctype = "text/html" if name.endswith(".html") else "text/plain"
            if name.endswith(".js"): ctype = "application/javascript"
            if name.endswith(".css"): ctype = "text/css"
            with open(fp, "rb") as f: data = f.read()
            self._send(200, data, ctype)

        def _session_view(self, s):
            d = db.one("SELECT * FROM decisions WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (s["id"],))
            rows = db.all("SELECT type,status FROM checks WHERE session_id=?", (s["id"],))
            summary = {}
            for r in rows: summary[r["type"]] = r["status"]
            out = {"id": s["id"], "tenant_id": s["tenant_id"], "env": s["env"], "applicant_id": s["applicant_id"],
                   "level": s["level"], "status": s["status"], "expires_at": s["expires_at"], "created_at": s["created_at"],
                   "checks_summary": summary, "decision": row_to_dict(d, ("reason_codes",)) if d else None}
            return out

        def _case_view(self, c):
            # PII view: audited.
            db.audit("tenant", c["tenant_id"], c["tenant_id"], "case.view", "case", c["id"])
            s = db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],))
            app = db.one("SELECT * FROM applicants WHERE id=?", (s["applicant_id"],)) if s else None
            docs = db.all("SELECT id,kind,issuing_country,doc_first_name,doc_last_name,doc_dob,doc_number,doc_expiry,ocr_text,mrz_raw,storage_path IS NOT NULL AS has_front, back_storage_path IS NOT NULL AS has_back FROM documents WHERE session_id=?", (c["session_id"],))
            bio = db.all("SELECT id, storage_path IS NOT NULL AS has_image FROM biometric_captures WHERE session_id=?", (c["session_id"],))
            chks = db.all("SELECT * FROM checks WHERE session_id=? ORDER BY created_at", (c["session_id"],))
            doc_list = []
            for d in docs:
                dd = row_to_dict(d)
                dd["image_url"] = f"/v1/documents/{d['id']}/image"
                doc_list.append(dd)
            bio_list = [{"id": b["id"], "has_image": bool(b["has_image"]), "image_url": f"/v1/biometrics/{b['id']}/image"} for b in bio]
            return {"case": row_to_dict(c), "session": self._session_view(s) if s else None,
                    "applicant": row_to_dict(app), "documents": doc_list, "biometrics": bio_list,
                    "checks": [row_to_dict(x, ("findings", "reason_codes")) for x in chks]}

        def _image(self, table, rid, tid, env):
            r = db.one(f"SELECT * FROM {table} WHERE id=? AND tenant_id=? AND env=?", (rid, tid, env))
            if not r or not r["storage_path"]: return self._err(404, "not found")
            fp = os.path.join(data_dir, r["storage_path"])
            if not os.path.isfile(fp): return self._err(404, "file gone")
            db.audit("tenant", tid, tid, "image.view", table, rid)  # audited view; served directly, no persistent URL
            with open(fp, "rb") as f: data = f.read()
            self._send(200, data, "image/jpeg")

        # ================= POST / DELETE =================
        def do_POST(self):
            p = urlparse(self.path).path
            try: return self._post(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")
        def do_DELETE(self):
            p = urlparse(self.path).path
            try: return self._delete(p)
            except Exception as e: return self._err(500, f"internal: {e}", "internal")

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
            # --- tenant bootstrap (local MVP: unauthenticated) ---
            if p == "/v1/tenants":
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
                if not b.get("first_name") or not b.get("last_name") or not b.get("dob") or not b.get("country"):
                    return self._err(422, "first_name, last_name, dob, country required")
                aid = new_id()
                db.execute("INSERT INTO applicants(id,tenant_id,env,external_ref,first_name,last_name,dob,country,email,phone,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (aid, tid, env, b.get("external_ref"), b["first_name"], b["last_name"], b["dob"], b["country"], b.get("email"), b.get("phone"), now_iso(), now_iso()))
                db.audit("tenant", tid, tid, "applicant.create", "applicant", aid)
                return self._send(201, row_to_dict(db.one("SELECT * FROM applicants WHERE id=?", (aid,))))
            if p == "/v1/sessions":
                b = self._json()
                app = db.one("SELECT * FROM applicants WHERE id=? AND tenant_id=? AND env=?", (b.get("applicant_id", ""), tid, env))
                if not app: return self._err(404, "applicant not found")
                if app["data_deleted_at"]: return self._err(422, "applicant erased")
                level = b.get("level")
                if level not in (1, 2, 3): return self._err(422, "level must be 1, 2 or 3")
                sid = new_id(); token = secrets.token_urlsafe(32)
                hours = int(b.get("expires_hours") or 24)
                db.execute("INSERT INTO sessions(id,tenant_id,env,applicant_id,level,status,token_hash,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (sid, tid, env, app["id"], level, "created", sha256(token), iso_in(hours), now_iso(), now_iso()))
                db.audit("tenant", tid, tid, "session.create", "session", sid)
                return self._send(201, {"id": sid, "level": level, "env": env, "status": "created",
                                        "flow_url": f"/flow/{token}", "flow_token": token, "expires_at": iso_in(hours)})
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
            m = re.match(r"^/v1/cases/([\w-]+)/decide$", p)
            if m:
                return self._decide(m.group(1), tid, env, self._json())
            return self._err(404, "not found")

        # ---- reviewer decision ----
        def _decide(self, case_id, tid, env, b):
            c = db.one("SELECT * FROM cases WHERE id=? AND tenant_id=? AND env=?", (case_id, tid, env))
            if not c: return self._err(404, "not found")
            if c["status"] != "open": return self._err(409, "case already decided")
            action, reason = b.get("action"), (b.get("reason") or "").strip()
            if action not in ("approve", "reject", "request_more"): return self._err(422, "action must be approve|reject|request_more")
            if not reason: return self._err(422, "reason is required for every reviewer decision")
            outcome = {"approve": "approved", "reject": "rejected", "request_more": "needs_more_information"}[action]
            did = new_id()
            db.execute("INSERT INTO decisions(id,session_id,tenant_id,env,outcome,decided_by,reason,reason_codes,rules_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (did, c["session_id"], tid, env, outcome, "reviewer", reason, json.dumps([f"reviewer_{action}"]), RULES_VERSION, now_iso()))
            db.execute("UPDATE sessions SET status=?, decision_id=?, updated_at=? WHERE id=?", (outcome, did, now_iso(), c["session_id"]))
            db.execute("UPDATE cases SET status='decided', resolution=?, decision_id=?, updated_at=? WHERE id=?", (outcome, did, now_iso(), c["id"]))
            db.audit("reviewer", tid, tid, "case.decide", "case", c["id"], reason=reason, metadata={"outcome": outcome})
            view = self._session_view(db.one("SELECT * FROM sessions WHERE id=?", (c["session_id"],)))
            WH.fire(db, tid, env, "case.decided", {"case_id": c["id"], "session_id": c["session_id"], "outcome": outcome, "reason": reason})
            WH.fire(db, tid, env, "session.completed", view)
            return self._send(200, {"case_id": c["id"], "outcome": outcome, "decision_id": did})

        # ---- hosted flow ----
        def _flow_post(self, p, s):
            tid, env = s["tenant_id"], s["env"]
            if p == "/v1/flow/consent":
                b = self._json()
                db.execute("INSERT INTO consents(id,tenant_id,applicant_id,session_id,text_version,locale,granted_at) VALUES(?,?,?,?,?,?,?)",
                           (new_id(), tid, s["applicant_id"], s["id"], b.get("text_version") or CONSENT_TEXT_VERSION, b.get("locale") or "en", now_iso()))
                db.execute("UPDATE sessions SET consent_at=?, status='in_progress', updated_at=? WHERE id=?", (now_iso(), now_iso(), s["id"]))
                db.audit("applicant", s["applicant_id"], tid, "consent.grant", "session", s["id"])
                return self._send(200, {"consented": True})
            if p == "/v1/flow/document":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body()
                parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                kind = field_text(parts, "kind") or ""
                country = (field_text(parts, "issuing_country") or "").upper()
                front = parts.get("front"); back = parts.get("back")
                if country not in ALLOWED_DOCS or kind not in ALLOWED_DOCS[country]:
                    return self._err(422, f"document type {kind} not supported for {country or '?'} (passport: all launch countries NG/GB/US/CA/AU/DE/GH/KE/ZA/IN/PH/SG/AE/FR/NL/IE; licence/national ID: NG/US/GB/CA/AU/DE/GH)")
                if not front or not front["data"]: return self._err(422, "front image required")
                did = new_id()
                rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                def save(part, tag):
                    ext = ".jpg" if "jpeg" in (part["content_type"] or "") or (part["filename"] or "").lower().endswith((".jpg", ".jpeg")) else ".png"
                    rel = os.path.join(rel_dir, f"{did}_{tag}{ext}")
                    with open(os.path.join(data_dir, rel), "wb") as f: f.write(part["data"])
                    return rel
                front_rel = save(front, "front")
                back_rel = save(back, "back") if back and back["data"] else None
                db.execute("INSERT INTO documents(id,tenant_id,env,session_id,kind,issuing_country,storage_path,back_storage_path,doc_first_name,doc_last_name,doc_dob,doc_number,doc_expiry,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (did, tid, env, s["id"], kind, country, front_rel, back_rel,
                            field_text(parts, "doc_first_name"), field_text(parts, "doc_last_name"),
                            field_text(parts, "doc_dob"), field_text(parts, "doc_number"), field_text(parts, "doc_expiry"), now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "document.upload", "document", did)
                return self._send(201, {"document_id": did, "kind": kind, "issuing_country": country})
            if p == "/v1/flow/selfie":
                if not s["consent_at"]: return self._err(422, "consent required before upload")
                body = self._body(); parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                f = parts.get("selfie") or parts.get("front")
                if not f or not f["data"]: return self._err(422, "selfie image required")
                bid = new_id(); rel_dir = os.path.join("files", tid, s["id"]); os.makedirs(os.path.join(data_dir, rel_dir), exist_ok=True)
                rel = os.path.join(rel_dir, f"{bid}_selfie.jpg")
                with open(os.path.join(data_dir, rel), "wb") as fh: fh.write(f["data"])
                db.execute("INSERT INTO biometric_captures(id,tenant_id,env,session_id,storage_path,liveness_method,created_at) VALUES(?,?,?,?,?,?,?)",
                           (bid, tid, env, s["id"], rel, "none", now_iso()))
                db.audit("applicant", s["applicant_id"], tid, "selfie.upload", "biometric_capture", bid)
                return self._send(201, {"biometric_id": bid})
            if p == "/v1/flow/submit":
                req_info = {"ip": (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (self.client_address[0] if self.client_address else None),
                            "user_agent": self.headers.get("User-Agent", "")}
                return self._submit(s, req_info)
            return self._err(404, "not found")

        def _submit(self, s, req_info=None):
            tid, env = s["tenant_id"], s["env"]
            req_info = req_info or {}
            if not s["consent_at"]: return self._err(422, "consent required")
            doc = db.one("SELECT * FROM documents WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (s["id"],))
            if not doc: return self._err(422, "document required before submit")
            app = db.one("SELECT * FROM applicants WHERE id=?", (s["applicant_id"],))
            db.execute("UPDATE sessions SET status='processing', submitted_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), s["id"]))
            results = {}
            def record(ctype, res, provider="local"):
                results[ctype] = {"status": res["status"], "reason_codes": res.get("reason_codes", [])}
                db.execute("INSERT INTO checks(id,session_id,tenant_id,env,type,provider,status,findings,reason_codes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (new_id(), s["id"], tid, env, ctype, provider, res["status"], json.dumps(res.get("findings", {})), json.dumps(res.get("reason_codes", [])), now_iso()))
            front_path = os.path.join(data_dir, doc["storage_path"]) if doc["storage_path"] else None
            # capture_quality on document front (+ selfie quality in findings when present)
            record("capture_quality", C.check_capture_quality(path=front_path))
            # OCR
            ocr = C.check_ocr(front_path)
            record("ocr", ocr, provider="tesseract")
            ocr_text = ocr.get("text", "")
            # MRZ
            mrz = C.check_mrz(ocr_text)
            record("mrz", mrz, provider="local-mrz")
            parsed = mrz.get("parsed")
            # Store extracted data on the document row
            db.execute("UPDATE documents SET ocr_text=?, mrz_raw=? WHERE id=?", (ocr_text[:8000], (parsed or {}).get("line2"), doc["id"]))
            # expiry_age
            record("expiry_age", C.check_expiry_age(parsed if parsed and parsed.get("valid") else None,
                                                    doc_expiry=doc["doc_expiry"], doc_dob=doc["doc_dob"], applicant_dob=app["dob"]))
            # consistency
            record("consistency", C.check_consistency(app["first_name"], app["last_name"], app["dob"],
                                                      mrz_parsed=parsed, doc_first=doc["doc_first_name"], doc_last=doc["doc_last_name"],
                                                      doc_dob=doc["doc_dob"], ocr_text=ocr_text))
            # Phase 2 checks: recorded honestly as not_run (required for L2/L3)
            for ctype in ("face_match", "liveness"):
                record(ctype, {"status": "not_run", "findings": {"reason": "phase2_not_implemented_human_compares_images_in_console"}, "reason_codes": [f"{ctype}_not_run"]}, provider="none")
            if s["level"] >= 3:
                for ctype in ("poa", "screening_sanctions"):
                    record(ctype, {"status": "not_run", "findings": {"reason": "phase3_not_implemented"}, "reason_codes": [f"{ctype}_not_run"]}, provider="none")
            # --- Proportionate risk signals (AMBITION.md / owner order) ---
            # Signals only: stored structured, never a silent auto-reject.
            # An *elevated* signal routes to human review via the engine.
            # No external geo-IP service is used in this local build, so IP
            # country is honestly recorded as unknown unless a future
            # deployment supplies X-IP-Country from its edge.
            ip = req_info.get("ip"); ua = (req_info.get("user_agent") or "")[:200]
            ip_country = (self.headers.get("X-IP-Country") if hasattr(self, "headers") else None) or None
            doc_country = doc["issuing_country"]
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            velocity = db.one("SELECT COUNT(*) AS n FROM sessions WHERE tenant_id=? AND created_at>=?", (tid, one_hour_ago))["n"]
            sig_reasons = []
            mismatch = bool(ip_country and ip_country.upper() != doc_country)
            if mismatch: sig_reasons.append("ip_document_country_mismatch")
            if velocity > 20: sig_reasons.append("velocity_high")
            record("fraud_signals", {
                "status": "unclear" if sig_reasons else "pass",
                "findings": {"ip": ip, "ip_country": ip_country or "unknown_no_geoip_in_local_build",
                             "document_country": doc_country, "ip_document_country_mismatch": mismatch,
                             "user_agent_summary": ua, "device_class": "mobile" if any(k in ua.lower() for k in ("android", "iphone", "mobile")) else "desktop_or_unknown",
                             "tenant_sessions_last_hour": velocity, "velocity_threshold": 20,
                             "note": "signals inform review routing only; never auto-reject"},
                "reason_codes": sig_reasons}, provider="local-signals")
            outcome, reasons = decide(s["level"], results)
            did = new_id()
            db.execute("INSERT INTO decisions(id,session_id,tenant_id,env,outcome,decided_by,reason_codes,rules_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (did, s["id"], tid, env, outcome, "engine", json.dumps(reasons), RULES_VERSION, now_iso()))
            db.execute("UPDATE sessions SET status=?, decision_id=?, updated_at=? WHERE id=?", (outcome, did, now_iso(), s["id"]))
            db.audit("system", None, tid, "decision.engine", "session", s["id"], metadata={"outcome": outcome, "reasons": reasons})
            view = self._session_view(db.one("SELECT * FROM sessions WHERE id=?", (s["id"],)))
            WH.fire(db, tid, env, "session.completed", view)
            if outcome == "needs_review":
                cid = new_id()
                db.execute("INSERT INTO cases(id,session_id,tenant_id,env,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                           (cid, s["id"], tid, env, "open", now_iso(), now_iso()))
                db.audit("system", None, tid, "case.open", "case", cid)
                WH.fire(db, tid, env, "case.opened", {"case_id": cid, "session_id": s["id"], "reason_codes": reasons})
                view["case_id"] = cid
            return self._send(200, view)
    return H

def serve(port=8765, data_dir="data"):
    db = DB(data_dir)
    handler = make_handler(db, data_dir)
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"KYC Phase 1 local MVP on http://127.0.0.1:{port}  (data: {data_dir})")
    srv.serve_forever()
