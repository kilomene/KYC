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


class TestOrientationNormalization(unittest.TestCase):
    """Owner's order 2026-10-26, from his own sideways upload: 'it
    can be portrait, it can be landscape no matter how.' Uploaded
    images are stored upright; the reader never has to care how the
    photo was held."""

    def _normalized(self, data):
        from server import vision as V
        out, info = V.normalize_orientation_bytes(data, (1.2, 2.8))
        return out, info

    def test_sideways_slip_is_stored_upright(self):
        from PIL import Image
        raw = _synthetic_slip_bytes()
        im = Image.open(io.BytesIO(raw))
        for angle in (90, -90, 180):
            rot = im.rotate(angle, expand=True)
            buf = io.BytesIO(); rot.save(buf, format="PNG")
            out, info = self._normalized(buf.getvalue())
            self.assertTrue(info["applied"], (angle, info))
            # the corrected image reads the number cleanly
            fd, path = __import__("tempfile").mkstemp(suffix=".jpg")
            os.write(fd, out); os.close(fd)
            try:
                from server import fieldtemplates as FT
                from server import checks as C
                ocr = C.check_ocr(path, expect_mrz=False)
                ex = FT.extract_fields(path, "NG", "nin_slip",
                                       ocr_text=ocr.get("text", ""),
                                       ocr_texts=ocr.get("pass_texts"))
                num = ex["findings"]["fields"]["number"]
                self.assertEqual(num["value"], SLIP_NIN, (angle, ex))
            finally:
                os.unlink(path)

    def test_upright_slip_is_never_rotated(self):
        out, info = self._normalized(_synthetic_slip_bytes())
        self.assertFalse(info["applied"], info)
        self.assertEqual(info["angle"], 0, info)

    def test_rotated_upload_tallies_end_to_end(self):
        from PIL import Image
        im = Image.open(io.BytesIO(_slip_on_table_bytes()))
        rot = im.rotate(90, expand=True)
        buf = io.BytesIO(); rot.save(buf, format="PNG")
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            st, r = _upload(srv, token, buf.getvalue(), "nin_slip", claimed=SLIP_NIN)
            self.assertEqual(st, 201, r)
            st, p = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": r["document_id"]}, token)
            self.assertEqual(st, 200, p)
            self.assertEqual(p["number_tally"]["status"], "pass", p)
            self.assertTrue(p["number_tally"]["match"], p)


class TestPortraitOrientationDecider(unittest.TestCase):
    """The orientation chain's third decider: when the text
    deciders tie (tesseract auto-rotates sideways text internally,
    erasing the score evidence), the document's printed portrait
    decides — a face is only detectable upright. Uses a real LFW
    face composed into a card scene; skips when the corpus or the
    face models are unavailable (same contract as test_attacks)."""

    CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "benchmarks", "corpus", "lfw_funneled")

    def _scene(self):
        import glob
        from PIL import Image, ImageDraw
        from server import face as FACE
        if not FACE.models_present():
            self.skipTest("face models not fetched")
        files = sorted(glob.glob(os.path.join(self.CORPUS, "*", "*.jpg")))
        if not files:
            self.skipTest("LFW corpus not extracted")
        face = Image.open(files[0]).convert("RGB").resize((220, 220))
        card = Image.new("RGB", (900, 560), (238, 234, 222))
        d = ImageDraw.Draw(card)
        d.rectangle([640, 90, 860, 310], outline=(90, 90, 90), width=3)
        card.paste(face, (640, 90))
        d.text((60, 80), "SURNAME  EXAMPLE", fill=(20, 20, 20))
        d.text((60, 150), "FIRST NAME  TEST", fill=(20, 20, 20))
        d.text((60, 220), "NIN:  12345678901", fill=(20, 20, 20))
        scene = Image.new("RGB", (1200, 900), (52, 48, 44))
        scene.paste(card, (150, 170))
        return scene

    def test_probe_names_every_rotation(self):
        from server import vision as V
        scene = self._scene()
        self.assertEqual(V._portrait_orientation(scene, (1.2, 2.8)), 0)
        self.assertEqual(V._portrait_orientation(scene.rotate(-90, expand=True), (1.2, 2.8)), 270)
        self.assertEqual(V._portrait_orientation(scene.rotate(90, expand=True), (1.2, 2.8)), 90)
        self.assertEqual(V._portrait_orientation(scene.rotate(180, expand=True), (1.2, 2.8)), 180)

    def test_probe_silent_without_a_real_face(self):
        from PIL import Image
        from server import vision as V
        im = Image.open(io.BytesIO(_slip_on_table_bytes())).rotate(-90, expand=True)
        self.assertIsNone(V._portrait_orientation(im, (1.2, 2.8)))


class TestTiledWordFallback(unittest.TestCase):
    """Low-resolution uploads (owner's session-10 lesson): the
    full-page word pass goes nearly blind on small print, so
    ocr_words falls back to overlapping quadrant tiles — the labels
    and values come back at high confidence, and duplicate reads of
    the same printed word (a degraded token and its clean twin)
    merge by box overlap instead of joining into one value."""

    def test_tiles_rescue_labels_and_values(self):
        from PIL import Image, ImageFilter
        from server import vision as V
        im = Image.open(io.BytesIO(_synthetic_slip_bytes())).convert("RGB")
        im = im.resize((760, 380), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.9))
        buf = io.BytesIO(); im.save(buf, format="JPEG", quality=50)
        fd, path = __import__("tempfile").mkstemp(suffix=".jpg")
        os.write(fd, buf.getvalue()); os.close(fd)
        self.addCleanup(os.unlink, path)
        words = V.ocr_words(path)
        texts = [w["text"].upper().strip(':') for w in words]
        self.assertIn("NIN", texts)
        self.assertIn("SAMPLETON", texts)


class TestNumberZoneRecovery(unittest.TestCase):
    """The corroborated digit-zone recovery: completes a partial
    primary read only on a decisive variant vote that agrees with
    the digits already read; a conflicting partial vetoes it."""

    def _degraded_path(self):
        from PIL import Image, ImageFilter
        im = Image.open(io.BytesIO(_synthetic_slip_bytes())).convert("RGB")
        im = im.resize((560, 280), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
        buf = io.BytesIO(); im.save(buf, format="JPEG", quality=45)
        fd, path = __import__("tempfile").mkstemp(suffix=".jpg")
        os.write(fd, buf.getvalue()); os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def test_recovery_completes_a_corroborated_partial(self):
        from server import fieldtemplates as FT
        spec = FT.get_field_template("NG", "nin_slip")["fields"]["number"]
        got = FT._recover_number_zone(self._degraded_path(), spec, SLIP_NIN[:8])
        self.assertEqual(got, SLIP_NIN)

    def test_recovery_vetoed_by_a_conflicting_partial(self):
        from server import fieldtemplates as FT
        spec = FT.get_field_template("NG", "nin_slip")["fields"]["number"]
        got = FT._recover_number_zone(self._degraded_path(), spec, "99999999")
        self.assertIsNone(got)


if __name__ == "__main__":
    unittest.main()
