import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import checks as C
from server.engine import decide
from helpers import id_image_bytes
import io, tempfile

ICAO_LINE1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
ICAO_LINE2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

class TestMRZ(unittest.TestCase):
    def test_icao_sample_check_digits_valid(self):
        parsed = C.parse_mrz(ICAO_LINE1 + "\n" + ICAO_LINE2)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["valid"], parsed["checks"])
        self.assertEqual(parsed["document_number"], "L898902C3")
        self.assertEqual(parsed["dob_yymmdd"], "740812")
        self.assertEqual(parsed["expiry_yymmdd"], "120415")
        self.assertEqual(parsed["names"]["surname"], "ERIKSSON")

    def test_tampered_check_digit_fails(self):
        bad = ICAO_LINE2[:9] + "0" + ICAO_LINE2[10:]  # corrupt doc-number check digit (was 6)
        if bad == ICAO_LINE2: bad = ICAO_LINE2[:19] + "0" + ICAO_LINE2[20:]
        parsed = C.parse_mrz(ICAO_LINE1 + "\n" + bad)
        self.assertIsNotNone(parsed)
        self.assertFalse(parsed["valid"])

    def test_no_mrz_is_unclear_not_fake_pass(self):
        r = C.check_mrz("THIS IS NOT A PASSPORT AT ALL")
        self.assertEqual(r["status"], "unclear")

    def test_check_digit_math(self):
        # ICAO example: document number L898902C3 -> check digit 6
        self.assertEqual(C.mrz_check_digit("L898902C3"), "6")
        self.assertEqual(C.mrz_check_digit("740812"), "2")
        self.assertEqual(C.mrz_check_digit("120415"), "9")

class TestQuality(unittest.TestCase):
    def test_sharp_image_passes(self):
        r = C.check_capture_quality(data=id_image_bytes())
        self.assertEqual(r["status"], "pass", r)
    def test_blurred_image_does_not_pass(self):
        r = C.check_capture_quality(data=id_image_bytes(blur=True))
        self.assertIn(r["status"], ("fail", "unclear"), r)
        self.assertNotEqual(r["status"], "pass")
    def test_tiny_image_fails(self):
        r = C.check_capture_quality(data=id_image_bytes(size=(200, 120)))
        self.assertEqual(r["status"], "fail")
    def test_garbage_is_fail(self):
        r = C.check_capture_quality(data=b"not an image")
        self.assertEqual(r["status"], "fail")

class TestExpiryAge(unittest.TestCase):
    def test_expired_fails(self):
        r = C.check_expiry_age(doc_expiry="2020-01-01", doc_dob="1990-01-01")
        self.assertEqual(r["status"], "fail"); self.assertIn("document_expired", r["reason_codes"])
    def test_underage_fails(self):
        young = date.today().replace(year=date.today().year - 10).isoformat()
        r = C.check_expiry_age(doc_expiry="2035-01-01", doc_dob=young)
        self.assertEqual(r["status"], "fail"); self.assertIn("underage", r["reason_codes"])
    def test_valid_adult_passes(self):
        r = C.check_expiry_age(doc_expiry="2035-01-01", doc_dob="1990-06-15")
        self.assertEqual(r["status"], "pass")
    def test_missing_dates_unclear(self):
        r = C.check_expiry_age()
        self.assertEqual(r["status"], "unclear")
    def test_no_dob_document_type_passes_without_dob(self):
        # NG NIN slip shape (owner-confirmed 2026-10-26): the type
        # prints NO date of birth, so a missing DOB is not a defect —
        # the age leg is not applicable and must not hold the verdict.
        r = C.check_expiry_age(has_expiry=False, prints_dob=False)
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["reason_codes"], [])
        self.assertFalse(r["findings"]["dob_applicable"])
    def test_no_dob_type_still_fails_underage_when_dob_known(self):
        young = date.today().replace(year=date.today().year - 10).isoformat()
        r = C.check_expiry_age(doc_dob=young, has_expiry=False, prints_dob=False)
        self.assertEqual(r["status"], "fail"); self.assertIn("underage", r["reason_codes"])
    def test_no_dob_type_still_fails_expired(self):
        r = C.check_expiry_age(doc_expiry="2020-01-01", has_expiry=True, prints_dob=False)
        self.assertEqual(r["status"], "fail"); self.assertIn("document_expired", r["reason_codes"])

class TestEngineFailClosed(unittest.TestCase):
    BASE = {"capture_quality": {"status": "pass", "reason_codes": []},
            "ocr": {"status": "pass", "reason_codes": []},
            "expiry_age": {"status": "pass", "reason_codes": []},
            "consistency": {"status": "pass", "reason_codes": []}}
    def test_level1_all_pass_approves(self):
        out, _ = decide(1, dict(self.BASE)); self.assertEqual(out, "approved")
    def test_error_check_never_approves(self):
        c = dict(self.BASE); c["ocr"] = {"status": "error", "reason_codes": ["ocr_unavailable"]}
        out, _ = decide(1, c); self.assertEqual(out, "needs_review")
    def test_unclear_never_approves(self):
        # Doctrine refined 2026-10-28 (owner session 15): an unclear
        # REQUIRED check still never APPROVES — but inconclusive
        # evidence (the platform measured and could not conclude)
        # routes to a human instead of auto-rejecting a genuine
        # applicant; only missing/not-run work and the rescan classes
        # (framing, face_match) still auto-reject.
        c = dict(self.BASE); c["consistency"] = {"status": "unclear", "reason_codes": ["name_partial_match"]}
        out, reasons = decide(1, c)
        self.assertEqual(out, "needs_review")
        self.assertIn("consistency_inconclusive", reasons)
    def test_face_match_unclear_rejects_for_rescan(self):
        # The rescan class: a weak/undetected document portrait is the
        # applicant's to fix with a closer capture — rejected with the
        # rescan reasons, not parked for review.
        c = dict(self.BASE)
        c["mrz"] = {"status": "pass", "reason_codes": []}
        for t in ("document_classification", "data_consistency", "authenticity",
                  "face_track", "liveness", "deepfake"):
            c[t] = {"status": "pass", "reason_codes": []}
        c["face_match"] = {"status": "unclear", "reason_codes": ["document_portrait_weak_reference"]}
        out, reasons = decide(2, c)
        self.assertEqual(out, "rejected")
        self.assertIn("face_match_not_pass", reasons)
    def test_not_run_biometric_blocks_level2(self):
        # Same doctrine: biometrics that never ran auto-reject at L2.
        c = dict(self.BASE); c["mrz"] = {"status": "pass", "reason_codes": []}
        c["face_match"] = {"status": "not_run", "reason_codes": ["face_match_not_run"]}
        c["liveness"] = {"status": "not_run", "reason_codes": ["liveness_not_run"]}
        out, _ = decide(2, c); self.assertEqual(out, "rejected")
    def test_elevated_risk_signal_routes_clean_case_to_review(self):
        c = dict(self.BASE)
        c["fraud_signals"] = {"status": "unclear", "reason_codes": ["velocity_high"]}
        out, reasons = decide(1, c)
        self.assertEqual(out, "needs_review"); self.assertIn("velocity_high", reasons)
    def test_benign_risk_signal_does_not_block_approval(self):
        c = dict(self.BASE)
        c["fraud_signals"] = {"status": "pass", "reason_codes": []}
        out, _ = decide(1, c); self.assertEqual(out, "approved")
    def test_hard_fail_rejects_even_with_review_items(self):
        c = dict(self.BASE); c["expiry_age"] = {"status": "fail", "reason_codes": ["document_expired"]}
        out, reasons = decide(1, c); self.assertEqual(out, "rejected"); self.assertIn("document_expired", reasons)

class TestSupportedDocuments(unittest.TestCase):
    def test_owner_expanded_launch_list(self):
        from server.app import SUPPORTED_DOCUMENTS, LAUNCH_COUNTRIES
        expected = {"NG","GB","US","CA","AU","DE","GH","KE","ZA","IN","PH","SG","AE","FR","NL","IE"}
        self.assertEqual(set(LAUNCH_COUNTRIES), expected)
        self.assertEqual(set(SUPPORTED_DOCUMENTS), expected)
        for c in expected:  # passport for ALL launch countries
            self.assertIn("passport", SUPPORTED_DOCUMENTS[c], c)
        for c in ("NG","US","GB","CA","AU","DE","GH"):  # licence set
            self.assertIn("drivers_licence", SUPPORTED_DOCUMENTS[c], c)
        for c in ("NG","DE","GH"):  # general national identity cards
            self.assertIn("national_id", SUPPORTED_DOCUMENTS[c], c)
        for c in ("US","GB","CA","AU"):  # no generic national_id class
            self.assertNotIn("national_id", SUPPORTED_DOCUMENTS[c], c)
        self.assertNotIn("UK", SUPPORTED_DOCUMENTS)  # ISO code is GB

class TestOCR(unittest.TestCase):
    def test_ocr_reads_drawn_text_or_errors_honestly(self):
        import shutil
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(id_image_bytes()); path = f.name
        r = C.check_ocr(path)
        if not shutil.which("tesseract"):
            self.assertEqual(r["status"], "error")  # missing tesseract must NEVER pass
        else:
            self.assertEqual(r["status"], "pass", r)
            self.assertIn("ERIKSSON", r["text"].upper())

if __name__ == "__main__":
    unittest.main()
