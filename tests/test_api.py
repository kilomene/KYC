import hashlib, hmac, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, multipart, make_tenant, drive_flow, id_image_bytes
from server import webhooks as WH

class TestAPI(unittest.TestCase):
    def test_tenant_keys_shown_once_and_hashed_flow(self):
        with Server() as srv:
            tid, test_key, live_key = make_tenant(srv)
            self.assertTrue(test_key.startswith("kyc_test_"))
            st, r = call(srv, "GET", "/v1/keys", key=test_key)
            self.assertEqual(st, 200)
            self.assertNotIn(test_key, json.dumps(r))  # plaintext never returned again

    def test_revoked_key_rejected(self):
        with Server() as srv:
            tid, test_key, live_key = make_tenant(srv)
            st, keys = call(srv, "GET", "/v1/keys", key=test_key)
            kid = [k for k in keys["keys"] if k["env"] == "test"][0]["id"]
            st, _ = call(srv, "POST", f"/v1/keys/{kid}/revoke", {}, key=test_key)
            self.assertEqual(st, 200)
            st, _ = call(srv, "GET", "/v1/sessions", key=test_key)
            self.assertEqual(st, 401)

    def test_env_separation(self):
        with Server() as srv:
            tid, test_key, live_key = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "NG"}, key=test_key)
            self.assertEqual(st, 201)
            st, _ = call(srv, "GET", f"/v1/applicants/{app['id']}", key=live_key)
            self.assertEqual(st, 404)  # live key cannot read test-env data

    def test_tenant_isolation(self):
        with Server() as srv:
            _, key_a, _ = make_tenant(srv, "Tenant A")
            _, key_b, _ = make_tenant(srv, "Tenant B")
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "NG"}, key=key_a)
            st, _ = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key_b)
            self.assertEqual(st, 404)
            st, _ = call(srv, "GET", "/v1/cases", key=key_b)
            self.assertEqual(st, 200)

    def test_flow_level2_goes_to_review_and_reviewer_approves(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(st, 200, view)
            # Phase 2: face_match RUNS now (it can no longer be not_run);
            # the synthetic drawing has no detectable real face, so it can
            # never pass, and with no liveness video the session cannot
            # complete. Auto-decision doctrine (2026-10-26): that is now
            # an automatic REJECTION, not a review queue — a case still
            # opens so a reviewer may override (four-eyes, below).
            self.assertEqual(view["status"], "rejected", view)
            self.assertIn(view["checks_summary"].get("face_match"), ("unclear", "error", "fail"))
            self.assertEqual(view["checks_summary"].get("liveness"), "not_run")
            self.assertIn("case_id", view)
            # reviewer needs a reason
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/decide", {"action": "approve", "reason": "  "}, key=test_key)
            self.assertEqual(st, 422)
            # Overriding an engine rejection takes four eyes: reviewer A
            # decides (parked), a DIFFERENT reviewer B confirms.
            st, rev_a = call(srv, "POST", "/v1/users", {"name": "Reviewer A", "role": "reviewer"}, key=test_key)
            self.assertEqual(st, 201, rev_a)
            st, rev_b = call(srv, "POST", "/v1/users", {"name": "Reviewer B", "role": "reviewer"}, key=test_key)
            self.assertEqual(st, 201, rev_b)
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/decide",
                         {"action": "approve", "reason": "Document and selfie compared by eye; details match."},
                         key=test_key, raw_headers={"X-Reviewer-Key": rev_a["token"]})
            self.assertEqual(st, 202, r); self.assertEqual(r["status"], "awaiting_second")
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/confirm",
                         {"reason": "Second pair of eyes: agreed."},
                         key=test_key, raw_headers={"X-Reviewer-Key": rev_b["token"]})
            self.assertEqual(st, 200, r); self.assertEqual(r["outcome"], "approved")
            st, sess = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}", key=test_key)
            self.assertEqual(sess["status"], "approved")
            self.assertEqual(sess["decision"]["decided_by"], "reviewer")

    def test_expired_document_hard_rejects(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=1, doc_fields={"doc_expiry": "2019-01-01"},
                             doc_bytes=id_image_bytes(expiry="2019-01-01"))
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(view["status"], "rejected", view)
            self.assertIn("document_expired", view["decision"]["reason_codes"])

    def test_erasure_deletes_files_and_pii(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=1)
            files_dir = os.path.join(srv.data_dir, "files")
            before = sum(len(fs) for _, _, fs in os.walk(files_dir))
            self.assertGreater(before, 0)
            st, r = call(srv, "DELETE", f"/v1/applicants/{ctx['applicant']['id']}", key=test_key)
            self.assertEqual(st, 200, r); self.assertGreaterEqual(r["files_deleted"], 2)
            after = sum(len(fs) for _, _, fs in os.walk(files_dir))
            self.assertEqual(after, 0)
            st, app = call(srv, "GET", f"/v1/applicants/{ctx['applicant']['id']}", key=test_key)
            self.assertIsNone(app["first_name"]); self.assertIsNotNone(app["data_deleted_at"])

    def test_consent_required_before_upload(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "NG"}, key=test_key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=test_key)
            st, r = multipart(srv, "/v1/flow/document", {"kind": "passport", "issuing_country": "NG"},
                              {"front": ("f.png", id_image_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 422)

    def test_national_id_rejected_for_passport_only_country(self):
        # FR is in the launch list for passports only (owner-expanded D3).
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "FR"}, key=test_key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=test_key)
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
            st, r = multipart(srv, "/v1/flow/document", {"kind": "national_id", "issuing_country": "FR"},
                              {"front": ("f.png", id_image_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 422)

    def test_expanded_launch_coverage(self):
        # Passport accepted for a passport-only launch country (KE), and
        # licence + national ID accepted for the licence/ID set (CA, GB).
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            for country, kind, applicant_country in (("KE", "passport", "KE"), ("CA", "drivers_licence", "CA"), ("GB", "national_id", "GB"), ("IN", "passport", "IN"), ("AE", "passport", "AE")):
                st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": applicant_country}, key=test_key)
                self.assertEqual(st, 201, app)
                st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=test_key)
                call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
                st, r = multipart(srv, "/v1/flow/document", {"kind": kind, "issuing_country": country},
                                  {"front": ("f.png", id_image_bytes(), "image/png")}, sess["flow_token"])
                self.assertEqual(st, 201, (country, kind, r))
            # A country outside the launch list is rejected.
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "JP"}, key=test_key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=test_key)
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
            st, r = multipart(srv, "/v1/flow/document", {"kind": "passport", "issuing_country": "JP"},
                              {"front": ("f.png", id_image_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 422)

    def test_session_is_resumable_mid_flow(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG"}, key=test_key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 2}, key=test_key)
            token = sess["flow_token"]
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=token)
            st, r = multipart(srv, "/v1/flow/document",
                              {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna", "doc_last_name": "Eriksson", "doc_dob": "1974-08-12", "doc_expiry": "2032-04-15"},
                              {"front": ("f.png", id_image_bytes(), "image/png")}, token)
            self.assertEqual(st, 201, r)
            # Applicant "drops" and reopens the same unexpired link:
            st, info = call(srv, "GET", "/v1/flow/session", token=token)
            self.assertEqual(st, 200, info)
            self.assertEqual(len(info["documents"]), 1)          # upload survived
            self.assertFalse(info["selfie_uploaded"])
            self.assertEqual(info["session"]["status"], "in_progress")
            # …and can simply continue from the selfie step:
            from helpers import selfie_bytes
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("s.png", selfie_bytes(), "image/png")}, token)
            self.assertEqual(st, 201, r)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            # L2 without a liveness video: incomplete verification ->
            # automatic rejection under the 2026-10-26 doctrine (was
            # needs_review). Resumability itself is what this test proves.
            self.assertEqual(view["status"], "rejected")

    def test_fraud_signals_recorded_at_submit(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"],
                            raw_headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10)"})
            self.assertEqual(st, 200, view)
            st, ch = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}/checks", key=test_key)
            sig = [c for c in ch["checks"] if c["type"] == "fraud_signals"]
            self.assertEqual(len(sig), 1, ch)
            self.assertIn(sig[0]["status"], ("pass", "unclear"))
            f = sig[0]["findings"]
            self.assertIn("tenant_sessions_last_hour", f)
            self.assertIn("document_country", f)
            self.assertIn("device_class", f)

    def test_session_cancel_kills_flow_token(self):
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "NG"}, key=test_key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=test_key)
            st, _ = call(srv, "POST", f"/v1/sessions/{sess['id']}/cancel", {}, key=test_key)
            self.assertEqual(st, 200)
            st, _ = call(srv, "GET", "/v1/flow/session", token=sess["flow_token"])
            self.assertEqual(st, 401)

    def test_retention_deletes_old_decided_images(self):
        with Server() as srv:
            from server.db import DB
            from server.retention import run_retention
            from datetime import datetime, timezone, timedelta
            tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            call(srv, "POST", f"/v1/cases/{view['case_id']}/decide", {"action": "approve", "reason": "ok compared"}, key=test_key)
            db = DB(srv.data_dir)
            future = datetime.now(timezone.utc) + timedelta(days=365)
            res = run_retention(db, srv.data_dir, days=90, now=future)
            self.assertGreaterEqual(res["files_deleted"], 2, res)
            files_dir = os.path.join(srv.data_dir, "files")
            self.assertEqual(sum(len(fs) for _, _, fs in os.walk(files_dir)), 0)

class TestWebhookSigning(unittest.TestCase):
    def test_signature_roundtrip_and_tamper(self):
        body = b'{"event":"session.completed"}'
        header, _, _ = WH.sign("whsec_test", body, ts=1700000000)
        self.assertTrue(WH.verify("whsec_test", body, header))
        self.assertFalse(WH.verify("whsec_test", body + b"x", header))
        self.assertFalse(WH.verify("wrong", body, header))
    def test_signature_matches_manual_hmac(self):
        body = b"abc"; header, ts, mac = WH.sign("s3cret", body, ts=42)
        expected = hmac.new(b"s3cret", b"42." + body, hashlib.sha256).hexdigest()
        self.assertEqual(mac, expected)

    def test_webhook_delivery_logged(self):
        # Point an endpoint at the server's own /healthz (will 501/404 on POST
        # or succeed as delivery attempt) — what matters is a logged attempt.
        with Server() as srv:
            tid, test_key, _ = make_tenant(srv)
            st, ep = call(srv, "POST", "/v1/webhooks", {"url": srv.base + "/healthz", "events": []}, key=test_key)
            self.assertEqual(st, 201, ep)
            self.assertTrue(ep["secret"].startswith("whsec_"))
            ctx = drive_flow(srv, test_key, level=1)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            from server.db import DB
            db = DB(srv.data_dir)
            rows = db.all("SELECT * FROM webhook_deliveries WHERE tenant_id=?", (tid,))
            self.assertGreaterEqual(len(rows), 1)
            self.assertTrue(all(r["signature"].startswith("t=") for r in rows))

if __name__ == "__main__":
    unittest.main()
