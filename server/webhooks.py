"""Signed webhook delivery with retries, dead-letter and replay
(Phase 4 WS3; was one-attempt in Phase 1).

Signature header format (docs/API.md):
  KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
The HMAC is computed over b"<ts>." + raw_body with the endpoint secret —
the same construction Stripe-style schemes use, so a captured signature
cannot be replayed against a different body or much later. Every attempt
is re-signed with a FRESH timestamp, so a retry never carries a stale
signature outside a receiver's tolerance window.

Delivery lifecycle (webhook_deliveries.status):
  pending -> delivered            first or a later attempt succeeded
  pending -> failed -> failed...  attempts remain; next_attempt_at set
                                  with exponential backoff (base
                                  KYC_WEBHOOK_BACKOFF_SEC, default 30s,
                                  doubling per attempt)
  failed  -> dead_letter          attempt budget exhausted
                                  (KYC_WEBHOOK_MAX_ATTEMPTS, default 5);
                                  visible via GET /v1/webhooks/deliveries
                                  and replayable via
                                  POST /v1/webhooks/deliveries/{id}/replay
Retries are driven by process_due() — a background sweeper thread in
server/app.py serve() calls it periodically; tests call it directly.

SSRF guard: the server POSTs to tenant-supplied URLs, so targets are
restricted to public addresses. Non-http(s) schemes, "localhost", DNS
failures, and any host resolving to a loopback/private/link-local/
reserved/multicast address are refused BEFORE any network call (the
refusal is recorded as the attempt's response_summary). The guard can
be relaxed for local development ONLY by setting
KYC_ALLOW_PRIVATE_WEBHOOKS=1 — never set it in production. Known
limit (stated in docs/SECURITY.md): the check resolves at attempt
time; DNS rebinding between check and connect is not fully excluded
by urllib, so egress filtering remains a deployment control.
"""
import hashlib, hmac, ipaddress, json, os, socket, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

def sign(secret, body_bytes, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    mac = hmac.new(secret.encode(), ts.encode() + b"." + body_bytes, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}", ts, mac

def verify(secret, body_bytes, header):
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, mac = parts["t"], parts["v1"]
    except Exception:
        return False
    expected = hmac.new(secret.encode(), ts.encode() + b"." + body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, mac)

# ---------------- configuration ----------------

def max_attempts():
    try:
        return max(1, int(os.environ.get("KYC_WEBHOOK_MAX_ATTEMPTS") or 5))
    except ValueError:
        return 5

def backoff_seconds(attempts_done):
    """Delay before the NEXT attempt, after `attempts_done` attempts."""
    try:
        base = float(os.environ.get("KYC_WEBHOOK_BACKOFF_SEC") or 30)
    except ValueError:
        base = 30.0
    return base * (2 ** max(0, attempts_done - 1))

def _now():
    return datetime.now(timezone.utc)

def _iso(dt):
    return dt.isoformat()

# ---------------- SSRF guard ----------------

def url_allowed(url):
    """-> (ok, reason). Fail closed on anything unparseable,
    non-public, or unresolvable."""
    if os.environ.get("KYC_ALLOW_PRIVATE_WEBHOOKS") == "1":
        # Explicit development override (local receivers in tests).
        # Scheme is still restricted so file:// etc. never fire.
        from urllib.parse import urlparse
        return (urlparse(url or "").scheme in ("http", "https")), "scheme not http/https"
    from urllib.parse import urlparse
    try:
        u = urlparse(url or "")
    except Exception:
        return False, "unparseable URL"
    if u.scheme not in ("http", "https"):
        return False, "scheme not http/https"
    host = (u.hostname or "").strip().lower()
    if not host:
        return False, "no host"
    if host == "localhost" or host.endswith(".localhost"):
        return False, "localhost target"
    ips = []
    try:
        literal = ipaddress.ip_address(host)
        ips = [literal]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80),
                                       proto=socket.IPPROTO_TCP)
            ips = [ipaddress.ip_address(info[4][0]) for info in infos]
        except Exception:
            return False, "host does not resolve"
    if not ips:
        return False, "host does not resolve"
    for ip in ips:
        if (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False, f"target resolves to non-public address {ip}"
    return True, "ok"

# ---------------- delivery engine ----------------

def _attempt(db, ep, row):
    """Perform ONE delivery attempt for an existing delivery row.
    Re-signs with a fresh timestamp. Updates the row in place and
    returns its new status."""
    from .db import now_iso
    body = (row["payload"] or "").encode()
    attempts = int(row["attempts"] or 0) + 1
    header, _, _ = sign(ep["secret"], body)
    status, summary = "failed", ""
    allowed, why = url_allowed(ep["url"])
    if not allowed:
        summary = f"blocked by SSRF guard: {why}"
    else:
        try:
            req = urllib.request.Request(ep["url"], data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("KYC-Signature", header)
            req.add_header("KYC-Event", row["event"])
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = "delivered"; summary = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            summary = f"HTTP {e.code}"
        except Exception as e:
            summary = f"{type(e).__name__}: {e}"[:200]
    if status == "delivered":
        db.execute("UPDATE webhook_deliveries SET status='delivered', attempts=?, signature=?, "
                   "response_summary=?, next_attempt_at=NULL WHERE id=?",
                   (attempts, header, summary, row["id"]))
    elif attempts >= max_attempts():
        db.execute("UPDATE webhook_deliveries SET status='dead_letter', attempts=?, signature=?, "
                   "response_summary=?, next_attempt_at=NULL, dead_lettered_at=? WHERE id=?",
                   (attempts, header, summary, now_iso(), row["id"]))
        status = "dead_letter"
    else:
        nxt = _iso(_now() + timedelta(seconds=backoff_seconds(attempts)))
        db.execute("UPDATE webhook_deliveries SET status='failed', attempts=?, signature=?, "
                   "response_summary=?, next_attempt_at=? WHERE id=?",
                   (attempts, header, summary, nxt, row["id"]))
    return status

def fire(db, tenant_id, env, event, payload):
    """Create delivery rows for matching endpoints and make the
    first attempt on each. Later attempts are process_due()'s job."""
    endpoints = db.all("SELECT * FROM webhook_endpoints WHERE tenant_id=? AND env=? AND revoked_at IS NULL", (tenant_id, env))
    body = json.dumps({"event": event, "data": payload}, separators=(",", ":")).encode()
    for ep in endpoints:
        try:
            events = json.loads(ep["events"] or "[]")
        except Exception:
            events = []
        if events and event not in events:
            continue
        header, _, _ = sign(ep["secret"], body)
        from .db import new_id, now_iso
        did = new_id()
        db.execute("INSERT INTO webhook_deliveries(id,endpoint_id,tenant_id,event,payload,signature,status,attempts,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (did, ep["id"], tenant_id, event, body.decode(), header, "pending", 0, now_iso()))
        row = db.one("SELECT * FROM webhook_deliveries WHERE id=?", (did,))
        _attempt(db, ep, row)
    return True

def process_due(db, now=None):
    """Attempt every delivery whose retry time has come. Called by
    the serve() sweeper thread and directly by tests. Returns counts."""
    now = now or _iso(_now())
    rows = db.all("SELECT * FROM webhook_deliveries WHERE status='failed' AND next_attempt_at IS NOT NULL "
                  "AND next_attempt_at<=? AND attempts<? ORDER BY next_attempt_at LIMIT 200",
                  (now, max_attempts()))
    out = {"processed": 0, "delivered": 0, "dead_lettered": 0}
    for row in rows:
        ep = db.one("SELECT * FROM webhook_endpoints WHERE id=?", (row["endpoint_id"],))
        if ep is None or ep["revoked_at"]:
            from .db import now_iso
            db.execute("UPDATE webhook_deliveries SET status='dead_letter', response_summary='endpoint gone or revoked', "
                       "next_attempt_at=NULL, dead_lettered_at=? WHERE id=?", (now_iso(), row["id"]))
            out["processed"] += 1; out["dead_lettered"] += 1
            continue
        st = _attempt(db, ep, row)
        out["processed"] += 1
        if st == "delivered": out["delivered"] += 1
        elif st == "dead_letter": out["dead_lettered"] += 1
    return out

def replay(db, delivery_id):
    """Operator replay of a dead-lettered (or failed) delivery:
    resets the attempt budget and delivers immediately with a fresh
    signature. Returns the updated row, or None when the delivery or
    its endpoint no longer exists."""
    row = db.one("SELECT * FROM webhook_deliveries WHERE id=?", (delivery_id,))
    if not row:
        return None
    ep = db.one("SELECT * FROM webhook_endpoints WHERE id=?", (row["endpoint_id"],))
    if ep is None or ep["revoked_at"]:
        return None
    db.execute("UPDATE webhook_deliveries SET status='pending', attempts=0, next_attempt_at=NULL, "
               "dead_lettered_at=NULL, response_summary='replayed by operator' WHERE id=?", (delivery_id,))
    row = db.one("SELECT * FROM webhook_deliveries WHERE id=?", (delivery_id,))
    _attempt(db, ep, row)
    return db.one("SELECT * FROM webhook_deliveries WHERE id=?", (delivery_id,))
