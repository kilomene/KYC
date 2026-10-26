#!/usr/bin/env python3
"""Live E2E (Phases 1-3): starts the real server on a test port and drives
a full LEVEL 3 verification end to end in the sandbox:

  tenant -> applicant (with address) -> L3 session -> consent -> document
  -> selfie -> proof of address -> submit (prints the full check table,
  including face_match, face_track, liveness, deepfake, authenticity,
  verification layers, PoA and screening) -> reviewer console view
  (assist block, risk score) -> reviewer override approves under
  four-eyes (two distinct reviewers) -> a signed reusable credential
  is issued -> the credential is verified -> a second tenant reuses the
  credential for a Level 1 session which auto-approves from the
  inherited checks.

Synthetic images cannot pass real face/liveness checks, and since the
2026-10-26 auto-decision build those decisive failures REJECT
automatically (no human queue in the standard path) — that is the
honest sandbox outcome. The reviewer console completes the case via a
four-eyes override, which is what the console is for.

Run:  python3 scripts/e2e_local.py
Exits non-zero on any failed assertion.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
from helpers import Server, call, multipart, id_image_bytes, selfie_bytes, poa_image_bytes, PLATFORM_ADMIN

ADMIN_HDR = {"X-Platform-Admin": PLATFORM_ADMIN}

def print_checks(summary):
    print("[e2e] checks:")
    for k in sorted(summary):
        print(f"        {k:22s} {summary[k]}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=0); a = ap.parse_args()
    with Server() as srv:
        print(f"[e2e] server at {srv.base}")
        st, t = call(srv, "POST", "/v1/tenants", {"name": "Nova Payments (internal)", "country": "NG"}, raw_headers=ADMIN_HDR)
        assert st == 201, t
        key = t["keys"]["test"]["key"]
        print(f"[e2e] tenant created, test key prefix {key[:14]}…")

        # Applicant with a postal address (Level 3 PoA matches against it).
        st, app = call(srv, "POST", "/v1/applicants",
                       {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG",
                        "address_line": "12 Marina Road", "city": "Lagos"}, key=key)
        assert st == 201, app
        st, sess0 = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 3}, key=key)
        assert st == 201, sess0
        ctx = {"token": sess0["flow_token"], "session": sess0}
        call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"}, token=ctx["token"])
        st, r = multipart(srv, "/v1/flow/document",
                          {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna",
                           "doc_last_name": "Eriksson", "doc_dob": "1974-08-12", "doc_expiry": "2032-04-15"},
                          {"front": ("front.png", id_image_bytes(), "image/png")}, ctx["token"])
        assert st == 201, r
        st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, ctx["token"])
        assert st == 201, r
        print(f"[e2e] applicant {app['id']} + L3 session {ctx['session']['id']}; consent/document/selfie uploaded")

        st, r = multipart(srv, "/v1/flow/poa", {}, {"document": ("bill.png", poa_image_bytes(), "image/png")}, ctx["token"])
        assert st == 201, r
        print("[e2e] proof of address uploaded")

        st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
        assert st == 200, view
        print(f"[e2e] submit → status={view['status']}")
        print_checks(view["checks_summary"])
        assert view["checks_summary"]["poa"] == "pass", view["checks_summary"]
        assert view["checks_summary"]["screening_sanctions"] in ("pass", "unclear"), view["checks_summary"]
        assert view["status"] == "rejected", view  # synthetic face/liveness fail decisively -> automatic rejection
        assert "verification_layers" in view["checks_summary"], view["checks_summary"]

        st, detail = call(srv, "GET", f"/v1/cases/{view['case_id']}", key=key)
        assert detail["documents"] and detail["biometrics"], detail
        dec0 = detail["session"]["decision"]
        print(f"[e2e] case {view['case_id']} opened · risk {dec0['risk_score']} ({dec0['risk_band']}) · config {dec0['config_version']}")
        assist = detail["assist"]
        print(f"[e2e] assist: suggested={assist['suggested_disposition']} · mismatches={len(assist['mismatches'])} · '{assist['label']}'")
        assert assist["suggested_disposition"] in ("approve", "reject", "request_more")

        # Four-eyes override: overriding an engine rejection parks at
        # awaiting_second; a DIFFERENT reviewer confirms it.
        st, rev_a = call(srv, "POST", "/v1/users", {"name": "Reviewer A", "role": "reviewer"}, key=key)
        assert st == 201, rev_a
        st, rev_b = call(srv, "POST", "/v1/users", {"name": "Reviewer B", "role": "reviewer"}, key=key)
        assert st == 201, rev_b
        st, dec = call(srv, "POST", f"/v1/cases/{view['case_id']}/decide",
                       {"action": "approve", "reason": "E2E: document, selfie and PoA compared by eye; details match."},
                       key=key, raw_headers={"X-Reviewer-Key": rev_a["token"]})
        assert st == 202 and dec["status"] == "awaiting_second", dec
        print("[e2e] reviewer A approved -> awaiting a second reviewer (four-eyes)")
        st, dec = call(srv, "POST", f"/v1/cases/{view['case_id']}/confirm",
                       {"reason": "E2E: second pair of eyes, agreed."},
                       key=key, raw_headers={"X-Reviewer-Key": rev_b["token"]})
        assert st == 200 and dec["outcome"] == "approved", dec
        print("[e2e] reviewer B confirmed -> approved")

        st, sess = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}", key=key)
        assert sess["status"] == "approved", sess
        print(f"[e2e] GET session → approved (decided_by={sess['decision']['decided_by']})")

        # Reusable verified credential: issued on approval, verifiable by
        # any tenant, reusable for a lower-level session.
        st, cred_view = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}/credential", key=key)
        assert st == 200 and cred_view.get("credential"), cred_view
        cred = cred_view["credential"]
        print(f"[e2e] credential issued: {cred['claims']['credential_id']} level {cred['claims']['level']} over_18={cred['claims']['over_18']}")
        st, t2 = call(srv, "POST", "/v1/tenants", {"name": "Agent Exchange (internal)", "country": "NG"}, raw_headers=ADMIN_HDR)
        key2 = t2["keys"]["test"]["key"]
        st, v = call(srv, "POST", "/v1/credentials/verify", {"credential": cred}, key=key2)
        assert v["valid"], v
        print("[e2e] credential verified by a second tenant (claims only, no document data)")
        st, sess2 = call(srv, "POST", "/v1/sessions", {"level": 1, "credential": cred}, key=key2)
        assert st == 201 and "ocr" in sess2["inherited_checks"], sess2
        call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"}, token=sess2["flow_token"])
        st, view2 = call(srv, "POST", "/v1/flow/submit", {}, token=sess2["flow_token"])
        assert view2["status"] == "approved" and view2["decision"]["decided_by"] == "engine", view2
        print(f"[e2e] credential-based L1 session auto-approved from inherited checks {sorted(sess2['inherited_checks'])} (biometrics/liveness never inherited)")

        print("[e2e] PASS")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
