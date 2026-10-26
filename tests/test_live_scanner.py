"""Live-scanner build (2026-10-26): per-country document registry with
per-document facts, no-expiry logic, document_framing check, two-sided
capture, and capture metadata."""
import io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from helpers import Server, call, multipart, make_tenant, drive_flow, id_image_bytes, selfie_bytes, structured_photo
from server import checks as C
from server import framing as F
from server import docregistry as R

def _blank_bytes(size=(1240, 800)):
    im = Image.new("RGB", size, "white")
    out = io.BytesIO(); im.save(out, format="PNG"); return out.getvalue()

def _photo_bytes():
    out = io.BytesIO(); structured_photo().save(out, format="PNG"); return out.getvalue()

def _session(srv, key, country="NG", level=1):
    st, app = call(srv, "POST", "/v1/applicants",
                   {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": country}, key=key)
    assert st == 201, app
    st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": level}, key=key)
    assert st == 201, sess
    call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
    return app, sess

def _upload_doc(srv, sess, kind, country, fields=None, meta=None):
    f = {"kind": kind, "issuing_country": country, "doc_first_name": "Anna", "doc_last_name": "Eriksson",
         "doc_dob": "1974-08-12", "doc_number": "X123456"}
    if fields: f.update(fields)
    if meta: f["capture_meta"] = meta
    return multipart(srv, "/v1/flow/document", f,
                     {"front": ("front.png", id_image_bytes(), "image/png")}, sess["flow_token"])

class TestRegistry(unittest.TestCase):
    def test_owner_facts_encoded(self):
        ng = R.DOCUMENT_REGISTRY["NG"]
        self.assertEqual(ng["passport"], {"label": "Passport", "sides": 1, "has_expiry": True, "mrz": True, "aspect": 1.42,
                                          "physical": "card", "guide_aspect": 1.42})
        self.assertEqual(ng["voter_card"]["sides"], 2); self.assertFalse(ng["voter_card"]["has_expiry"])
        self.assertFalse(ng["nin_card"]["has_expiry"]); self.assertEqual(ng["nin_card"]["sides"], 2)
        self.assertFalse(ng["nin_slip"]["has_expiry"]); self.assertEqual(ng["nin_slip"]["sides"], 1)
        us = R.DOCUMENT_REGISTRY["US"]
        self.assertEqual(us["passport_card"]["sides"], 2); self.assertTrue(us["passport_card"]["mrz"])
        self.assertIn("state_id", us); self.assertIn("drivers_license", us)

    def test_voter_card_valid_ng_invalid_us(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            _, sess = _session(srv, key, country="NG")
            st, r = _upload_doc(srv, sess, "voter_card", "NG")
            self.assertEqual(st, 201, r)
            _, sess2 = _session(srv, key, country="US")
            st, r = _upload_doc(srv, sess2, "voter_card", "US")
            self.assertEqual(st, 422, r)

    def test_state_id_and_nin_slip_country_scoping(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            _, sess = _session(srv, key, country="US")
            st, r = _upload_doc(srv, sess, "state_id", "US")
            self.assertEqual(st, 201, r)
            _, sess2 = _session(srv, key, country="NG")
            st, r = _upload_doc(srv, sess2, "state_id", "NG")
            self.assertEqual(st, 422, r)
            st, r = _upload_doc(srv, sess2, "nin_slip", "NG")
            self.assertEqual(st, 201, r)

class TestNoExpiry(unittest.TestCase):
    def test_unit_no_expiry_passes_without_expiry_date(self):
        r = C.check_expiry_age(doc_dob="1990-01-01", has_expiry=False)
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual(r["findings"]["detail"], "document type has no expiry date")
        r = C.check_expiry_age(doc_expiry="2010-01-01", doc_dob="1990-01-01", has_expiry=False)
        self.assertEqual(r["status"], "pass", r)  # even a stale printed date is not an expiry
    def test_unit_expired_passport_still_fails(self):
        r = C.check_expiry_age(doc_expiry="2010-01-01", doc_dob="1990-01-01", has_expiry=True)
        self.assertEqual(r["status"], "fail"); self.assertIn("document_expired", r["reason_codes"])

    def test_nin_slip_session_never_fails_on_expiry(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1, kind="nin_slip", country="NG",
                             doc_fields={"doc_expiry": ""})
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(st, 200, view)
            st, ch = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}/checks", key=key)
            exp = [c for c in ch["checks"] if c["type"] == "expiry_age"]
            self.assertEqual(len(exp), 1, ch)
            self.assertEqual(exp[0]["status"], "pass", exp)
            self.assertEqual(exp[0]["findings"]["detail"], "document type has no expiry date")
            self.assertNotIn("document_expired", view["decision"]["reason_codes"])

class TestFraming(unittest.TestCase):
    def test_card_image_passes(self):
        r = F.check_document_framing(data=id_image_bytes())
        self.assertEqual(r["status"], "pass", r)
        self.assertTrue(r["findings"]["quad_found"])
    def test_blank_and_random_photo_fail(self):
        self.assertEqual(F.check_document_framing(data=_blank_bytes())["status"], "fail")
        self.assertEqual(F.check_document_framing(data=_photo_bytes())["status"], "fail")
        self.assertEqual(F.check_document_framing(data=selfie_bytes())["status"], "fail")
    def test_combine_worst_side_wins(self):
        good = F.check_document_framing(data=id_image_bytes())
        bad = F.check_document_framing(data=_blank_bytes())
        self.assertEqual(F.combine_framing(good, bad)["status"], "fail")
        self.assertEqual(F.combine_framing(good, good)["status"], "pass")
        self.assertIn("back", F.combine_framing(good, bad)["findings"])

class TestTwoSidedCapture(unittest.TestCase):
    def test_two_sided_session_completes_with_back_scan(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            # Tenant config explicitly requires review (ceiling -1) —
            # one of the sanctioned review paths — so the case view of a
            # two-sided document can be exercised; a clean session like
            # this one otherwise auto-approves with no case at all.
            st, r = call(srv, "PUT", "/v1/config", {"level": 1, "config": {"risk_auto_approve_ceiling": -1}}, key=key)
            self.assertEqual(st, 200, r)
            app, sess = _session(srv, key, country="NG", level=1)
            st, r = _upload_doc(srv, sess, "drivers_licence", "NG",
                                meta='{"front":{"method":"live_camera","side":"front"}}')
            self.assertEqual(st, 201, r); self.assertEqual(r["sides"], 2)
            doc_id = r["document_id"]
            st, info = call(srv, "GET", "/v1/flow/session", token=sess["flow_token"])
            d = info["documents"][-1]
            self.assertTrue(d["has_front"]); self.assertFalse(d["has_back"])
            self.assertEqual(d["capture_meta"]["front"]["method"], "live_camera")
            # Back scan attaches to the same document.
            st, r = multipart(srv, "/v1/flow/document/back",
                              {"document_id": doc_id, "capture_meta": '{"back":{"method":"live_camera","side":"back"}}'},
                              {"back": ("back.png", id_image_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 201, r)
            st, info = call(srv, "GET", "/v1/flow/session", token=sess["flow_token"])
            d = info["documents"][-1]
            self.assertTrue(d["has_back"]); self.assertEqual(d["capture_meta"]["back"]["method"], "live_camera")
            st, r = multipart(srv, "/v1/flow/selfie", {"capture_meta": '{"method":"live_camera"}'},
                              {"selfie": ("s.png", selfie_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 201, r)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=sess["flow_token"])
            self.assertEqual(st, 200, view)
            self.assertEqual(view["checks_summary"].get("document_framing"), "pass", view["checks_summary"])
            # Console/case view exposes BOTH sides + framing findings.
            st, case = call(srv, "GET", f"/v1/cases/{view['case_id']}", key=key)
            doc = case["documents"][0]
            self.assertIn("back_image_url", doc)
            self.assertEqual(doc["capture_meta"]["front"]["method"], "live_camera")
            framing = [c for c in case["checks"] if c["type"] == "document_framing"]
            self.assertEqual(len(framing), 1)
            self.assertIn("front", framing[0]["findings"]); self.assertIn("back", framing[0]["findings"])
            import urllib.request
            req = urllib.request.Request(srv.base + doc["back_image_url"],
                                         headers={"Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.assertEqual(resp.status, 200)
                self.assertGreater(len(resp.read()), 1000)  # real image bytes served

    def test_back_rejected_for_one_sided_document(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess = _session(srv, key, country="NG", level=1)
            st, r = _upload_doc(srv, sess, "passport", "NG")
            self.assertEqual(st, 201, r); self.assertEqual(r["sides"], 1)
            st, r = multipart(srv, "/v1/flow/document/back", {"document_id": r["document_id"]},
                              {"back": ("back.png", id_image_bytes(), "image/png")}, sess["flow_token"])
            self.assertEqual(st, 422, r)

if __name__ == "__main__":
    unittest.main()
