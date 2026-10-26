"""SQLite data layer. Mirrors docs/DATA-MODEL.md (SQLite instead of
Postgres for the local-first build; column names and invariants are the
same so the move to Supabase is a port, not a redesign)."""
import json, os, sqlite3, threading, uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, status TEXT NOT NULL DEFAULT 'active',
  retention_days INTEGER NOT NULL DEFAULT 90, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_keys(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), env TEXT NOT NULL CHECK(env IN ('test','live')),
  key_hash TEXT NOT NULL UNIQUE, key_prefix TEXT NOT NULL, created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS applicants(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, env TEXT NOT NULL, external_ref TEXT,
  first_name TEXT, last_name TEXT, dob TEXT, country TEXT, email TEXT, phone TEXT,
  data_deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consents(
  id TEXT PRIMARY KEY, tenant_id TEXT, applicant_id TEXT, session_id TEXT,
  text_version TEXT NOT NULL, locale TEXT, granted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, env TEXT NOT NULL, applicant_id TEXT NOT NULL,
  level INTEGER NOT NULL CHECK(level IN (1,2,3)), status TEXT NOT NULL DEFAULT 'created',
  token_hash TEXT, expires_at TEXT NOT NULL, consent_at TEXT, submitted_at TEXT,
  decision_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, env TEXT NOT NULL, session_id TEXT NOT NULL,
  kind TEXT NOT NULL, issuing_country TEXT NOT NULL, storage_path TEXT, back_storage_path TEXT,
  doc_first_name TEXT, doc_last_name TEXT, doc_dob TEXT, doc_number TEXT, doc_expiry TEXT,
  ocr_text TEXT, mrz_raw TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS biometric_captures(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, env TEXT NOT NULL, session_id TEXT NOT NULL,
  storage_path TEXT, liveness_method TEXT NOT NULL DEFAULT 'none', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checks(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tenant_id TEXT NOT NULL, env TEXT NOT NULL,
  type TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'local', status TEXT NOT NULL,
  findings TEXT NOT NULL DEFAULT '{}', reason_codes TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tenant_id TEXT NOT NULL, env TEXT NOT NULL,
  outcome TEXT NOT NULL, decided_by TEXT NOT NULL, reason TEXT,
  reason_codes TEXT NOT NULL DEFAULT '[]', rules_version TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tenant_id TEXT NOT NULL, env TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open', resolution TEXT, decision_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS webhook_endpoints(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, env TEXT NOT NULL, url TEXT NOT NULL,
  secret TEXT NOT NULL, events TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS webhook_deliveries(
  id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL, tenant_id TEXT, event TEXT NOT NULL,
  payload TEXT NOT NULL, signature TEXT, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  response_summary TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, actor_type TEXT NOT NULL, actor_id TEXT,
  tenant_id TEXT, action TEXT NOT NULL, target_type TEXT, target_id TEXT,
  reason TEXT, metadata TEXT NOT NULL DEFAULT '{}', at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deletions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT, target_type TEXT, target_id TEXT,
  kind TEXT NOT NULL, detail TEXT, at TEXT NOT NULL);
"""

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_id():
    return str(uuid.uuid4())

class DB:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(os.path.join(data_dir, "files"), exist_ok=True)
        self.path = os.path.join(data_dir, "kyc.db")
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def one(self, sql, params=()):
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def audit(self, actor_type, actor_id, tenant_id, action, target_type=None, target_id=None, reason=None, metadata=None):
        self.execute("INSERT INTO audit_log(actor_type,actor_id,tenant_id,action,target_type,target_id,reason,metadata,at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (actor_type, actor_id, tenant_id, action, target_type, target_id, reason, json.dumps(metadata or {}), now_iso()))

def row_to_dict(row, json_fields=()):
    if row is None:
        return None
    d = dict(row)
    for f in json_fields:
        if f in d and isinstance(d[f], str):
            try: d[f] = json.loads(d[f])
            except Exception: pass
    return d
