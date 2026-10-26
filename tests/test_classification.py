"""Document classification (Addition 9): the captured image must
classify AS the claimed document type by layout — template aspect,
portrait position, printed labels, number zone, MRZ zone — not merely
be a rectangle. Templated types must PASS for auto-approval; a
mismatch auto-rejects. Coarse types: failure = no auto-approval.

Calibration on this suite's fixtures (measured 2026-10-26): the drawn
passport scores ~88 as an NG passport and ~58 claimed as a US driver's
licence (threshold 70); a room photo scores ~35 as a passport.
"""
import os, shutil, unittest
from unittest import mock

import numpy as np

from server import templates as T
from server import checks as C
from server import vision as V
from server import face as FACE
from tests.helpers import Server, call, make_tenant, drive_flow, id_image_bytes, jpeg_roundtrip, structured_photo
import io

def _submit(srv, ctx):
    st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
    assert st == 200, view
    return view

TESS = shutil.which("tesseract") is not None

class ClassificationUnits(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.idp = os.path.join(self.dir, "id.png")
        open(self.idp, "wb").write(id_image_bytes())
        buf = io.BytesIO(); jpeg_roundtrip(structured_photo(), 90).save(buf, "JPEG")
        self.roomp = os.path.join(self.dir, "room.jpg")
        open(self.roomp, "wb").write(buf.getvalue())

    def test_non_document_classifies_as_nothing(self):
        r = T.check_classification(self.roomp, "NG", "passport")
        self.assertEqual(r["status"], "fail")
        self.assertLess(r["findings"]["score"], T.PASS_SCORE)

    @unittest.skipUnless(TESS, "needs tesseract for the OCR-fed elements")
    def test_synthetic_passport_classifies_as_passport(self):
        text = V.read_document_text(self.idp)["text"]
        parsed = C.parse_mrz(text)
        r = T.check_classification(self.idp, "NG", "passport", ocr_text=text,
                                   mrz_parsed=parsed if parsed and parsed.get("valid") else None)
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertGreaterEqual(r["findings"]["score"], T.PASS_SCORE)

    @unittest.skipUnless(TESS, "needs tesseract for the OCR-fed elements")
    def test_same_image_as_drivers_licence_mismatches(self):
        text = V.read_document_text(self.idp)["text"]
        parsed = C.parse_mrz(text)
        r = T.check_classification(self.idp, "US", "drivers_license", ocr_text=text,
                                   mrz_parsed=parsed if parsed and parsed.get("valid") else None)
        self.assertEqual(r["status"], "fail")
        self.assertIn("document_classification_mismatch", r["reason_codes"])
        self.assertLess(r["findings"]["score"], T.PASS_SCORE)

    def test_portrait_on_wrong_side_scores_down(self):
        # A face detected OUTSIDE the template's portrait zone is the
        # strong classification tell (fraction 0.16 vs 1.0 inside).
        fake = np.zeros(25, dtype=np.float32)
        fake[0], fake[1], fake[2], fake[3] = 800.0, 200.0, 180.0, 180.0  # right side
        with mock.patch.object(FACE, "largest_face", return_value=fake):
            r = T.check_classification(self.idp, "NG", "passport")
        el = r["findings"]["elements"]["portrait"]
        self.assertTrue(el["found"])
        self.assertFalse(el["position_match"])

    def test_portrait_inside_zone_scores_full(self):
        fake = np.zeros(25, dtype=np.float32)
        fake[0], fake[1], fake[2], fake[3] = 80.0, 150.0, 180.0, 220.0  # left zone
        with mock.patch.object(FACE, "largest_face", return_value=fake):
            r = T.check_classification(self.idp, "NG", "passport")
        self.assertTrue(r["findings"]["elements"]["portrait"]["position_match"])

    def test_missing_template_is_honest(self):
        # An unknown passport still gets the generic TD3 template by
        # design; an unknown KIND has no template and must say so.
        r = T.check_classification(self.idp, "XX", "drivers_licence")
        self.assertEqual(r["status"], "unclear")
        self.assertIn("classification_template_missing", r["reason_codes"])

    def test_templates_cover_priority_set(self):
        for country, kind in [("NG", "passport"), ("NG", "drivers_licence"), ("NG", "voter_card"),
                              ("NG", "nin_card"), ("NG", "nin_slip"), ("US", "passport"),
                              ("US", "passport_card"), ("US", "drivers_license"), ("US", "state_id")]:
            tpl, level = T.get_template(country, kind)
            self.assertIsNotNone(tpl, (country, kind))
            self.assertEqual(level, "full", (country, kind))
            self.assertIn("pattern_expected", tpl)
        tpl, level = T.get_template("DE", "passport")
        self.assertEqual(level, "generic")  # generic TD3 for other passports
        # Phase 4 WS1: GB/CA/AU/DE/GH licences and DE/GH national IDs
        # (plus all newly merged registry types) carry FULL templates;
        # the coarse fallback remains only for untemplated kinds.
        for country, kind in [("GB", "drivers_licence"), ("CA", "drivers_licence"),
                              ("AU", "drivers_licence"), ("DE", "drivers_licence"),
                              ("GH", "drivers_licence"), ("DE", "national_id"),
                              ("GH", "national_id"), ("IN", "aadhaar"), ("PH", "philid"),
                              ("SG", "nric"), ("KE", "national_id"), ("ZA", "smart_id"),
                              ("AE", "emirates_id"), ("FR", "national_id"),
                              ("NL", "national_id"), ("IE", "passport_card")]:
            tpl, level = T.get_template(country, kind)
            self.assertIsNotNone(tpl, (country, kind))
            self.assertEqual(level, "full", (country, kind))

@unittest.skipUnless(TESS, "session flows need tesseract")
class ClassificationSessions(unittest.TestCase):
    def test_clean_l1_records_classification_pass(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1)
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["checks_summary"].get("document_classification"), "pass")

    def test_passport_image_claimed_as_licence_auto_rejects(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1, kind="drivers_licence")
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "rejected", view)
            self.assertEqual(view["checks_summary"].get("document_classification"), "fail")
            self.assertIn("document_classification_mismatch", view["decision"]["reason_codes"])

    def test_full_template_mismatch_auto_rejects(self):
        # GB drivers_licence is a FULL template since Phase 4 WS1: a
        # passport image claimed as one fails classification outright
        # (before WS1 it was coarse: unclear, blocking auto-approval).
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1, kind="drivers_licence", country="GB")
            view = _submit(srv, ctx)
            self.assertEqual(view["checks_summary"].get("document_classification"), "fail", view)
            self.assertEqual(view["status"], "rejected", view)

if __name__ == "__main__":
    unittest.main()
