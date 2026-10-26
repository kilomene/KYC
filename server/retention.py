"""Retention helper (endpoint-free CLI).

Deletes stored images for DECIDED sessions (approved / rejected /
needs_more_information) whose latest decision is older than --days, and
records each deletion in the deletions table + audit log. Decision and
audit records themselves are kept (the audit skeleton) — only image
files are removed.

Usage:  python3 -m server.retention --days 90 [--data-dir data] [--now 2026-..]
"""
import argparse, os
from datetime import datetime, timezone, timedelta
from .db import DB, now_iso

TERMINAL = ("approved", "rejected", "needs_more_information")

def run_retention(db: DB, data_dir: str, days: int, now: datetime = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()
    rows = db.all(
        "SELECT s.id AS sid, s.tenant_id, d.created_at AS decided_at FROM sessions s "
        "JOIN decisions d ON d.id = s.decision_id WHERE s.status IN (%s) AND d.created_at < ?"
        % ",".join("?" * len(TERMINAL)), (*TERMINAL, cutoff))
    files_deleted = 0; sessions_touched = 0
    for r in rows:
        touched = False
        for table, cols in (("documents", ("storage_path", "back_storage_path")), ("biometric_captures", ("storage_path",))):
            for row in db.all(f"SELECT id, {', '.join(cols)} FROM {table} WHERE session_id=?", (r["sid"],)):
                for col in cols:
                    if row[col]:
                        fp = os.path.join(data_dir, row[col])
                        if os.path.isfile(fp):
                            os.remove(fp); files_deleted += 1; touched = True
                sets = ", ".join(f"{c}=NULL" for c in cols)
                db.execute(f"UPDATE {table} SET {sets} WHERE id=?", (row["id"],))
        if True:
            sessions_touched += 1
            db.execute("INSERT INTO deletions(tenant_id,target_type,target_id,kind,detail,at) VALUES(?,?,?,?,?,?)",
                       (r["tenant_id"], "session", r["sid"], "retention", f"days={days}", now_iso()))
            db.audit("system", None, r["tenant_id"], "retention.delete_images", "session", r["sid"], metadata={"days": days})
    return {"sessions": sessions_touched, "files_deleted": files_deleted, "cutoff": cutoff}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    db = DB(a.data_dir)
    print(run_retention(db, a.data_dir, a.days))
