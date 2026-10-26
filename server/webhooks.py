"""Signed webhook delivery. Signature header format (docs/API.md):
  KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
The HMAC is computed over b"<ts>." + raw_body with the endpoint secret —
the same construction Stripe-style schemes use, so a captured signature
cannot be replayed against a different body or much later.
One immediate delivery attempt is made (short timeout); the attempt is
always logged in webhook_deliveries. Failures are recorded, never fatal.
Retries/backoff/replay UI are production concerns beyond Phase 1 local.
"""
import hashlib, hmac, json, time, urllib.request, urllib.error

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

def fire(db, tenant_id, env, event, payload):
    """Create delivery rows for matching endpoints and attempt delivery."""
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
        status, summary = "failed", ""
        try:
            req = urllib.request.Request(ep["url"], data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("KYC-Signature", header)
            req.add_header("KYC-Event", event)
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = "delivered"; summary = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            summary = f"HTTP {e.code}"
        except Exception as e:
            summary = f"{type(e).__name__}: {e}"[:200]
        db.execute("UPDATE webhook_deliveries SET status=?, attempts=1, response_summary=? WHERE id=?", (status, summary, did))
    return True
