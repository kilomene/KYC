"""Presentation-attack suite harness (Phase 4 WS2) — smoke tests.

Runs ONE simulated print artefact through the production defences
and asserts the harness produces verdicts and the static presentation
is NOT passed by the combination. Skips when the LFW corpus or the
face models are unavailable (the corpus is gitignored).

Honesty contract: these tests guard the HARNESS, not the catch rate.
Measured catch rates live in benchmarks/BIOMETRICS.md /
benchmarks/attacks.json from the full suite run.
"""
import os, unittest

from server import face as FACE

CORPUS_READY = os.path.isdir(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "benchmarks", "corpus", "lfw_funneled"))

@unittest.skipUnless(CORPUS_READY, "LFW corpus not extracted")
class TestAttackHarnessSmoke(unittest.TestCase):
    def test_print_simulation_and_defences(self):
        if not FACE.models_present():
            self.skipTest("face models not fetched")
        import cv2
        from scripts import benchmark_attacks as A
        os.makedirs(A.WORK, exist_ok=True)
        faces = A.lfw_faces(1)
        self.assertTrue(faces, "no LFW faces available")
        img = cv2.imread(faces[0][0])
        self.assertIsNotNone(img)
        printed = A.simulate_print(img)
        self.assertEqual(printed.shape, img.shape)
        video = A.write_video(A.present_on_paper(printed, seconds=2, handheld=False),
                              os.path.join(A.WORK, "test_print.mp4"))
        self.assertIsNotNone(video)
        out = A.run_defences(video, faces[0][0])
        self.assertIn("legs", out)
        self.assertIn("rejected", out)
        # A static printed photo must never sail through the whole
        # combination: liveness (movement challenge) cannot pass on a
        # frozen presentation, so all_passing must be False.
        self.assertFalse(out["combination_all_passing"], out)

    def test_screen_simulation_changes_frame(self):
        import numpy as np
        from scripts import benchmark_attacks as A
        img = (np.random.RandomState(1).rand(120, 160, 3) * 255).astype(np.uint8)
        out = A.simulate_screen_frame(img, t=0.1)
        self.assertEqual(out.shape, img.shape)
        self.assertFalse(np.array_equal(out, img))

if __name__ == "__main__":
    unittest.main()
