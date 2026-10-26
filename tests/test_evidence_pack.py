"""Addition 10: (A) the data-consistency matrix — pairwise agreement
across printed / OCR / MRZ / decoded-barcode / applicant sources;
(B) the security-feature signal pack in authenticity; (C) the
document_evidence combination record on the case.

Signal calibration (measured 2026-10-26): compositing ring/interior
ratio — clean card 0.30, pasted-portrait splice 3.23 (strong);
border runs — clean card none, double-drawn border strong on 2 sides;
pattern texture energy — drawn card 6992, room 355, flat synthetic
fill 0.96 (strong missing_pattern). The font-consistency thresholds
(height CV 0.35/0.55, 45% outlier) are set from the fixture's uniform
36-44px print and verified against the big-digit tamper fixture.
"""
import os, shutil, tempfile, unittest

from server import vision as V
from server import authenticity as A
from tests.helpers import (Server, call, make_tenant, drive_flow, id_image_bytes, portrait_splice_bytes,
                           ghost_border_bytes, flat_card_bytes, font_tamper_bytes)

def _submit(srv, ctx):
    st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
    assert st == 200, view
    return view

TESS = shutil.which("tesseract") is not None

DOC = {"doc_first_name": "Adaeze", "doc_last_name": "Okafor", "doc_dob": "2004-12-18",
       "doc_number": "L898902C3", "doc_expiry": "2034-05-01"}
APP = {"first_name": "Adaeze", "last_name": "Okafor", "dob": "2004-12-18"}
MRZ = {"valid": True, "names": {"surname": "OKAFOR", "given_names": "ADAEZE"},
       "dob_yymmdd": "041218", "expiry_yymmdd": "340501", "document_number": "L898902C3"}

class DataConsistencyMatrix(unittest.TestCase):
    def test_all_sources_agree_passes(self):
        r = V.build_data_consistency(doc_fields=DOC, applicant=APP, mrz_parsed=MRZ,
                                     ocr_text="ADAEZE OKAFOR DOB 2004-12-18 EXPIRY 2034-05-01 L898902C3")
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertEqual(r["findings"]["disagreements"], [])
        self.assertEqual(r["findings"]["matrix"]["dob"]["printed_vs_mrz"], "agree")
        self.assertEqual(r["findings"]["matrix"]["number"]["applicant_vs_mrz"], "not_available")

    def test_mrz_vs_barcode_number_disagree_is_named(self):
        aamva = {"surname": "OKAFOR", "first_name": "ADAEZE", "dob": "12182004",
                 "expiry": "05012034", "number": "X999999X9"}
        r = V.build_data_consistency(doc_fields=DOC, applicant=APP, mrz_parsed=MRZ,
                                     ocr_text="ADAEZE OKAFOR DOB 2004-12-18 EXPIRY 2034-05-01 L898902C3",
                                     aamva=aamva)
        self.assertEqual(r["status"], "fail")
        self.assertIn("mrz_vs_barcode_number_disagree", r["reason_codes"])
        self.assertIn("printed_vs_barcode_number_disagree", r["reason_codes"])
        self.assertIn("data_inconsistency", r["reason_codes"])
        self.assertEqual(r["findings"]["matrix"]["number"]["mrz_vs_barcode"], "disagree")

    def test_applicant_dob_disagree_fails(self):
        bad = dict(APP, dob="2004-12-19")
        r = V.build_data_consistency(doc_fields=DOC, applicant=bad, mrz_parsed=MRZ,
                                     ocr_text="ADAEZE OKAFOR DOB 2004-12-18 EXPIRY 2034-05-01 L898902C3")
        self.assertEqual(r["status"], "fail")
        self.assertIn("printed_vs_applicant_dob_disagree", r["reason_codes"])

    def test_nothing_comparable_is_unclear_never_pass(self):
        r = V.build_data_consistency(doc_fields={}, applicant={}, mrz_parsed=None)
        self.assertEqual(r["status"], "unclear")

class SecurityFeatureSignals(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.paths = {}
        for name, data in [("id", id_image_bytes()), ("splice", portrait_splice_bytes()),
                           ("ghost", ghost_border_bytes()), ("flat", flat_card_bytes()),
                           ("font", font_tamper_bytes())]:
            p = os.path.join(self.dir, name + ".jpg")
            open(p, "wb").write(data)
            self.paths[name] = p

    def test_clean_card_passes_all_four(self):
        p = self.paths["id"]
        self.assertEqual(A.compositing_edges_signal(p)["strength"], "none")
        self.assertEqual(A.border_edges_signal(p)["strength"], "none")
        self.assertEqual(A.pattern_presence_signal(p, "passport", "NG")["strength"], "none")
        if TESS:
            self.assertIn(A.font_consistency_signal(p, "passport", "NG")["strength"], ("none", "not_applicable"))

    def test_pasted_portrait_trips_compositing(self):
        s = A.compositing_edges_signal(self.paths["splice"])
        self.assertEqual(s["strength"], "strong")
        self.assertGreater(s["score"], 2.6)
        r = A.check_authenticity(self.paths["splice"], kind="passport", country="NG")
        self.assertIn("compositing_suspect", r["reason_codes"])

    def test_ghost_border_trips_border_edges(self):
        s = A.border_edges_signal(self.paths["ghost"])
        self.assertEqual(s["strength"], "strong")
        self.assertGreaterEqual(s["score"], 2)

    def test_flat_fill_trips_missing_pattern(self):
        s = A.pattern_presence_signal(self.paths["flat"], "passport", "NG")
        self.assertEqual(s["strength"], "strong")
        self.assertLess(s["score"], 1.5)

    @unittest.skipUnless(TESS, "font consistency needs tesseract word boxes")
    def test_altered_digit_trips_font_consistency(self):
        s = A.font_consistency_signal(self.paths["font"], "passport", "NG")
        self.assertIn(s["strength"], ("moderate", "strong"), s)

@unittest.skipUnless(TESS, "session flows need tesseract")
class DocumentEvidenceRecord(unittest.TestCase):
    def test_clean_session_records_matrix_and_evidence(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1)
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["checks_summary"].get("data_consistency"), "pass")
            self.assertEqual(view["checks_summary"].get("document_evidence"), "pass")
            st, checks = call(srv, "GET", f"/v1/sessions/{ctx['session']['id']}/checks", key=key)
            self.assertEqual(st, 200, checks)
            by_type = {c["type"]: c for c in checks["checks"]}
            de = by_type["document_evidence"]["findings"]["components"]
            self.assertEqual(de["layout_classification"], "pass")
            self.assertEqual(de["text_extraction"], "pass")
            self.assertEqual(de["machine_readable"], "pass")
            self.assertEqual(de["image_quality"], "pass")
            dc = by_type["data_consistency"]["findings"]
            self.assertEqual(dc["disagreements"], [])
            self.assertIn("mrz", dc["sources_present"])

if __name__ == "__main__":
    unittest.main()
