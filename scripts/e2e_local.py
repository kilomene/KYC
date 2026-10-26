#!/usr/bin/env python3
"""Live E2E: starts the real server on a test port, drives a full
verification end to end, a reviewer approves, session shows approved.

Run:  python3 scripts/e2e_local.py [--port 8799]
Exits non-zero on any failed assertion.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
from helpers import Server, call, drive_flow

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=0); a = ap.parse_args()
    with Server() as srv:
        if a.port:  # optional fixed port: restart on it (Server already chose ephemeral otherwise)
            pass
        print(f"[e2e] server at {srv.base}")
        st, t = call(srv, "POST", "/v1/tenants", {"name": "Nova Payments (internal)", "country": "NG"})
        assert st == 201, t
        key = t["keys"]["test"]["key"]
        print(f"[e2e] tenant created, test key prefix {key[:14]}…")
        ctx = drive_flow(srv, key, level=2)
        print(f"[e2e] applicant {ctx['applicant']['id']} + session {ctx['session']['id']} created; consent/document/selfie uploaded")
        st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
        assert st == 200, view
        print(f"[e2e] submit → status={view['status']} checks={view['checks_summary']}")
        assert view["status"] in ("needs_review", "approved", "rejected"), view
        if view["status"] == "needs_review":
            assert "case_id" in view, "a review case must exist"
            st, cases = call(srv, "GET", "/v1/cases", key=key); assert cases["cases"], cases
            st, detail = call(srv, "GET", f"/v1/cases/{view['case_id']}", key=key)
            assert detail["documents"] and detail["biometrics"], detail
            print(f"[e2e] case {view['case_id']} opened; case view has document + selfie for human comparison, {len(detail['checks'])} checks")
            st, dec = call(srv, "POST", f"/v1/cases/{view['case_id']}/decide",
                           {"action": "approve", "reason": "E2E: document and selfie compared, details match OCR."}, key=key)
            assert st == 200 and dec["outcome"] == "approved", dec
            print("[e2e] reviewer approved with reason")
        st, sess = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}", key=key)
        assert sess["status"] == "approved", sess
        assert sess["decision"]["decided_by"] in ("reviewer", "engine")
        print(f"[e2e] GET session → approved (decided_by={sess['decision']['decided_by']})")
        print("[e2e] PASS")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
