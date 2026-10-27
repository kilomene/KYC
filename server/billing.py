"""Billing machinery (Phase 4 WS6): usage metering, configurable
prices, tenant quotas, invoice generation.

The owner's pricing DECISION (D7) is still open — per-level
prices are unset. This module is the machinery that works the
day prices land:

  * Every decided session meters exactly ONE usage event
    (UNIQUE session_id — a re-submit or a reviewer override of
    the same verification never double-bills).
  * The amount is priced at metering time from the active
    price for (level, env); with no price configured the event
    is recorded UNPRICED (amount NULL) — visible, honest, and
    never silently zero. Sandbox (env='test') is free by the D7
    shape: amount 0, priced as sandbox_free.
  * Prices are operator-managed (versioned rows; setting a new
    price deactivates the old — history is never rewritten).
  * Invoices aggregate a tenant's priced, not-yet-invoiced
    events in a period; an event joins exactly one invoice.
  * Quotas: an operator-set monthly cap on LIVE verifications
    per tenant; no row = unlimited. Test env is never capped.

Money is integer cents throughout. No payment collection here
— this engine meters and invoices; charging is a payments
integration (Nova Payments) on top.
"""
from datetime import datetime, timezone

SANDBOX_FREE = "sandbox_free"


def _now():
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS prices(
        id TEXT PRIMARY KEY, level INTEGER, env TEXT,
        unit_price_cents INTEGER, currency TEXT,
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS usage_events(
        id TEXT PRIMARY KEY, tenant_id TEXT, env TEXT,
        session_id TEXT UNIQUE, level INTEGER,
        amount_cents INTEGER, price_id TEXT, invoice_id TEXT,
        created_at TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS invoices(
        id TEXT PRIMARY KEY, tenant_id TEXT, env TEXT,
        period_start TEXT, period_end TEXT, currency TEXT,
        total_cents INTEGER, status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS tenant_quotas(
        tenant_id TEXT PRIMARY KEY, monthly_limit INTEGER,
        updated_at TEXT)""")


def set_price(db, new_id, level, env, unit_price_cents, currency="USD"):
    ensure_schema(db)
    db.execute("UPDATE prices SET active=0 WHERE level=? AND env=? AND active=1",
               (level, env))
    pid = new_id()
    db.execute("INSERT INTO prices(id,level,env,unit_price_cents,currency,active,created_at) "
               "VALUES(?,?,?,?,?,1,?)",
               (pid, level, env, int(unit_price_cents), currency, _now()))
    return pid


def active_price(db, level, env):
    ensure_schema(db)
    return db.one("SELECT * FROM prices WHERE level=? AND env=? AND active=1 "
                  "ORDER BY created_at DESC", (level, env))


def meter(db, new_id, tid, env, session_id, level):
    """Record the single billable event for a decided session.
    Idempotent (UNIQUE session_id). Returns the event id or
    None when the session was already metered."""
    ensure_schema(db)
    existing = db.one("SELECT id FROM usage_events WHERE session_id=?", (session_id,))
    if existing:
        return None
    if env == "test":
        amount, price_id = 0, SANDBOX_FREE
    else:
        p = active_price(db, level, env)
        amount = int(p["unit_price_cents"]) if p else None
        price_id = p["id"] if p else None
    eid = new_id()
    db.execute("INSERT INTO usage_events(id,tenant_id,env,session_id,level,"
               "amount_cents,price_id,invoice_id,created_at) VALUES(?,?,?,?,?,?,?,NULL,?)",
               (eid, tid, env, session_id, level, amount, price_id, _now()))
    return eid


def usage_summary(db, tid, env, period_start, period_end):
    ensure_schema(db)
    rows = db.all("SELECT level, COUNT(*) AS n, "
                  "COALESCE(SUM(amount_cents),0) AS cents, "
                  "SUM(CASE WHEN amount_cents IS NULL THEN 1 ELSE 0 END) AS unpriced "
                  "FROM usage_events WHERE tenant_id=? AND env=? AND created_at>=? AND created_at<? "
                  "GROUP BY level ORDER BY level", (tid, env, period_start, period_end))
    return [{"level": r["level"], "verifications": r["n"],
             "amount_cents": r["cents"], "unpriced": r["unpriced"] or 0} for r in rows]


def generate_invoice(db, new_id, tid, env, period_start, period_end):
    """Draft an invoice from priced, uninvoiced events in the
    period. Unpriced events are reported, never billed at a
    guessed amount. Returns (invoice_dict, unpriced_count)."""
    ensure_schema(db)
    events = db.all("SELECT * FROM usage_events WHERE tenant_id=? AND env=? "
                    "AND invoice_id IS NULL AND created_at>=? AND created_at<? "
                    "ORDER BY created_at", (tid, env, period_start, period_end))
    priced = [e for e in events if e["amount_cents"] is not None]
    unpriced = len(events) - len(priced)
    if not priced:
        return None, unpriced
    currencies = set()
    for e in priced:
        if e["price_id"] and e["price_id"] != SANDBOX_FREE:
            p = db.one("SELECT currency FROM prices WHERE id=?", (e["price_id"],))
            currencies.add(p["currency"] if p else "USD")
    currency = currencies.pop() if len(currencies) == 1 else "USD"
    total = sum(int(e["amount_cents"]) for e in priced)
    iid = new_id()
    db.execute("INSERT INTO invoices(id,tenant_id,env,period_start,period_end,"
               "currency,total_cents,status,created_at) VALUES(?,?,?,?,?,?,?,'draft',?)",
               (iid, tid, env, period_start, period_end, currency, total, _now()))
    for e in priced:
        db.execute("UPDATE usage_events SET invoice_id=? WHERE id=?", (iid, e["id"]))
    return {"id": iid, "tenant_id": tid, "env": env, "period_start": period_start,
            "period_end": period_end, "currency": currency, "total_cents": total,
            "events": len(priced), "status": "draft"}, unpriced


def quota_exceeded(db, tid, env, now=None):
    """(exceeded, limit, used) for the tenant's LIVE monthly
    quota. Test env and unlimited tenants never exceed."""
    ensure_schema(db)
    if env != "live":
        return False, None, 0
    q = db.one("SELECT monthly_limit FROM tenant_quotas WHERE tenant_id=?", (tid,))
    if not q:
        return False, None, 0
    now = now or datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    row = db.one("SELECT COUNT(*) AS n FROM sessions WHERE tenant_id=? AND env='live' "
                 "AND created_at>=?", (tid, month_start))
    used = int(row["n"]) if row else 0
    return used >= int(q["monthly_limit"]), int(q["monthly_limit"]), used
