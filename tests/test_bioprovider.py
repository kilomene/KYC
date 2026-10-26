"""Provider adapter (Phase 4 WS2, decision D5).

Contract: our own SFace pipeline is provider #1 THROUGH the interface;
external slots are named but NOT configured and must fail closed —
never a fabricated similarity, never a pass.
"""
import os, unittest

from server import bioprovider as BP

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "benchmarks", "corpus", "lfw_funneled")

class TestExternalSlotFailsClosed(unittest.TestCase):
    def test_unconfigured_provider(self):
        p = BP.get_provider("external:some-vendor")
        self.assertFalse(p.available())
        r = p.compare("a.jpg", "b.jpg")
        self.assertEqual(r["status"], "error", r)
        self.assertIn("provider_not_configured", r["reason_codes"])
        emb, err = p.embed("a.jpg")
        self.assertIsNone(emb)
        self.assertIsNotNone(err)
        self.assertIn("provider_not_configured", err["reason_codes"])

    def test_unknown_name_fails_closed(self):
        p = BP.get_provider("totally-unknown")
        self.assertFalse(p.available())
        self.assertEqual(p.compare("a", "b")["status"], "error")

    def test_registry_lists_own_provider(self):
        self.assertIn("own:sface", BP.PROVIDER_NAMES)

class TestSFaceProvider(unittest.TestCase):
    def test_is_production_threshold(self):
        from server import face as FACE
        self.assertEqual(BP.PRODUCTION_THRESHOLD, FACE.DEFAULT_THRESHOLD)
        p = BP.get_provider("own:sface")
        self.assertEqual(p.pass_threshold, FACE.DEFAULT_THRESHOLD)

    def test_compare_returns_standard_dict(self):
        p = BP.get_provider("own:sface")
        if not p.available():
            self.skipTest("face models not fetched")
        from tests.helpers import selfie_bytes
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(selfie_bytes()); path = f.name
        try:
            r = p.compare(path, path)
            self.assertIn(r["status"], ("pass", "unclear", "fail", "error", "not_run"))
            self.assertEqual(r["findings"].get("provider"), "own:sface")
        finally:
            os.unlink(path)

    def test_embed_no_face_is_marker_not_error(self):
        p = BP.get_provider("own:sface")
        if not p.available():
            self.skipTest("face models not fetched")
        from tests.helpers import selfie_bytes
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(selfie_bytes()); path = f.name
        try:
            emb, err = p.embed(path)  # drawn face: YuNet finds no real face
            self.assertIsNone(emb)
            self.assertIsNone(err)  # no-face is distinct from an error
        finally:
            os.unlink(path)

class TestFullResolutionDetection(unittest.TestCase):
    """WS2 regression: YuNet misses faces on multi-megapixel stills
    (measured on real phone captures). Detection downscales a copy
    and rescales the box — an upscaled real face must still detect,
    with the box in ORIGINAL image coordinates."""

    @unittest.skipUnless(os.path.isdir(CORPUS), "LFW corpus not downloaded")
    def test_upscaled_face_still_detects(self):
        import cv2
        from server import face as FACE
        if not FACE.models_present():
            self.skipTest("face models not fetched")
        src = os.path.join(CORPUS, "Aaron_Eckhart", "Aaron_Eckhart_0001.jpg")
        img = cv2.imread(src)
        self.assertIsNotNone(img)
        big = cv2.resize(img, (3000, 3000), interpolation=cv2.INTER_CUBIC)
        faces = FACE.detect_faces(big)
        self.assertTrue(faces, "no face detected in 3000x3000 upscale")
        x, y, w, h = [float(v) for v in faces[0][:4]]
        self.assertTrue(0 <= x <= 3000 and 0 <= y <= 3000 and w > 100 and h > 100,
                        f"box {(x, y, w, h)} not in original coordinates")

@unittest.skipUnless(os.path.isdir(CORPUS), "LFW corpus not downloaded")
class TestSFaceProviderOnRealFaces(unittest.TestCase):
    def test_same_person_scores_above_production_threshold(self):
        p = BP.get_provider("own:sface")
        if not p.available():
            self.skipTest("face models not fetched")
        sys_pairs = os.path.join(os.path.dirname(CORPUS), "pairs.txt")
        with open(sys_pairs) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        name, i, j = lines[1].split("\t")  # first same-person pair
        a = os.path.join(CORPUS, name, f"{name}_{int(i):04d}.jpg")
        b = os.path.join(CORPUS, name, f"{name}_{int(j):04d}.jpg")
        ea, erra = p.embed(a); eb, errb = p.embed(b)
        self.assertIsNotNone(ea, erra); self.assertIsNotNone(eb, errb)
        sim = p.similarity(ea, eb)
        self.assertGreater(sim, BP.PRODUCTION_THRESHOLD,
                           f"same-person LFW pair similarity {sim:.3f} should exceed the production threshold")

if __name__ == "__main__":
    unittest.main()
