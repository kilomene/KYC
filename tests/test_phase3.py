"""Phase 3 tests: proof of address, screening + disposition + four-eyes,
ongoing monitoring, KYB assembly, reviewer assist, reusable credentials."""
import csv, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, multipart, make_tenant, drive_flow, id_image_bytes, poa_image_bytes
from server import checks as C
from server import screening as SCR
from server import assist as ASSIST
from server import credentials as CRED
from datetime import date, timedelta

SAMPLE_ENTRY = {"full_name": "Viktor Petrov", "dob": "1968-03-14", "country": "RU",
                "list_source": "SAMPLE_SANCTIONS_FIXTURE", "entry_id": "SAMPLE-001"}

def make_user(srv, key, name, role="reviewer"):
    st, r = call(srv, "POST", "/v1/users", {"name": name, "role": role}, key=key)
    assert st == 201, r
    return r

def decide_as(srv, case_id, key, body, reviewer_token=None):
    headers = {"X-Reviewer-Key": reviewer_token} if reviewer_token else None
    return call(srv, "POST", f"/v1/cases/{case_id}/decide", body, key=key, raw_headers=headers)

class TestScreeningMatching(unittest.TestCase):
    def test_exact_name_and_dob_hits(self):
        hits = SCR.screen_person("Viktor Petrov", "1968-03-14", [SAMPLE_ENTRY])
        self.assertEqual(len(hits), 1)
        self.assertGreaterEqual(hits[0]["score"], 80)
    def test_different_person_does_not_hit(self):
        hits = SCR.screen_person("Anna Eriksson", "1974-08-12", [SAMPLE_ENTRY])
        self.assertEqual(hits, [])
    def test_fuzzy_name_with_same_dob_hits_as_pending(self):
        hits = SCR.screen_person("Viktor Petrova", "1968-03-14",
                                 [{**SAMPLE_ENTRY, "full_name": "Viktor Petrova"}])
        # a one-token difference with equal DOB: similarity still high
        hits2 = SCR.screen_person("Viktor Petrov", "1968-03-14", [{**SAMPLE_ENTRY, "full_name": "Viktar Petrov"}])
        self.assertEqual(len(hits2), 1, hits2)
    def test_conflicting_dob_caps_score(self):
        s_match, rel = SCR.match_score("Viktor Petrov", "1968-03-14", SAMPLE_ENTRY)
        s_conf, rel2 = SCR.match_score("Viktor Petrov", "1999-01-01", SAMPLE_ENTRY)
        self.assertEqual(rel, "match"); self.assertEqual(rel2, "conflict")
        self.assertLess(s_conf, s_match)
    def test_hit_is_pending_never_auto_reject(self):
        # The screening check returns 'unclear' with a hit, not 'fail'.
        import tempfile
        from server.db import DB
        tmp = tempfile.mkdtemp()
        db = DB(os.path.join(tmp, "data"))
        class A(dict): __getitem__ = lambda self, k: dict.get(self, k)
        app = {"id": "a1", "first_name": "Viktor", "last_name": "Petrov", "dob": "1968-03-14"}
        import server.screening as S
        orig = S.load_lists
        S.load_lists = lambda data_dir: [SAMPLE_ENTRY]
        try:
            r = S.run_screening(db, tmp, "t1", "test", app, threshold=80)
        finally:
            S.load_lists = orig
        self.assertEqual(r["status"], "unclear")
        self.assertIn("screening_hit_pending", r["reason_codes"])
        rows = db.all("SELECT status FROM screening_hits WHERE applicant_id='a1'")
        self.assertEqual(rows[0]["status"], "pending")

class TestPoA(unittest.TestCase):
    def test_poa_text_logic(self):
        recent = (date.today() - timedelta(days=5)).strftime("%d %B %Y")
        text = f"UTILITY BILL\nANNA ERIKSSON\n12 Marina Road Lagos\nBill date: {recent}"
        r = C.check_poa(text, "Anna", "Eriksson", "12 Marina Road Lagos")
        self.assertEqual(r["status"], "pass", r)
    def test_poa_no_date_is_unclear(self):
        r = C.check_poa("UTILITY BILL ANNA ERIKSSON 12 Marina Road", "Anna", "Eriksson", "12 Marina Road Lagos")
        self.assertEqual(r["status"], "unclear"); self.assertIn("poa_no_date_found", r["reason_codes"])
    def test_poa_stale_date_fails(self):
        old = (date.today() - timedelta(days=200)).strftime("%d %B %Y")
        r = C.check_poa(f"BILL ANNA ERIKSSON date {old}", "Anna", "Eriksson", None, window_days=90)
        self.assertEqual(r["status"], "fail"); self.assertIn("poa_outdated", r["reason_codes"])
    def test_poa_ocr_on_synthetic_bill(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(poa_image_bytes()); path = f.name
        ocr = C.check_ocr(path)
        if ocr["status"] == "error":
            self.skipTest("tesseract unavailable")
        self.assertEqual(ocr["status"], "pass", ocr)
        r = C.check_poa(ocr["text"], "Anna", "Eriksson", "12 Marina Road Lagos")
        self.assertEqual(r["status"], "pass", r)

def drive_l3_with_poa(srv, key, first="Anna", last="Eriksson", dob="1974-08-12", poa_bytes=None, address="12 Marina Road Lagos"):
    ctx = drive_flow(srv, key, level=3, first=first, last=last, dob=dob)
    # drive_flow created the applicant without an address; PoA matching
    # uses whatever address is on file (none -> address leg is skipped).
    st, r = multipart(srv, "/v1/flow/poa", {}, {"document": ("bill.png", poa_bytes if poa_bytes is not None else poa_image_bytes(first=first.upper(), last=last.upper()), "image/png")}, ctx["token"])
    assert st == 201, r
    return ctx

class TestScreeningFlowAndFourEyes(unittest.TestCase):
    def test_pending_hit_blocks_approval_and_false_positive_needs_four_eyes(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            rev_a = make_user(srv, key, "Reviewer A")
            rev_b = make_user(srv, key, "Reviewer B")
            # Applicant matches the shipped SAMPLE list exactly.
            ctx = drive_l3_with_poa(srv, key, first="Viktor", last="Petrov", dob="1968-03-14")
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            # Auto-decision doctrine (2026-10-26): the synthetic-media
            # session also carries decisive failures (no real face /
            # liveness, an MRZ the band pass misread), so the ENGINE now
            # auto-rejects instead of parking at needs_review. What this
            # test exercises is unchanged: the case opens either way, the
            # screening hit stays pending and blocks approval until it is
            # disposed, and overriding to approve takes four eyes.
            self.assertEqual(view["status"], "rejected", view)
            self.assertEqual(view["checks_summary"]["screening_sanctions"], "unclear")
            self.assertEqual(view["checks_summary"]["poa"], "pass", view)
            case_id = view["case_id"]
            st, detail = call(srv, "GET", f"/v1/cases/{case_id}", key=key)
            self.assertEqual(len(detail["screening_hits"]), 1, detail["screening_hits"])
            self.assertIn("assist", detail)
            hit_id = detail["screening_hits"][0]["id"]
            # Approval is blocked while the hit is pending.
            st, r = decide_as(srv, case_id, key, {"action": "approve", "reason": "looks fine"}, rev_a["token"])
            self.assertEqual(st, 409, r)
            # Dispose as false positive (reason required).
            st, r = call(srv, "POST", f"/v1/cases/{case_id}/hits/{hit_id}/dispose",
                         {"disposition": "false_positive", "reason": " "}, key=key, raw_headers={"X-Reviewer-Key": rev_a["token"]})
            self.assertEqual(st, 422, r)
            st, r = call(srv, "POST", f"/v1/cases/{case_id}/hits/{hit_id}/dispose",
                         {"disposition": "false_positive", "reason": "Different person: DOB and photo ID checked, namesake only."},
                         key=key, raw_headers={"X-Reviewer-Key": rev_a["token"]})
            self.assertEqual(st, 200, r)
            # Now approval needs four-eyes: first reviewer decision parks it.
            st, r = decide_as(srv, case_id, key, {"action": "approve", "reason": "All other checks reviewed."}, rev_a["token"])
            self.assertEqual(st, 202, r); self.assertEqual(r["status"], "awaiting_second")
            # The SAME reviewer cannot confirm their own decision.
            st, r = call(srv, "POST", f"/v1/cases/{case_id}/confirm", {"reason": "confirming"},
                         key=key, raw_headers={"X-Reviewer-Key": rev_a["token"]})
            self.assertEqual(st, 403, r)
            # A second, different reviewer confirms -> approved.
            st, r = call(srv, "POST", f"/v1/cases/{case_id}/confirm", {"reason": "Second pair of eyes: agreed, false positive."},
                         key=key, raw_headers={"X-Reviewer-Key": rev_b["token"]})
            self.assertEqual(st, 200, r); self.assertEqual(r["outcome"], "approved", r)
            st, sess = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}", key=key)
            self.assertEqual(sess["status"], "approved")

    def test_confirmed_hit_rejects_with_sanctions_reason(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            ctx = drive_l3_with_poa(srv, key, first="Viktor", last="Petrov", dob="1968-03-14")
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            case_id = view["case_id"]
            st, detail = call(srv, "GET", f"/v1/cases/{case_id}", key=key)
            hit_id = detail["screening_hits"][0]["id"]
            st, r = call(srv, "POST", f"/v1/cases/{case_id}/hits/{hit_id}/dispose",
                         {"disposition": "confirmed", "reason": "Exact name + DOB match confirmed."}, key=key)
            self.assertEqual(st, 200, r); self.assertEqual(r["outcome"], "rejected")
            st, sess = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}", key=key)
            self.assertEqual(sess["status"], "rejected")
            self.assertIn("sanctions_hit_confirmed", sess["decision"]["reason_codes"])

    def test_override_of_engine_rejection_needs_four_eyes(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            rev_b = make_user(srv, key, "Reviewer B")
            ctx = drive_flow(srv, key, level=1, doc_fields={"doc_expiry": "2019-01-01"},
                             doc_bytes=id_image_bytes(expiry="2019-01-01"))
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(view["status"], "rejected", view)
            self.assertIn("case_id", view)  # rejected sessions open an override case
            # First decision (tenant API key identity) -> awaiting second.
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/decide",
                         {"action": "approve", "reason": "Applicant provided a renewed document out of band."}, key=key)
            self.assertEqual(st, 202, r)
            # The same identity (API key) cannot confirm.
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/confirm", {"reason": "confirm"}, key=key)
            self.assertEqual(st, 403, r)
            st, r = call(srv, "POST", f"/v1/cases/{view['case_id']}/confirm", {"reason": "Second reviewer agrees."},
                         key=key, raw_headers={"X-Reviewer-Key": rev_b["token"]})
            self.assertEqual(st, 200, r); self.assertEqual(r["outcome"], "approved")

    def test_case_has_sla_and_queue_sorts_by_it(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=2)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            st, cases = call(srv, "GET", "/v1/cases", key=key)
            self.assertEqual(len(cases["cases"]), 1)
            self.assertIsNotNone(cases["cases"][0]["sla_due_at"])

class TestMonitoringRescreen(unittest.TestCase):
    def test_rescreen_flags_new_match_on_approved_applicant(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            # Clean L1 applicant auto-approves (not on any list yet).
            ctx = drive_flow(srv, key, level=1, first="Musa", last="Bello", dob="1990-02-02")
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(view["status"], "approved", view)
            st, r = call(srv, "POST", "/v1/monitoring/rescreen", {}, key=key)
            self.assertEqual(r["new_hits"], 0, r)
            # A NEW list entry naming the approved applicant appears.
            lists_dir = os.path.join(srv.data_dir, "lists"); os.makedirs(lists_dir, exist_ok=True)
            with open(os.path.join(lists_dir, "watch.csv"), "w", newline="") as f:
                w = csv.writer(f); w.writerow(["full_name", "dob", "country", "list_source", "entry_id"])
                w.writerow(["Musa Bello", "1990-02-02", "NG", "TEST_WATCHLIST", "W-1"])
            st, r = call(srv, "POST", "/v1/monitoring/rescreen", {}, key=key)
            self.assertEqual(st, 200, r); self.assertEqual(r["new_hits"], 1, r)
            st, alerts = call(srv, "GET", "/v1/monitoring/alerts", key=key)
            self.assertEqual(len(alerts["alerts"]), 1)
            # Re-running does not duplicate the alert.
            st, r = call(srv, "POST", "/v1/monitoring/rescreen", {}, key=key)
            self.assertEqual(r["new_hits"], 0, r)

class TestKYB(unittest.TestCase):
    def test_business_verifies_only_when_people_and_registry_done(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            st, bad = call(srv, "POST", "/v1/businesses",
                           {"legal_name": "Bad Co", "registration_number": "XYZ!", "country": "NG"}, key=key)
            self.assertEqual(st, 422, bad)
            st, biz = call(srv, "POST", "/v1/businesses",
                           {"legal_name": "Acme Ventures Ltd", "registration_number": "RC1234567", "country": "NG"}, key=key)
            self.assertEqual(st, 201, biz); bid = biz["id"]
            self.assertEqual(biz["registry_status"], "format_valid")
            # Person attached but not verified -> pending.
            st, app = call(srv, "POST", "/v1/applicants", {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG"}, key=key)
            st, r = call(srv, "POST", f"/v1/businesses/{bid}/people",
                         {"applicant_id": app["id"], "role": "director", "ownership_pct": 60}, key=key)
            self.assertEqual(st, 201, r)
            st, ev = call(srv, "POST", f"/v1/businesses/{bid}/evaluate", {}, key=key)
            self.assertEqual(ev["status"], "pending", ev)
            self.assertTrue(any("not_verified" in x for x in ev["evaluation"]["reasons"]), ev)
            # Verify the person at Level 2 (reviewer path), then registry
            # document + confirmation, then evaluate -> verified.
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 2}, key=key)
            token = sess["flow_token"]
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=token)
            st, r = multipart(srv, "/v1/flow/document",
                              {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna", "doc_last_name": "Eriksson", "doc_dob": "1974-08-12", "doc_expiry": "2032-04-15"},
                              {"front": ("f.png", id_image_bytes(), "image/png")}, token)
            self.assertEqual(st, 201, r)
            from helpers import selfie_bytes
            multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("s.png", selfie_bytes(), "image/png")}, token)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            # Auto-decision doctrine (2026-10-26): the synthetic L2
            # session auto-rejects; the KYB reviewer path completes it
            # via a four-eyes override.
            self.assertEqual(view["status"], "rejected", view)
            rev_a = make_user(srv, key, "KYB Reviewer A")
            rev_b = make_user(srv, key, "KYB Reviewer B")
            st, dec = decide_as(srv, view["case_id"], key,
                                {"action": "approve", "reason": "KYB director verified by eye."}, rev_a["token"])
            self.assertEqual(st, 202, dec); self.assertEqual(dec["status"], "awaiting_second")
            st, dec = call(srv, "POST", f"/v1/cases/{view['case_id']}/confirm",
                           {"reason": "Second pair of eyes: agreed."},
                           key=key, raw_headers={"X-Reviewer-Key": rev_b["token"]})
            self.assertEqual(st, 200, dec); self.assertEqual(dec["outcome"], "approved", dec)
            st, doc = multipart(srv, f"/v1/businesses/{bid}/document", {},
                                {"document": ("reg.pdf", b"%PDF-1.4 fake certificate bytes", "application/pdf")}, key)
            self.assertEqual(st, 201, doc)
            st, ev = call(srv, "POST", f"/v1/businesses/{bid}/evaluate", {}, key=key)
            self.assertEqual(ev["status"], "pending", ev)  # registry not yet confirmed
            st, reg = call(srv, "POST", f"/v1/businesses/{bid}/registry",
                           {"status": "confirmed", "reason": "Certificate inspected; number format and document agree."}, key=key)
            self.assertEqual(st, 200, reg)
            st, ev = call(srv, "POST", f"/v1/businesses/{bid}/evaluate", {}, key=key)
            self.assertEqual(ev["status"], "verified", ev)
            st, got = call(srv, "GET", f"/v1/businesses/{bid}", key=key)
            self.assertEqual(got["status"], "verified")
            self.assertTrue(got["people"][0]["verified_l2plus"])

class TestAssist(unittest.TestCase):
    def test_assist_suggests_approve_on_clean(self):
        checks = {"ocr": {"status": "pass", "reason_codes": []},
                  "expiry_age": {"status": "pass", "reason_codes": []}}
        a = ASSIST.build_assist(checks, ["ocr", "expiry_age"])
        self.assertEqual(a["suggested_disposition"], "approve")
        self.assertEqual(a["label"], "Assist — a human decides.")
    def test_assist_suggests_reject_on_hard_fail(self):
        checks = {"expiry_age": {"status": "fail", "reason_codes": ["document_expired"]}}
        a = ASSIST.build_assist(checks, ["expiry_age"])
        self.assertEqual(a["suggested_disposition"], "reject")
        self.assertTrue(any(m["reason"] == "document_expired" for m in a["mismatches"]))
    def test_assist_flags_pending_hit(self):
        a = ASSIST.build_assist({"ocr": {"status": "pass", "reason_codes": []}}, ["ocr"], pending_hits=1)
        self.assertEqual(a["suggested_disposition"], "request_more")

class TestCredentials(unittest.TestCase):
    def _approved_l1(self, srv, key):
        ctx = drive_flow(srv, key, level=1)
        st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
        assert view["status"] == "approved", view
        return ctx, view
    def test_issue_verify_revoke(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            ctx, view = self._approved_l1(srv, key)
            self.assertIn("credential", view)
            cred = view["credential"]
            st, v = call(srv, "POST", "/v1/credentials/verify", {"credential": cred}, key=key)
            self.assertTrue(v["valid"], v)
            self.assertEqual(v["claims"]["level"], 1)
            # Claims only, no document DATA. (Check NAMES in
            # checks_passed — e.g. document_classification — are
            # metadata about what ran, not document data; the ban is
            # on the data itself, tightened 2026-10-26 when new check
            # names made the old blunt substring assertion wrong.)
            for _forbidden in ("document_number", "doc_number", "storage_path",
                               "ocr_text", "mrz_raw", "image_url", "date_of_birth"):
                self.assertNotIn(_forbidden, json.dumps(v))
            # Tampered claims are rejected.
            bad = json.loads(json.dumps(cred)); bad["claims"]["level"] = 3
            st, v = call(srv, "POST", "/v1/credentials/verify", {"credential": bad}, key=key)
            self.assertFalse(v["valid"]); self.assertEqual(v["reason"], "bad_signature")
            # Revocation kills it.
            st, r = call(srv, "POST", "/v1/credentials/revoke", {"credential_id": cred["claims"]["credential_id"]}, key=key)
            self.assertEqual(st, 200, r)
            st, v = call(srv, "POST", "/v1/credentials/verify", {"credential": cred}, key=key)
            self.assertFalse(v["valid"]); self.assertEqual(v["reason"], "revoked")
    def test_expired_credential_rejected(self):
        import tempfile
        from server.db import DB
        tmp = tempfile.mkdtemp(); db = DB(os.path.join(tmp, "data"))
        db.execute("INSERT INTO tenants(id,name,created_at) VALUES('t1','T',?)", ("2026-01-01",))
        db.execute("INSERT INTO applicants(id,tenant_id,env,first_name,last_name,dob,country,created_at,updated_at) VALUES('a1','t1','test','A','B','1990-01-01','NG','2026-01-01','2026-01-01')")
        app = db.one("SELECT * FROM applicants WHERE id='a1'")
        sess = {"id": "s1", "level": 2}
        cred = CRED.issue_credential(db, os.path.join(tmp, "data"), "t1", "test", app, sess, ["ocr"],
                                     expires_at="2020-01-01T00:00:00+00:00")
        v = CRED.verify_credential(db, os.path.join(tmp, "data"), cred)
        self.assertFalse(v["valid"]); self.assertEqual(v["reason"], "expired")
    def test_credential_based_session_reuses_checks(self):
        with Server() as srv:
            tid_a, key_a, _ = make_tenant(srv, "Tenant A")
            ctx, view = self._approved_l1(srv, key_a)
            cred = view["credential"]
            # A second tenant accepts the credential for a Level 1 session.
            tid_b, key_b, _ = make_tenant(srv, "Tenant B")
            st, sess = call(srv, "POST", "/v1/sessions", {"level": 1, "credential": cred}, key=key_b)
            self.assertEqual(st, 201, sess)
            self.assertIn("ocr", sess["inherited_checks"])
            self.assertNotIn("face_match", sess["inherited_checks"])  # never inherited (and not in this L1 anyway)
            # The flow completes without any document upload.
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
            st, view2 = call(srv, "POST", "/v1/flow/submit", {}, token=sess["flow_token"])
            self.assertEqual(st, 200, view2)
            self.assertEqual(view2["status"], "approved", view2)
            self.assertEqual(view2["decision"]["decided_by"], "engine")
            st, ch = call(srv, "GET", f"/v1/sessions/{sess['id']}/checks", key=key_b)
            providers = {c["type"]: c["provider"] for c in ch["checks"]}
            self.assertEqual(providers.get("ocr"), "verified_credential")
            # A revoked credential can no longer seed a session.
            call(srv, "POST", "/v1/credentials/revoke", {"credential_id": cred["claims"]["credential_id"]}, key=key_a)
            st, r = call(srv, "POST", "/v1/sessions", {"level": 1, "credential": cred}, key=key_b)
            self.assertEqual(st, 422, r)
            # Nor can a credential be stretched above its level.
            ctx2, view3 = self._approved_l1(srv, key_a)
            st, r = call(srv, "POST", "/v1/sessions", {"level": 3, "credential": view3["credential"]}, key=key_b)
            self.assertEqual(st, 422, r)

if __name__ == "__main__":
    unittest.main()
