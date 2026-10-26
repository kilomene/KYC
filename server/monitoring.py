"""Ongoing monitoring (Phase 3): re-screen approved applicants against
the CURRENT lists. A new match creates a pending screening hit, a
monitoring alert, a fresh review case for the applicant's approved
session, and fires the screening.hit_new webhook. It never un-approves
anyone by itself — a human dispositions the hit.

Used by POST /v1/monitoring/rescreen and as a CLI:
    python3 -m server.monitoring --tenant <tenant_id> --env test [--data-dir data]
"""
import argparse, json
from .db import DB, new_id, now_iso
from . import screening as SCR
from . import webhooks as WH

def run_rescreen(db, data_dir, tenant_id, env, threshold=SCR.DEFAULT_THRESHOLD):
    entries = SCR.load_lists(data_dir)
    approved = db.all(
        "SELECT DISTINCT a.* FROM applicants a JOIN sessions s ON s.applicant_id=a.id "
        "WHERE a.tenant_id=? AND a.env=? AND s.status='approved' AND a.data_deleted_at IS NULL",
        (tenant_id, env))
    new_hits, alerts = [], []
    for app in approved:
        name = f"{app['first_name'] or ''} {app['last_name'] or ''}".strip()
        if not name:
            continue
        for h in SCR.screen_person(name, app["dob"], entries, threshold):
            existing = db.one("SELECT id FROM screening_hits WHERE applicant_id=? AND entry_id=? AND list_source=?",
                              (app["id"], h["entry_id"], h["list_source"]))
            if existing:
                continue
            sess = db.one("SELECT id FROM sessions WHERE applicant_id=? AND status='approved' ORDER BY created_at DESC LIMIT 1", (app["id"],))
            sid = sess["id"] if sess else None
            hid = new_id()
            db.execute("INSERT INTO screening_hits(id,tenant_id,env,session_id,applicant_id,entry_id,list_source,matched_name,matched_dob,matched_country,score,status,origin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (hid, tenant_id, env, sid, app["id"], h["entry_id"], h["list_source"], h["matched_name"],
                        h["matched_dob"], h["matched_country"], h["score"], "pending", "monitoring", now_iso(), now_iso()))
            # Open a case on the approved session if none is open.
            case_id = None
            if sid:
                open_case = db.one("SELECT id FROM cases WHERE session_id=? AND status IN ('open','awaiting_second')", (sid,))
                if open_case:
                    case_id = open_case["id"]
                else:
                    case_id = new_id()
                    db.execute("INSERT INTO cases(id,session_id,tenant_id,env,status,origin_outcome,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                               (case_id, sid, tenant_id, env, "open", "monitoring_hit", now_iso(), now_iso()))
            aid = new_id()
            db.execute("INSERT INTO monitoring_alerts(id,tenant_id,env,applicant_id,hit_id,case_id,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (aid, tenant_id, env, app["id"], hid, case_id, "open", now_iso()))
            db.audit("system", None, tenant_id, "monitoring.hit_new", "applicant", app["id"],
                     metadata={"hit_id": hid, "list_source": h["list_source"], "score": h["score"]})
            WH.fire(db, tenant_id, env, "screening.hit_new",
                    {"applicant_id": app["id"], "hit_id": hid, "case_id": case_id,
                     "list_source": h["list_source"], "matched_name": h["matched_name"], "score": h["score"]})
            new_hits.append({"hit_id": hid, "applicant_id": app["id"], "list_source": h["list_source"], "score": h["score"]})
            alerts.append(aid)
    return {"rescreened": len(approved), "new_hits": len(new_hits), "hits": new_hits, "alerts": alerts,
            "lists_loaded": len(entries)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--env", default="test", choices=["test", "live"])
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    db = DB(a.data_dir)
    print(json.dumps(run_rescreen(db, a.data_dir, a.tenant, a.env), indent=2))
