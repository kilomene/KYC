"""Fraud intelligence (Phase 4 WS7): cross-session duplicate
detection, velocity and coordinated-abuse signals.

Privacy-preserving by construction (the plan's own words:
"hashed embeddings, no cross-tenant data exposure"):

  * The index stores ONLY keyed hashes (HMAC-SHA256 under a key
    derived from the platform master key). A document number is
    indexed as one HMAC of its normalised form; a face is
    indexed as locality-sensitive bucket hashes of its embedding
    — the embedding itself is never stored, and nothing in the
    index can be reversed into a number or a face.
  * Every lookup is scoped to (tenant_id, env): one tenant's
    applicants can never be matched against another tenant's.

Signals, never verdicts: duplicates and velocity feed the
fraud_signals check and the explainable risk score, and the
engine routes elevated signals to human review. Nothing in
this module rejects anyone — a person re-verifying with their
own document, or a family sharing one IP, are legitimate
patterns a reviewer can see and clear.
"""
import hashlib
import hmac as _hmac

# --- tunables (deliberately conservative) -------------------------
DOC_DUP_REASON = "duplicate_document"
FACE_DUP_REASON = "duplicate_face_suspected"
VEL_IP_REASON = "velocity_ip_high"
VEL_APP_REASON = "velocity_applicant_high"
COORD_REASON = "coordinated_abuse_suspected"

IP_HOUR_LIMIT = 5           # sessions from one IP in an hour
APP_DAY_LIMIT = 3           # sessions for one applicant in a day
COORD_IP_APPLICANTS = 3     # distinct applicants from one IP in a day

_FACE_BUCKETS = 4           # independent LSH bands
_FACE_BITS = 12             # projection bits per band
_FACE_MIN_BAND_HITS = 2     # bands (of 4) that must collide


def _index_key():
    """HMAC key for the fraud index, derived from the master
    key so the index is useless without it. Falls back to a
    labelled development derivation when no master key is
    configured (test/dev only — production always has one)."""
    try:
        from . import storage
        mk = storage.master_key()
        return _hmac.new(mk, b"kyc-fraud-index-v1", hashlib.sha256).digest()
    except Exception:
        return hashlib.sha256(b"kyc-fraud-index-dev-only").digest()


def _h(key, msg):
    return _hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def normalise_number(country, kind, number):
    n = "".join(ch for ch in str(number or "").upper() if ch.isalnum())
    return f"{(country or '').upper()}:{(kind or '').lower()}:{n}" if n else ""


def document_key(country, kind, number, key=None):
    norm = normalise_number(country, kind, number)
    if not norm:
        return None
    return _h(key or _index_key(), "doc:" + norm)


def _projection_bits(embedding, key):
    """Deterministic random-hyperplane bits for the embedding:
    bit (band, i) is the sign of the dot product with a
    projection vector derived from the index key — stable across
    restarts, meaningless without the key."""
    import math
    vec = [float(x) for x in embedding]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    vec = [x / norm for x in vec]
    bits = []
    for band in range(_FACE_BUCKETS):
        code = 0
        for i in range(_FACE_BITS):
            # One key-derived coefficient per dimension (a fresh
            # HMAC per (band, bit, dimension-bucket of 16)) — real
            # random hyperplanes, so unrelated faces' codes are
            # ~uniform and the collision maths in
            # face_bucket_hashes holds.
            acc = 0.0
            for d0 in range(0, len(vec), 16):
                seed = _hmac.new(key, f"proj:{band}:{i}:{d0}".encode(),
                                 hashlib.sha256).digest()
                for j, v in enumerate(vec[d0:d0 + 16]):
                    acc += v * ((seed[j % len(seed)] / 127.5) - 1.0)
            if acc >= 0:
                code |= (1 << i)
        bits.append(code)
    return bits


def face_bucket_hashes(embedding, key=None):
    """The stored form of a face: for each band, the HMAC of the
    band's bit code AND of every one-bit neighbour (multi-probe:
    near-identical faces land in adjacent codes). 4 bands x 13
    hashes. A different person's code collides with a stored
    neighbour with probability ~13/4096 per band — candidates,
    not conclusions."""
    if not embedding:
        return []
    key = key or _index_key()
    out = []
    for band, code in enumerate(_projection_bits(embedding, key)):
        variants = {code} | {code ^ (1 << i) for i in range(_FACE_BITS)}
        for v in variants:
            out.append((band, _h(key, f"face:{band}:{v:03x}")))
    return out


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS fraud_index(
        id TEXT PRIMARY KEY, tenant_id TEXT, env TEXT, kind TEXT,
        key_hash TEXT, band INTEGER, session_id TEXT,
        applicant_id TEXT, created_at TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fraud_lookup "
               "ON fraud_index(tenant_id, env, kind, key_hash)")


def evaluate(db, tid, env, session_id, applicant_id, client_ip,
             doc_country, doc_kind, doc_number, face_embedding,
             now_iso_str, hour_ago_iso, day_ago_iso):
    """Run the WS7 signals for a submitting session.
    Returns (findings, reason_codes). Tenant+env scoped."""
    ensure_schema(db)
    findings = {}
    reasons = []
    key = _index_key()

    # --- duplicate document (different applicant, same number) ---
    dk = document_key(doc_country, doc_kind, doc_number, key)
    findings["duplicate_document"] = False
    if dk:
        row = db.one("SELECT COUNT(*) AS n, COUNT(DISTINCT applicant_id) AS apps "
                     "FROM fraud_index WHERE tenant_id=? AND env=? AND kind='document' "
                     "AND key_hash=? AND applicant_id<>?",
                     (tid, env, dk, applicant_id))
        if row and row["apps"] and row["apps"] >= 1:
            findings["duplicate_document"] = True
            findings["duplicate_document_sessions"] = int(row["n"])
            reasons.append(DOC_DUP_REASON)

    # --- duplicate face (LSH bucket collisions, other applicants) -
    findings["duplicate_face_bands"] = 0
    if face_embedding:
        hashes = face_bucket_hashes(face_embedding, key)
        if hashes:
            bands_hit = set()
            for band, hh in hashes:
                row = db.one("SELECT COUNT(*) AS n FROM fraud_index "
                             "WHERE tenant_id=? AND env=? AND kind='face' "
                             "AND key_hash=? AND band=? AND applicant_id<>?",
                             (tid, env, hh, band, applicant_id))
                if row and row["n"]:
                    bands_hit.add(band)
            findings["duplicate_face_bands"] = len(bands_hit)
            if len(bands_hit) >= _FACE_MIN_BAND_HITS:
                reasons.append(FACE_DUP_REASON)

    # --- velocity: per-IP (hour), per-applicant (day) -------------
    if client_ip:
        row = db.one("SELECT COUNT(*) AS n FROM sessions WHERE tenant_id=? AND env=? "
                     "AND client_ip=? AND created_at>=? AND id<>?",
                     (tid, env, client_ip, hour_ago_iso, session_id))
        n_ip = int(row["n"]) if row else 0
        findings["ip_sessions_last_hour"] = n_ip
        if n_ip >= IP_HOUR_LIMIT:
            reasons.append(VEL_IP_REASON)
        row = db.one("SELECT COUNT(DISTINCT applicant_id) AS n FROM sessions "
                     "WHERE tenant_id=? AND env=? AND client_ip=? AND created_at>=?",
                     (tid, env, client_ip, day_ago_iso))
        n_apps = int(row["n"]) if row else 0
        findings["ip_distinct_applicants_last_day"] = n_apps
        if n_apps >= COORD_IP_APPLICANTS:
            reasons.append(COORD_REASON)
    row = db.one("SELECT COUNT(*) AS n FROM sessions WHERE tenant_id=? AND env=? "
                 "AND applicant_id=? AND created_at>=? AND id<>?",
                 (tid, env, applicant_id, day_ago_iso, session_id))
    n_app = int(row["n"]) if row else 0
    findings["applicant_sessions_last_day"] = n_app
    if n_app >= APP_DAY_LIMIT:
        reasons.append(VEL_APP_REASON)

    return findings, reasons


def index_session(db, new_id, tid, env, session_id, applicant_id,
                  doc_country, doc_kind, doc_number, face_embedding,
                  now_iso_str):
    """Index THIS session's document + face after evaluation, so
    later sessions can match against it. Every decided session
    is indexed — a rejected attempt is exactly what duplicate
    detection exists to catch next time."""
    ensure_schema(db)
    key = _index_key()
    dk = document_key(doc_country, doc_kind, doc_number, key)
    if dk:
        db.execute("INSERT INTO fraud_index(id,tenant_id,env,kind,key_hash,band,"
                   "session_id,applicant_id,created_at) VALUES(?,?,?,'document',?,NULL,?,?,?)",
                   (new_id(), tid, env, dk, session_id, applicant_id, now_iso_str))
    for band, hh in face_bucket_hashes(face_embedding, key):
        db.execute("INSERT INTO fraud_index(id,tenant_id,env,kind,key_hash,band,"
                   "session_id,applicant_id,created_at) VALUES(?,?,?,'face',?,?,?,?,?)",
                   (new_id(), tid, env, hh, band, session_id, applicant_id, now_iso_str))
