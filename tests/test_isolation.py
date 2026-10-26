"""WS3 tenant-isolation battery: automated cross-tenant attack tests.

Every test ATTEMPTS the cross-tenant access with tenant B's real
credentials and asserts refusal. Two tenants are built with real data
(applicant, flow session + uploaded document/selfie, an opened case, a
KYB business, a reviewer user, a webhook endpoint with deliveries, a
verified credential) and B tries to read, modify or enumerate each of
A's objects through every route that exposes it. Refusals must be the
SAME 404 shape as a random nonexistent id (no existence oracle), and
test/live env separation is exercised the same way.
"""
import io, json, os, sys, unittest, urllib.request, urllib.error, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, multipart, make_tenant, drive_flow, id_image_bytes, selfie_bytes
from server.db import DB
from server import credentials as CRED

def raw_get(srv, path, key=None, token=None, headers=None):
    h = dict(headers or {})
    if key: h["Authorization"] = f"Bearer {key}"
    if token: h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(srv.base + path, method="GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def build_tenant_world(srv, name, webhook_url="http://127.0.0.1:1/hook", with_credential=True):
    """A tenant with one of everything. Returns a dict of ids/keys."""
    tid, test_key, live_key = make_tenant(srv, name)
    st, ep = call(srv, "POST", "/v1/webhooks", {"url": webhook_url, "events": []}, key=test_key)
    assert st == 201, ep
    # Expired-document L1 flow -> engine rejection -> an open case.
    ctx = drive_flow(srv, test_key, level=1, doc_fields={"doc_expiry": "2019-01-01"},
                     doc_bytes=id_image_bytes(expiry="2019-01-01"))
    st, view = call(srv, "POST", "/v1/flow/submit", {}, **{"token": ctx["token"]})
    assert st == 200 and view.get("case_id"), view
    case_id = view["case_id"]
    st, detail = call(srv, "GET", f"/v1/cases/{case_id}", key=test_key)
    assert st == 200, detail
    doc_id = detail["documents"][0]["id"]
    bio_id = detail["biometrics"][0]["id"]
    # KYB business.
    st, biz = call(srv, "POST", "/v1/businesses",
                   {"legal_name": f"{name} Ltd", "registration_number": "RC1234567", "country": "NG"}, key=test_key)
    assert st == 201, biz
    # Reviewer user.
    st, user = call(srv, "POST", "/v1/users", {"name": f"{name} Reviewer", "role": "reviewer"}, key=test_key)
    assert st == 201, user
    # A real signed credential for this applicant/session (issued via
    # the same code path approvals use).
    cred = None
    if with_credential:
        db = DB(srv.data_dir)
        app_row = db.one("SELECT * FROM applicants WHERE id=?", (ctx["applicant"]["id"],))
        sess_row = db.one("SELECT * FROM sessions WHERE id=?", (ctx["session"]["id"],))
        cred = CRED.issue_credential(db, srv.data_dir, tid, "test", app_row, sess_row, ["ocr", "consistency"])
    return {"tid": tid, "test_key": test_key, "live_key": live_key,
            "applicant_id": ctx["applicant"]["id"], "session_id": ctx["session"]["id"],
            "flow_token": ctx["token"], "case_id": case_id, "doc_id": doc_id, "bio_id": bio_id,
            "business_id": biz["id"], "user_id": user["id"], "user_token": user["token"],
            "webhook_id": ep["id"], "credential": cred,
            "credential_id": cred["claims"]["credential_id"] if cred else None}

class TestCrossTenantReads(unittest.TestCase):
    def test_applicant_session_case_reads_refused(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            b = build_tenant_world(srv, "Tenant B")
            bk = b["test_key"]
            # B reading A's objects: all 404.
            for path in (f"/v1/applicants/{a['applicant_id']}",
                         f"/v1/sessions/{a['session_id']}",
                         f"/v1/sessions/{a['session_id']}/checks",
                         f"/v1/sessions/{a['session_id']}/credential",
                         f"/v1/cases/{a['case_id']}",
                         f"/v1/businesses/{a['business_id']}"):
                st, r = call(srv, "GET", path, key=bk)
                self.assertEqual(st, 404, (path, r))
            # B's lists contain only B's objects.
            st, r = call(srv, "GET", "/v1/sessions", key=bk)
            ids = [s["id"] for s in r["sessions"]]
            self.assertIn(b["session_id"], ids); self.assertNotIn(a["session_id"], ids)
            st, r = call(srv, "GET", "/v1/cases", key=bk)
            self.assertNotIn(a["case_id"], [c["id"] for c in r["cases"]])
            st, r = call(srv, "GET", "/v1/users", key=bk)
            self.assertNotIn(a["user_id"], [u["id"] for u in r["users"]])
            st, r = call(srv, "GET", "/v1/webhooks", key=bk)
            self.assertNotIn(a["webhook_id"], [e["id"] for e in r["endpoints"]])
            st, r = call(srv, "GET", "/v1/businesses", key=bk)
            self.assertNotIn(a["business_id"], [x["id"] for x in r["businesses"]])
            # Control: A reads its own objects fine.
            st, r = call(srv, "GET", f"/v1/applicants/{a['applicant_id']}", key=a["test_key"])
            self.assertEqual(st, 200, r)
            st, r = call(srv, "GET", f"/v1/cases/{a['case_id']}", key=a["test_key"])
            self.assertEqual(st, 200, r)

    def test_no_existence_oracle(self):
        """A real other-tenant id and a random UUID must produce the
        IDENTICAL error response — the API must not confirm existence."""
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            _, bk, _ = make_tenant(srv, "Tenant B")
            ghost = str(uuid.uuid4())
            for tmpl, real in (("/v1/applicants/{}", a["applicant_id"]),
                               ("/v1/sessions/{}", a["session_id"]),
                               ("/v1/cases/{}", a["case_id"]),
                               ("/v1/businesses/{}", a["business_id"])):
                st1, r1 = call(srv, "GET", tmpl.format(real), key=bk)
                st2, r2 = call(srv, "GET", tmpl.format(ghost), key=bk)
                self.assertEqual(st1, 404, (tmpl, r1))
                self.assertEqual((st1, r1), (st2, r2), tmpl)

    def test_image_reads_refused_cross_tenant(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            _, bk, _ = make_tenant(srv, "Tenant B")
            for path in (f"/v1/documents/{a['doc_id']}/image",
                         f"/v1/documents/{a['doc_id']}/image?side=back",
                         f"/v1/biometrics/{a['bio_id']}/image"):
                st, body = raw_get(srv, path, key=bk)
                self.assertEqual(st, 404, path)
                self.assertNotIn(b"PNG", body[:8])
            # Control: the owner tenant gets the bytes.
            st, body = raw_get(srv, f"/v1/documents/{a['doc_id']}/image", key=a["test_key"])
            self.assertEqual(st, 200)
            self.assertTrue(len(body) > 1000)

class TestCrossTenantWrites(unittest.TestCase):
    def test_case_actions_refused_cross_tenant(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            b = build_tenant_world(srv, "Tenant B")
            bk, brt = b["test_key"], b["user_token"]
            # B's API key AND B's genuine reviewer token both refused.
            for headers in (None, {"X-Reviewer-Key": brt}):
                st, r = call(srv, "POST", f"/v1/cases/{a['case_id']}/decide",
                             {"action": "reject", "reason": "cross-tenant attack"}, key=bk, raw_headers=headers)
                self.assertEqual(st, 404, r)
                st, r = call(srv, "POST", f"/v1/cases/{a['case_id']}/confirm",
                             {"reason": "cross-tenant attack"}, key=bk, raw_headers=headers)
                self.assertEqual(st, 404, r)
                st, r = call(srv, "POST", f"/v1/cases/{a['case_id']}/hits/{uuid.uuid4()}/dispose",
                             {"disposition": "confirmed", "reason": "cross-tenant attack"}, key=bk, raw_headers=headers)
                self.assertEqual(st, 404, r)
            # A's case is untouched: still open.
            st, detail = call(srv, "GET", f"/v1/cases/{a['case_id']}", key=a["test_key"])
            self.assertEqual(detail["case"]["status"], "open")

    def test_business_user_webhook_writes_refused(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            _, bk, _ = make_tenant(srv, "Tenant B")
            st, r = call(srv, "POST", f"/v1/businesses/{a['business_id']}/people",
                         {"applicant_id": a["applicant_id"], "role": "director"}, key=bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "POST", f"/v1/businesses/{a['business_id']}/evaluate", {}, key=bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "POST", f"/v1/businesses/{a['business_id']}/registry",
                         {"status": "confirmed", "reason": "cross-tenant attack"}, key=bk)
            self.assertEqual(st, 404, r)
            st, r = multipart(srv, f"/v1/businesses/{a['business_id']}/document", {},
                              {"document": ("doc.bin", b"forged", "application/octet-stream")}, bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "POST", f"/v1/users/{a['user_id']}/revoke", {}, key=bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "POST", f"/v1/users/{a['user_id']}/mfa/enroll", {}, key=bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "POST", f"/v1/sessions/{a['session_id']}/cancel", {}, key=bk)
            self.assertEqual(st, 404, r)
            # Config: B's write must not move A's config.
            st, before = call(srv, "GET", "/v1/config?level=1", key=a["test_key"])
            st, r = call(srv, "PUT", "/v1/config", {"level": 1, "config": {"sla_hours": 7}}, key=bk)
            self.assertEqual(st, 200, r)
            st, after = call(srv, "GET", "/v1/config?level=1", key=a["test_key"])
            self.assertEqual(after["config"]["sla_hours"], before["config"]["sla_hours"])
            # Erasure of A's applicant by B: refused, and A intact.
            st, r = call(srv, "DELETE", f"/v1/applicants/{a['applicant_id']}", key=bk)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "GET", f"/v1/applicants/{a['applicant_id']}", key=a["test_key"])
            self.assertEqual(st, 200, r)
            self.assertIsNone(r["data_deleted_at"])

    def test_webhook_deliveries_scoped_and_replay_refused(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            _, bk, _ = make_tenant(srv, "Tenant B")
            st, r = call(srv, "GET", "/v1/webhooks/deliveries", key=a["test_key"])
            self.assertEqual(st, 200, r)
            self.assertGreaterEqual(len(r["deliveries"]), 1)  # submit fired events
            delivery_id = r["deliveries"][0]["id"]
            st, r = call(srv, "GET", "/v1/webhooks/deliveries", key=bk)
            self.assertEqual(r["deliveries"], [])
            st, r = call(srv, "POST", f"/v1/webhooks/deliveries/{delivery_id}/replay", {}, key=bk)
            self.assertEqual(st, 404, r)

class TestEnvSeparation(unittest.TestCase):
    def test_test_key_cannot_touch_live_data_and_vice_versa(self):
        with Server() as srv:
            tid, test_key, live_key = make_tenant(srv, "Env Tenant")
            st, app = call(srv, "POST", "/v1/applicants",
                           {"first_name": "Live", "last_name": "Person", "dob": "1990-01-01", "country": "NG"}, key=live_key)
            self.assertEqual(st, 201, app)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=live_key)
            self.assertEqual(st, 201, sess)
            # The test key sees neither the live applicant nor session.
            st, r = call(srv, "GET", f"/v1/applicants/{app['id']}", key=test_key)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "GET", f"/v1/sessions/{sess['id']}", key=test_key)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "GET", "/v1/sessions", key=test_key)
            self.assertEqual(r["sessions"], [])
            # And the live key cannot see test-env data either.
            st, tapp = call(srv, "POST", "/v1/applicants",
                            {"first_name": "Test", "last_name": "Person", "dob": "1990-01-01", "country": "NG"}, key=test_key)
            self.assertEqual(st, 201, tapp)
            st, r = call(srv, "GET", f"/v1/applicants/{tapp['id']}", key=live_key)
            self.assertEqual(st, 404, r)

class TestFlowTokenBoundaries(unittest.TestCase):
    def test_flow_token_is_session_bound_and_not_an_api_key(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            b = build_tenant_world(srv, "Tenant B", with_credential=False)
            # Control: A's token reads A's flow session.
            st, r = call(srv, "GET", "/v1/flow/session", **{"token": a["flow_token"]})
            self.assertEqual(st, 200, r)
            # A tampered token is refused.
            bad = a["flow_token"][:-2] + ("AA" if not a["flow_token"].endswith("AA") else "BB")
            st, r = call(srv, "GET", "/v1/flow/session", token=bad)
            self.assertEqual(st, 401, r)
            # A's flow token cannot attach a back side to B's document
            # (the lookup is scoped to the token's own session).
            st, r = multipart(srv, "/v1/flow/document/back",
                              {"document_id": b["doc_id"]},
                              {"back": ("back.png", id_image_bytes(), "image/png")}, a["flow_token"])
            self.assertEqual(st, 404, r)
            # A flow token is not an API key, and an API key is not a flow token.
            st, r = call(srv, "GET", f"/v1/applicants/{a['applicant_id']}", **{"token": a["flow_token"]})
            self.assertEqual(st, 401, r)
            st, r = call(srv, "GET", "/v1/flow/session", key=a["test_key"])
            self.assertEqual(st, 401, r)
            # B's token sees B's credential state only: A has a credential
            # on A's session; B's flow credential lookup finds none of A's.
            st, r = call(srv, "GET", "/v1/flow/credential", **{"token": a["flow_token"]})
            self.assertEqual(st, 200, r)
            st, r = call(srv, "GET", "/v1/flow/credential", **{"token": b["flow_token"]})
            self.assertEqual(st, 404, r)

    def test_credential_verify_is_claims_only_and_revoke_is_tenant_scoped(self):
        with Server() as srv:
            a = build_tenant_world(srv, "Tenant A")
            _, bk, _ = make_tenant(srv, "Tenant B")
            # Verification by a second tenant is BY DESIGN (selective
            # disclosure): it returns claims only — never document data.
            st, v = call(srv, "POST", "/v1/credentials/verify", {"credential": a["credential"]}, key=bk)
            self.assertEqual(st, 200, v)
            self.assertTrue(v["valid"], v)
            claims_blob = json.dumps(v["claims"])
            # Claims carry check TYPE names (e.g. "ocr" in checks_passed)
            # by design — what must never appear is document DATA:
            # numbers, extracted text, names, images, storage paths.
            for forbidden in ("L898902C3", "doc_number", "ocr_text", "image", "storage_path", "Eriksson", "1974"):
                self.assertNotIn(forbidden, claims_blob)
            # But B cannot revoke A's credential, nor read it via A's session.
            st, r = call(srv, "POST", "/v1/credentials/revoke", {"credential_id": a["credential_id"]}, key=bk)
            self.assertEqual(st, 404, r)
            st, v2 = call(srv, "POST", "/v1/credentials/verify", {"credential": a["credential"]}, key=bk)
            self.assertTrue(v2["valid"], v2)  # still active: the revoke really was refused
            # A tampered credential never verifies.
            forged = {"claims": {**a["credential"]["claims"], "level": 3}, "signature": a["credential"]["signature"]}
            st, v3 = call(srv, "POST", "/v1/credentials/verify", {"credential": forged}, key=bk)
            self.assertFalse(v3["valid"], v3)

if __name__ == "__main__":
    unittest.main()
