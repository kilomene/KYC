"""NIN-slip upload + typed-number tally (owner's order 2026-10-26,
STRICTLY scoped): the laminated NIN slip defeats live scanning, so
for nin_slip ONLY the user uploads a photo of the slip and types
their NIN; the number read off the slip must tally with the typed
number, and the slip's printed portrait is face-matched against the
live selfie by the ordinary pipeline. Every other document type
keeps the live-scanner-only rule — a typed number sent for any
other kind is refused, and no upload path exists for them in the
flow.

Fixture values are INVENTED (the synthetic slip prints NIN
12345678901). No owner data in this file.
"""
import io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Server, call, multipart, make_tenant, selfie_bytes, id_image_bytes
from server import engine as E
from test_paper_detection import _synthetic_slip_bytes
from test_identity_from_document import _slip_on_table_bytes, _document_session, _checks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLIP_NIN = "12345678901"          # printed on the synthetic fixture
WRONG_NIN = "10987654321"         # 11 digits, not the fixture's


def _upload(srv, token, data, kind, country="NG", claimed=None, method="file_upload"):
    fields = {"kind": kind, "issuing_country": country,
              "capture_meta": '{"front": {"method": "%s", "side": "front"}}' % method}
    if claimed is not None:
        fields["claimed_number"] = claimed
    return multipart(srv, "/v1/flow/document", fields,
                     {"front": ("front.png", data, "image/png")}, token)


class TestClaimScoping(unittest.TestCase):
    def test_claim_refused_for_other_kinds(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, id_image_bytes(), "passport", claimed=SLIP_NIN)
            self.assertEqual(st, 422, r)

    def test_claim_must_be_11_digits(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, _synthetic_slip_bytes(), "nin_slip", claimed="12345")
            self.assertEqual(st, 422, r)

    def test_claim_endpoint_refuses_other_kinds(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, id_image_bytes(), "passport")
            self.assertEqual(st, 201, r)
            st, r = call(srv, "POST", "/v1/flow/document/claim",
                         {"document_id": r["document_id"], "claimed_number": SLIP_NIN}, token=token)
            self.assertEqual(st, 422, r)


class TestTallyReadBack(unittest.TestCase):
    def test_process_reports_match(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, _slip_on_table_bytes(), "nin_slip", claimed=SLIP_NIN)
            self.assertEqual(st, 201, r)
            st, p = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": r["document_id"]}, token=token)
            self.assertEqual(st, 200, p)
            self.assertIsNotNone(p["number_tally"], p)
            self.assertEqual(p["number_tally"]["status"], "pass", p)
            self.assertTrue(p["number_tally"]["match"], p)

    def test_process_reports_mismatch_then_claim_corrects(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, _slip_on_table_bytes(), "nin_slip", claimed=WRONG_NIN)
            self.assertEqual(st, 201, r)
            did = r["document_id"]
            st, p = call(srv, "POST", "/v1/flow/document/process", {"document_id": did}, token=token)
            self.assertEqual(p["number_tally"]["status"], "fail", p)
            self.assertFalse(p["number_tally"]["match"], p)
            st, c = call(srv, "POST", "/v1/flow/document/claim",
                         {"document_id": did, "claimed_number": SLIP_NIN}, token=token)
            self.assertEqual(st, 200, c)
            self.assertTrue(c["match"], c)
            st, p = call(srv, "POST", "/v1/flow/document/process", {"document_id": did}, token=token)
            self.assertEqual(p["number_tally"]["status"], "pass", p)


class TestTallyAtDecision(unittest.TestCase):
    def _run_to_submit(self, srv, key, token, claimed):
        st, r = _upload(srv, token, _slip_on_table_bytes(), "nin_slip", claimed=claimed)
        assert st == 201, r
        st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
        assert st == 201, r
        return call(srv, "POST", "/v1/flow/submit", {}, token=token)

    def test_match_records_tally_pass(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, view = self._run_to_submit(srv, key, token, SLIP_NIN)
            self.assertEqual(st, 200, view)
            checks = _checks(srv, key, sess["id"])
            self.assertIn("number_tally", checks)
            self.assertEqual(checks["number_tally"]["status"], "pass", checks["number_tally"])

    def test_mismatch_rejects_with_tally_reason(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, view = self._run_to_submit(srv, key, token, WRONG_NIN)
            self.assertEqual(st, 200, view)
            self.assertEqual(view["status"], "rejected", view)
            checks = _checks(srv, key, sess["id"])
            self.assertEqual(checks["number_tally"]["status"], "fail", checks.get("number_tally"))
            st, sv = call(srv, "GET", f"/v1/sessions/{sess['id']}", key=key)
            reasons = (sv.get("decision") or {}).get("reason_codes") or []
            self.assertIn("nin_number_mismatch", reasons, sv.get("decision"))


class TestEngineHardFail(unittest.TestCase):
    def test_mismatch_is_decisive(self):
        outcome, reasons = E.decide(1, {"number_tally": {"status": "fail",
                                                         "reason_codes": ["nin_number_mismatch"]}})
        self.assertEqual(outcome, "rejected")
        self.assertIn("nin_number_mismatch", reasons)

    def test_not_provided_is_decisive(self):
        outcome, reasons = E.decide(1, {"number_tally": {"status": "fail",
                                                         "reason_codes": ["nin_number_not_provided"]}})
        self.assertEqual(outcome, "rejected")
        self.assertIn("nin_number_not_provided", reasons)


class TestFlowScoping(unittest.TestCase):
    def test_upload_ui_exists_only_for_nin(self):
        html = open(os.path.join(ROOT, "public", "flow.html")).read()
        self.assertIn('id="nin-panel"', html)
        self.assertIn('id="nin-file"', html)
        self.assertIn('id="nin-number"', html)
        self.assertIn("isNinSlip()", html)
        self.assertIn("file_upload", html)
        self.assertIn("/v1/flow/document/claim", html)
        # the panel starts hidden; the scanner remains the default path
        self.assertIn('id="nin-panel" style="display:none"', html)
        # camera-roll photos exceed the tunnel's body limit (the
        # owner's first real upload got HTTP 413): the upload path
        # downscales to the scanner's own maxDim before sending.
        self.assertIn("downscaleForUpload", html)
        self.assertIn("2048", html)


if __name__ == "__main__":
    unittest.main()
