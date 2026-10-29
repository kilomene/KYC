"""Session-18 incident fixes (2026-10-29). Three repairs, each tied
to a measured failure on the owner's real session:

1. OCR winner selection: a pass that read NOTHING at ~95% tesseract
   confidence (the contrast-enhanced rendition can blank a faint
   slip's print) beat passes that read the document fully, and the
   OCR check declared ocr_low_text over a fully-read document.
   Text-bearing passes now form the winner pool whenever one exists.
2. Document portrait enhancement: extract_document_portrait_feature
   reads the warped rendition through CLAHE + 2x first (genuine
   0.369 -> 0.441 measured; impostors stay ~0.03) and falls back to
   the plain read when the enhanced one finds no face.
3. Submit read reuse: the read-back job keeps its full
   _read_document result and the decision pipeline reuses it
   (fenced by completion + claim fingerprint + framing not failed)
   instead of paying the dual-engine read twice.
Plus the flow contract: the liveness recorder takes the framed
canvas (what the user sees), never the raw sensor stream, unless
canvas capture is unavailable.

All fixture values are synthetic. No owner data in this file.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from server import vision as VISION
from server import face as FACE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestOcrWinnerSelection(unittest.TestCase):
    def test_empty_confident_pass_cannot_win(self):
        import tempfile
        d = tempfile.mkdtemp()
        pa = os.path.join(d, "a.png")
        pb = os.path.join(d, "b.png")
        Image.new("RGB", (400, 300), (200, 200, 200)).save(pa)
        Image.new("RGB", (400, 300), (210, 210, 210)).save(pb)
        text = ("NATIONAL IDENTITY MANAGEMENT COMMISSION "
                "FEDERAL REPUBLIC OF NIGERIA ") * 8
        orig_prep = VISION._prep_variants
        orig_enh = VISION.enhanced_rendition
        orig_tsv = VISION._tesseract_tsv

        def fake_tsv(exe, vpath):
            if vpath == pa:
                return text, 72.4
            return "", 95.0

        VISION._prep_variants = lambda p: [("plain", pa)]
        VISION.enhanced_rendition = lambda p: pb
        VISION._tesseract_tsv = fake_tsv
        try:
            r = VISION.read_document_text(pa, expect_mrz=False)
        finally:
            VISION._prep_variants = orig_prep
            VISION.enhanced_rendition = orig_enh
            VISION._tesseract_tsv = orig_tsv
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertEqual(r["findings"]["chosen"], "plain")
        self.assertGreaterEqual(r["findings"]["chars"], 10)
        self.assertIn("text-bearing", r["findings"]["choice_reason"])


class TestPortraitHelperContract(unittest.TestCase):
    def test_blank_image_falls_back_cleanly(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "blank.png")
        Image.new("RGB", (300, 200), (128, 128, 128)).save(p)
        feat, face, err, enh = FACE.extract_document_portrait_feature(p)
        self.assertIsNone(feat)
        self.assertIsNone(face)
        self.assertIsNone(err)
        self.assertEqual(enh, "none")

    def test_missing_file_does_not_raise(self):
        feat, face, err, enh = FACE.extract_document_portrait_feature(
            "/nonexistent/definitely-not-here.png")
        self.assertIsNone(feat)
        self.assertEqual(enh, "none")


class TestReadReuse(unittest.TestCase):
    def test_process_stashes_read_and_submit_decides(self):
        from helpers import Server, call, multipart, make_tenant, selfie_bytes
        from server import app as APPMOD
        from test_identity_from_document import _document_session, _checks
        from test_nin_slip_upload import _upload, SLIP_NIN
        from test_identity_from_document import _slip_on_table_bytes
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, _slip_on_table_bytes(),
                            "nin_slip", claimed=SLIP_NIN)
            self.assertEqual(st, 201, r)
            did = r["document_id"]
            st, p = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": did}, token=token)
            self.assertEqual(st, 200, p)
            job = APPMOD._READ_JOBS.get(did)
            self.assertIsNotNone(job, "read job missing")
            self.assertIsNotNone(job.get("read"),
                                 "job did not stash the full read")
            st, r = multipart(srv, "/v1/flow/selfie", {},
                              {"selfie": ("selfie.png", selfie_bytes(),
                                          "image/png")}, token)
            self.assertEqual(st, 201, r)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            self.assertIn(view["status"],
                          ("approved", "rejected", "needs_review",
                           "manual_review", "processing"), view)
            checks = _checks(srv, key, sess["id"])
            self.assertEqual(checks["number_tally"]["status"], "pass",
                             checks.get("number_tally"))


class TestFramedCanvasRecording(unittest.TestCase):
    def test_flow_records_the_framed_canvas(self):
        html = open(os.path.join(ROOT, "public", "flow.html")).read()
        self.assertIn("captureStream", html)
        self.assertIn("framed_canvas", html)
        self.assertIn("recording_source", html)
        self.assertIn("new MediaRecorder(recSrc", html)


if __name__ == "__main__":
    unittest.main()
