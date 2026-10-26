"""Automatic decisions + detection gates (2026-10-26, Parts A/B and
Additions 4-6): no manual review in the standard path.

- a non-document image auto-REJECTS on framing (never review);
- an unclear framing (document too small) auto-REJECTS for rescan;
- a clean synthetic card session auto-APPROVES;
- a face auto-match failure auto-REJECTS (Addition 5.3);
- a passport whose MRZ check digits are broken auto-REJECTS on the
  INTERNAL layer even though surface+text look clean (Addition 6);
- screen-recapture and portrait-splice evidence fire (Addition 5);
- registry aspect hints exist for card/passport/slip (Part A);
- the flow page's static contract: no file input, no shutter, the
  guidance map covers every state, voice + phone gate + client
  signals wired (Additions 1/2/5/7)."""
import io, os, tempfile, unittest
from unittest import mock

from PIL import Image

from helpers import (Server, call, make_tenant, drive_flow, id_image_bytes,
                     structured_photo, screen_recapture_bytes, portrait_splice_bytes)
from server import authenticity as AUTH
from server import docregistry as DOCREG
from server import face as FACE
from server import facetrack as FACETRACK
from server import liveness as LV
from server import deepfake as DEEPFAKE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _submit(srv, ctx):
    st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
    assert st == 200, view
    return view

class TestAutoDecision(unittest.TestCase):
    def test_room_photo_auto_rejects_not_review(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            buf = io.BytesIO(); structured_photo(size=(1240, 800)).save(buf, "PNG")
            ctx = drive_flow(srv, key, level=1, doc_bytes=buf.getvalue())
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "rejected", view)
            self.assertEqual(view["checks_summary"]["document_framing"], "fail", view)
            self.assertIn("document_not_detected", view["decision"]["reason_codes"], view)

    def test_small_document_auto_rejects_for_rescan(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            card = Image.open(io.BytesIO(id_image_bytes())).resize((430, 278))
            canvas = Image.new("RGB", (1240, 800), (200, 200, 200))
            canvas.paste(card, (405, 261))
            buf = io.BytesIO(); canvas.save(buf, "PNG")
            ctx = drive_flow(srv, key, level=1, doc_bytes=buf.getvalue())
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "rejected", view)
            self.assertIn("document_quality_rescan", view["decision"]["reason_codes"], view)

    def test_clean_card_session_auto_approves_with_layers(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1)
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["checks_summary"]["document_framing"], "pass", view)
            self.assertEqual(view["checks_summary"]["verification_layers"], "pass", view)
            self.assertEqual(view["checks_summary"]["mrz_viz_consistency"], "pass", view)

    def test_face_mismatch_auto_rejects(self):
        # The matcher itself is unit-tested (test_phase2) and no real
        # face fixtures exist for the drawn media, so the two biometric
        # engines are stubbed to isolate the DECISION: face match fails
        # decisively -> the machine rejects; no human is consulted.
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=2)
            fail = {"status": "fail", "findings": {"similarity": 0.05}, "reason_codes": ["face_mismatch"]}
            passthrough = lambda *a, **k: {"status": "pass", "findings": {}, "reason_codes": []}
            track = lambda *a, **k: {"status": "pass", "findings": {}, "reason_codes": []}
            with mock.patch.object(FACE, "check_face_match", return_value=fail), \
                 mock.patch.object(FACETRACK, "check_face_track", side_effect=track), \
                 mock.patch.object(LV, "check_liveness", side_effect=passthrough), \
                 mock.patch.object(DEEPFAKE, "check_deepfake", side_effect=passthrough):
                view = _submit(srv, ctx)
            self.assertEqual(view["status"], "rejected", view)
            self.assertEqual(view["checks_summary"]["face_match"], "fail", view)
            self.assertIn("face_mismatch", view["decision"]["reason_codes"], view)

    def test_corrupt_mrz_passport_rejects_on_internal_layer(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1, doc_bytes=id_image_bytes(corrupt_mrz=True))
            view = _submit(srv, ctx)
            self.assertEqual(view["status"], "rejected", view)
            self.assertIn("internal_data_unreadable", view["decision"]["reason_codes"], view)
            self.assertEqual(view["checks_summary"]["verification_layers"], "fail", view)

class TestScreenAndPortraitEvidence(unittest.TestCase):
    def _auth(self, data, suffix=".jpg"):
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(data); f.close()
        return AUTH.check_authenticity(f.name, kind="drivers_licence", ocr_text="DRIVER LICENCE", mrz_found=False)

    def test_screen_recapture_fires_document_on_screen(self):
        r = self._auth(screen_recapture_bytes())
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("document_on_screen", r["reason_codes"], r)
        self.assertTrue(r["findings"]["screen_detected"], r)
        self.assertGreaterEqual(len(r["findings"]["screen_evidence"]), 2, r)

    def test_clean_card_shows_no_screen_evidence(self):
        buf = io.BytesIO()
        from helpers import jpeg_roundtrip
        jpeg_roundtrip(structured_photo(size=(900, 580)), 88).save(buf, "JPEG", quality=88)
        r = self._auth(buf.getvalue())
        self.assertFalse(r["findings"]["screen_detected"], r)
        self.assertNotIn("document_on_screen", r["reason_codes"], r)
        self.assertEqual(r["status"], "pass", r)

    def test_portrait_splice_fires_named_finding(self):
        r = self._auth(portrait_splice_bytes())
        portrait = [s for s in r["findings"]["signals"] if s["name"] == "portrait"][0]
        self.assertEqual(portrait["strength"], "strong", r)
        self.assertIn("portrait_region_tamper", r["reason_codes"], r)

class TestRegistryAspects(unittest.TestCase):
    def test_aspect_hints_present(self):
        self.assertAlmostEqual(DOCREG.get_document("NG", "passport")["aspect"], 1.42)
        self.assertAlmostEqual(DOCREG.get_document("US", "drivers_license")["aspect"], 1.586)
        self.assertAlmostEqual(DOCREG.get_document("NG", "nin_slip")["aspect"], 1.41)
        for country, docs in DOCREG.DOCUMENT_REGISTRY.items():
            for kind, entry in docs.items():
                self.assertIn("aspect", entry, f"{country}/{kind} missing aspect hint")

class TestFlowPageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "public", "flow.html")) as f:
            cls.html = f.read()

    def test_no_file_input_no_shutter(self):
        self.assertNotIn('type="file"', self.html)
        self.assertNotIn("capture-btn", self.html)

    def test_guidance_map_covers_every_state(self):
        states = ["starting", "doc_dark", "doc_dim", "doc_none", "doc_screen", "doc_glare",
                  "doc_blurry", "doc_unstable", "doc_hold", "doc_captured", "doc_flip",
                  "poa_none", "face_dark", "face_bright", "face_none", "face_centre",
                  "face_close", "face_far", "face_unstable", "face_hold", "face_captured",
                  "lv_wait", "lv_record", "lv_turn_left", "lv_turn_right", "lv_turn_up",
                  "lv_turn_down", "lv_done"]
        for s in states:
            self.assertIn(f"{s}:", self.html, f"guidance state {s} missing from the map")
        # the descriptive, environment-aware voice lines (Addition 2.1)
        self.assertIn("The place where you are is dark. Move to a brighter place.", self.html)
        self.assertIn("This looks like a screen. Scan the physical document.", self.html)
        self.assertIn("speechSynthesis", self.html)

    def test_phone_gate_qr_and_camera_constraints(self):
        self.assertIn("(pointer: coarse)", self.html)
        self.assertIn("This verification can only be completed on a phone.", self.html)
        self.assertIn("qrMatrix", self.html)
        self.assertIn("ideal:1920", self.html.replace(" ", ""))

    def test_client_signals_wired(self):
        self.assertIn("client_signals", self.html)
        self.assertIn("devicemotion", self.html)
        self.assertIn("getVideoTracks", self.html)

if __name__ == "__main__":
    unittest.main()
