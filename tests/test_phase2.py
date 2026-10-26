"""Phase 2 tests: face decision logic, liveness analyser, authenticity
signals (ELA / moire / metadata), risk engine, flow config, and the
auto-decision upgrade. Model-dependent integration is skipUnless the
ONNX models have been fetched — the DECISION LOGIC is fully tested
without them."""
import io, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, multipart, make_tenant, drive_flow, structured_photo, jpeg_roundtrip
from server import face as FACE
from server import liveness as LV
from server import authenticity as AUTH
from server import risk as RISK
from server.engine import decide

MODELS = FACE.models_present()

class TestFaceDecisionLogic(unittest.TestCase):
    def test_cosine_identical_is_one(self):
        v = [0.3, -0.5, 0.8, 0.1]
        self.assertAlmostEqual(FACE.cosine_similarity(v, v), 1.0, places=6)
    def test_cosine_orthogonal_is_zero(self):
        self.assertAlmostEqual(FACE.cosine_similarity([1, 0, 0], [0, 1, 0]), 0.0, places=6)
    def test_cosine_opposite_is_minus_one(self):
        self.assertAlmostEqual(FACE.cosine_similarity([1, 2], [-1, -2]), -1.0, places=6)
    def test_same_embedding_passes(self):
        sim = FACE.cosine_similarity([0.2, 0.9, -0.4], [0.2, 0.9, -0.4])
        status, _ = FACE.similarity_decision(sim)
        self.assertEqual(status, "pass")
    def test_unrelated_embedding_fails(self):
        sim = FACE.cosine_similarity([1, 0, 0, 0], [0, 1, 0, 0])
        status, reasons = FACE.similarity_decision(sim)
        self.assertEqual(status, "fail"); self.assertIn("face_mismatch", reasons)
    def test_near_threshold_is_unclear(self):
        status, reasons = FACE.similarity_decision(0.363)  # exactly at threshold
        self.assertEqual(status, "unclear"); self.assertIn("face_match_near_threshold", reasons)
    def test_stricter_config_threshold_changes_decision(self):
        # sim 0.40 passes the default bar (0.363+0.05=0.413? no: near) —
        # with default margin it is 'unclear'; a stricter tenant threshold
        # keeps it unclear, a looser one passes it. The point: config moves
        # the decision, which is what item 6 requires.
        self.assertEqual(FACE.similarity_decision(0.40, 0.363, 0.05)[0], "unclear")
        self.assertEqual(FACE.similarity_decision(0.40, 0.30, 0.05)[0], "pass")
        self.assertEqual(FACE.similarity_decision(0.40, 0.50, 0.05)[0], "fail")  # 0.40 < 0.50-0.05

@unittest.skipUnless(MODELS, "face models not fetched (scripts/fetch_models.py)")
class TestFaceIntegration(unittest.TestCase):
    def test_no_face_in_drawing_is_unclear_not_pass(self):
        from helpers import id_image_bytes, selfie_bytes
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(id_image_bytes()); doc = f.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(selfie_bytes()); selfie = f.name
        r = FACE.check_face_match(doc, selfie)
        self.assertEqual(r["status"], "unclear", r)
        self.assertIn(r["reason_codes"][0], ("no_face_in_document", "no_face_in_selfie"))
    def test_missing_models_would_error(self):
        # Simulate absence by pointing MODELS_DIR elsewhere.
        orig = FACE.MODELS_DIR
        try:
            FACE.MODELS_DIR = "/nonexistent-models-dir"
            self.assertFalse(FACE.models_present())
            r = FACE.check_face_match(__file__, __file__)
            self.assertEqual(r["status"], "error"); self.assertIn("model_missing", r["reason_codes"])
        finally:
            FACE.MODELS_DIR = orig

def seq(moves, n=20, face_ratio=1.0, pix_var=6.0):
    """Build a synthetic frame-feature sequence. moves: list of
    (direction, frames) — centre travels that way for those frames."""
    feats = []
    cx = cy = 0.5
    step = 0.02
    plan = []
    for direction, frames in moves:
        plan += [direction] * frames
    plan += ["stay"] * max(0, n - len(plan))
    for i, mv in enumerate(plan[:n]):
        if mv == "left": cx -= step
        elif mv == "right": cx += step
        elif mv == "up": cy -= step
        elif mv == "down": cy += step
        face = (i / max(1, n)) < face_ratio
        feats.append({"face": face, "cx": cx, "cy": cy, "size": 0.3,
                      "pix_std": 20.0 + (pix_var if i % 2 else 0.0)})
    return feats

class TestLivenessAnalyser(unittest.TestCase):
    def test_moving_face_passes_challenge(self):
        feats = seq([("left", 8), ("up", 8)], n=20)
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "pass", r)
    def test_static_frames_fail_as_replay(self):
        feats = [{"face": True, "cx": 0.5, "cy": 0.5, "size": 0.3, "pix_std": 20.0} for _ in range(20)]
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("liveness_static_replay", r["reason_codes"])
    def test_face_mostly_absent_fails(self):
        feats = seq([("left", 8), ("up", 8)], n=20, face_ratio=0.3)
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "fail"); self.assertIn("liveness_face_absent", r["reason_codes"])
    def test_wrong_movement_is_unclear_not_pass(self):
        feats = seq([("right", 10)], n=20)
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "unclear", r)
    def test_challenge_is_server_generated_with_two_movements(self):
        ch = LV.new_challenge()
        self.assertEqual(len(ch["movements"]), 2)
        self.assertEqual(len(set(ch["movements"])), 2)
        self.assertTrue(all(m in LV.DIRECTIONS for m in ch["movements"]))

class TestAuthenticity(unittest.TestCase):
    def _tmp(self, im, suffix=".jpg", q=88):
        fd, p = tempfile.mkstemp(suffix=suffix); os.close(fd)
        if suffix == ".jpg":
            im.save(p, "JPEG", quality=q)
        else:
            im.save(p)
        return p
    def test_ela_clean_jpeg_no_signal(self):
        p = self._tmp(structured_photo())
        s = AUTH.ela_signal(p)
        self.assertEqual(s["strength"], "none", s)
    def test_ela_spliced_region_stands_out(self):
        clean = jpeg_roundtrip(structured_photo(), 88)
        from PIL import ImageDraw
        ImageDraw.Draw(clean).rectangle([200, 150, 400, 310], fill=(128, 128, 128))
        p = self._tmp(clean)
        s = AUTH.ela_signal(p)
        clean_score = AUTH.ela_signal(self._tmp(jpeg_roundtrip(structured_photo(), 88)))["score"]
        self.assertGreater(s["score"], clean_score, s)
        self.assertIn(s["strength"], ("moderate", "strong"), s)
    def test_moire_periodic_pattern_signals(self):
        import numpy as np
        g = np.zeros((600, 800))
        xs = np.arange(800)[None, :]; ys = np.arange(600)[:, None]
        g = 128 + 110 * np.sin(xs * 2 * np.pi / 6) * np.sin(ys * 2 * np.pi / 6)
        from PIL import Image
        p = self._tmp(Image.fromarray(g.astype("uint8")).convert("RGB"), suffix=".png")
        s = AUTH.moire_signal(p)
        self.assertIn(s["strength"], ("moderate", "strong"), s)
        p2 = self._tmp(structured_photo(), suffix=".png")
        s2 = AUTH.moire_signal(p2)
        self.assertEqual(s2["strength"], "none", s2)
        self.assertGreater(s["score"], s2["score"])
    def test_metadata_editor_tag_signals(self):
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        im = structured_photo()
        meta = PngInfo(); meta.add_text("Software", "OBS Studio screen recorder")
        fd, p = tempfile.mkstemp(suffix=".png"); os.close(fd)
        im.save(p, pnginfo=meta)
        s = AUTH.metadata_signal(p)
        self.assertEqual(s["strength"], "strong", s)
        self.assertTrue(s.get("editor_hits"))
    def test_single_weak_signal_never_fails(self):
        # Editor metadata alone (30 pts) must be unclear at most.
        from PIL.PngImagePlugin import PngInfo
        im = structured_photo()
        meta = PngInfo(); meta.add_text("Software", "Adobe Photoshop 25")
        fd, p = tempfile.mkstemp(suffix=".png"); os.close(fd)
        im.save(p, pnginfo=meta)
        r = AUTH.check_authenticity(p, kind="drivers_licence", ocr_text="DRIVER LICENCE", doc_number="AB12345")
        self.assertEqual(r["status"], "unclear", r)
    def test_clean_png_passes(self):
        p = self._tmp(structured_photo(), suffix=".png")
        r = AUTH.check_authenticity(p, kind="drivers_licence", ocr_text="DRIVER LICENCE", doc_number="AB12345")
        self.assertEqual(r["status"], "pass", r)

class TestRiskEngine(unittest.TestCase):
    def test_contributions_are_named_and_sum(self):
        r = RISK.compute_risk({
            "mrz": {"status": "fail", "reason_codes": ["mrz_check_digit_failed"]},
            "fraud_signals": {"status": "unclear", "reason_codes": ["ip_document_country_mismatch"]},
            "ocr": {"status": "pass", "reason_codes": []}})
        self.assertEqual(r["score"], 65, r)  # 40 + 25
        self.assertEqual(r["band"], "high")
        sources = {(c["source"], c["points"]) for c in r["contributions"]}
        self.assertIn(("mrz", 40), sources); self.assertIn(("fraud_signals", 25), sources)
        self.assertEqual(sum(c["points"] for c in r["contributions"]), r["score"])
    def test_banding(self):
        self.assertEqual(RISK.band_for(0), "low"); self.assertEqual(RISK.band_for(20), "low")
        self.assertEqual(RISK.band_for(21), "medium"); self.assertEqual(RISK.band_for(50), "medium")
        self.assertEqual(RISK.band_for(51), "high")
    def test_clean_case_scores_zero(self):
        r = RISK.compute_risk({"ocr": {"status": "pass", "reason_codes": []}})
        self.assertEqual(r["score"], 0); self.assertEqual(r["band"], "low"); self.assertEqual(r["contributions"], [])
    def test_engine_blocks_auto_approve_above_ceiling(self):
        checks = {"capture_quality": {"status": "pass", "reason_codes": []},
                  "ocr": {"status": "pass", "reason_codes": []},
                  "expiry_age": {"status": "pass", "reason_codes": []},
                  "consistency": {"status": "pass", "reason_codes": []}}
        out, _ = decide(1, checks, risk_score={"score": 65})
        self.assertEqual(out, "needs_review")
        out, _ = decide(1, checks, config={"risk_auto_approve_ceiling": 70}, risk_score={"score": 65})
        self.assertEqual(out, "approved")

class TestConfigAPI(unittest.TestCase):
    def test_config_roundtrip_and_versioning(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            st, r = call(srv, "GET", "/v1/config?level=2", key=key)
            self.assertEqual(st, 200); self.assertEqual(r["version"], 0)
            self.assertEqual(r["config"]["face_pass_threshold"], 0.363)
            st, r = call(srv, "PUT", "/v1/config", {"level": 2, "config": {"face_pass_threshold": 0.5}}, key=key)
            self.assertEqual(st, 200, r); self.assertEqual(r["version"], 1)
            st, r = call(srv, "GET", "/v1/config?level=2", key=key)
            self.assertEqual(r["config"]["face_pass_threshold"], 0.5)
            st, r = call(srv, "PUT", "/v1/config", {"level": 2, "config": {"nonsense": 1}}, key=key)
            self.assertEqual(st, 422)
    def test_config_change_affects_decision(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            # Clean Level 1 flow auto-approves under the default config...
            ctx = drive_flow(srv, key, level=1)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["decision"]["decided_by"], "engine")
            # ...then an impossible risk ceiling forces human review.
            st, r = call(srv, "PUT", "/v1/config", {"level": 1, "config": {"risk_auto_approve_ceiling": -1}}, key=key)
            self.assertEqual(st, 200, r)
            ctx2 = drive_flow(srv, key, level=1)
            st, view2 = call(srv, "POST", "/v1/flow/submit", {}, token=ctx2["token"])
            self.assertEqual(view2["status"], "needs_review", view2)
            self.assertIn("risk_above_auto_approve_ceiling", view2["decision"]["reason_codes"])
            self.assertEqual(view2["decision"]["config_version"], "v1")

class TestLivenessFlowAPI(unittest.TestCase):
    def test_challenge_then_video_upload_records_check(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=2)
            st, ch = call(srv, "POST", "/v1/flow/liveness/challenge", {}, token=ctx["token"])
            self.assertEqual(st, 201, ch)
            self.assertEqual(len(ch["challenge"]["movements"]), 2)
            # A short generated video of the drawn selfie scene: YuNet
            # finds no real face, so liveness must NOT pass — honest.
            try:
                import cv2, numpy as np
                from helpers import selfie_bytes
                fd, vp = tempfile.mkstemp(suffix=".mp4"); os.close(fd)
                img = cv2.imdecode(np.frombuffer(selfie_bytes(), np.uint8), cv2.IMREAD_COLOR)
                vw = cv2.VideoWriter(vp, cv2.VideoWriter_fourcc(*"mp4v"), 10, (img.shape[1], img.shape[0]))
                for _ in range(15): vw.write(img)
                vw.release()
                with open(vp, "rb") as f: vdata = f.read()
            except Exception:
                self.skipTest("cv2 video writing unavailable")
            st, r = multipart(srv, "/v1/flow/liveness", {}, {"video": ("liveness.mp4", vdata, "video/mp4")}, ctx["token"])
            self.assertEqual(st, 201, r)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(st, 200, view)
            self.assertIn(view["checks_summary"]["liveness"], ("fail", "unclear", "error"), view)
            self.assertNotEqual(view["status"], "approved", view)

if __name__ == "__main__":
    unittest.main()
