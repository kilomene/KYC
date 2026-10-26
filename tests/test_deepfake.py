"""Deepfake / fake-camera defence (Addition 7, 2026-10-26).

Honest-scope tests: the rPPG pulse leg is scored by a pure function —
a synthetic pulse in the human band must read present; a flat/static
series must NOT. A known virtual-camera label is a hard fail. And the
full check on synthetic (drawn, faceless) liveness media must never
return pass — unanalysable is unclear/error, not a pass."""
import math, random, tempfile, unittest

import numpy as np

from server import deepfake as DF

class TestPulseLeg(unittest.TestCase):
    def test_synthetic_pulse_reads_present(self):
        fps = 30.0
        rng = random.Random(4)
        series = [120 + 2.5 * math.sin(2 * math.pi * 1.2 * (i / fps)) + rng.gauss(0, 0.4)
                  for i in range(int(fps * 5))]
        r = DF.pulse_from_series(series, fps)
        self.assertIsNotNone(r["score"], r)
        self.assertTrue(r["present"], r)
        self.assertAlmostEqual(r["peak_hz"], 1.2, delta=0.35)

    def test_static_series_has_no_pulse(self):
        series = [120.0 + (0.01 if i % 7 == 0 else 0.0) for i in range(150)]
        r = DF.pulse_from_series(series, 30.0)
        self.assertFalse(r["present"], r)

    def test_animated_non_pulse_series_does_not_pass_pulse_leg(self):
        # Smooth non-physiological drift (slow ramp + steps): energy is
        # real but NOT a coherent in-band pulse.
        series = [100 + 0.05 * i + (5 if i > 100 else 0) for i in range(150)]
        r = DF.pulse_from_series(series, 30.0)
        self.assertFalse(r["present"], r)

    def test_short_clip_is_unanalysable_not_absent(self):
        r = DF.pulse_from_series([120.0] * 30, 30.0)  # 1 second
        self.assertIsNone(r["score"], r)
        self.assertFalse(r["present"], r)

class TestClientSignals(unittest.TestCase):
    def test_virtual_camera_labels_hit(self):
        for label in ("OBS Virtual Camera", "ManyCam Virtual Webcam", "Snap Camera", "Logitech Capture (Virtual)"):
            f = DF.client_signal_findings({"track_label": label, "motion": {"sensor_present": True, "samples": 50, "variance": 0.3}})
            self.assertIsNotNone(f["virtual_camera_hit"], label)

    def test_normal_camera_label_clean(self):
        f = DF.client_signal_findings({"track_label": "FaceTime HD Camera",
                                       "motion": {"sensor_present": True, "samples": 200, "variance": 0.42}})
        self.assertIsNone(f["virtual_camera_hit"])
        self.assertFalse(f["motion_absent"]); self.assertFalse(f["motion_frozen"])

    def test_motion_absent_and_frozen_flags(self):
        f = DF.client_signal_findings({"track_label": "USB Camera",
                                       "motion": {"sensor_present": False, "samples": 0, "variance": 0}})
        self.assertTrue(f["motion_absent"])
        f2 = DF.client_signal_findings({"track_label": "USB Camera",
                                        "motion": {"sensor_present": True, "samples": 300, "variance": 0.0}})
        self.assertTrue(f2["motion_frozen"])

    def test_virtual_camera_label_fails_without_any_video(self):
        r = DF.check_deepfake(None, None, {"track_label": "OBS Virtual Camera"})
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("virtual_camera_detected", r["reason_codes"])

    def test_missing_video_is_not_run_never_pass(self):
        r = DF.check_deepfake(None, None, {"track_label": "FaceTime HD Camera"})
        self.assertEqual(r["status"], "not_run", r)

class TestSyntheticMediaNeverPasses(unittest.TestCase):
    def test_drawn_animated_video_does_not_pass(self):
        try:
            import cv2
        except Exception:
            self.skipTest("opencv unavailable")
        path = tempfile.mktemp(suffix=".mp4")
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
        if not vw.isOpened():
            self.skipTest("no mp4 writer in this opencv build")
        for i in range(90):
            frame = np.full((240, 320, 3), 180, np.uint8)
            cx = 120 + i
            cv2.ellipse(frame, (cx, 120), (45, 60), 0, 0, 360, (150, 120, 100), -1)
            cv2.circle(frame, (cx - 15, 105), 5, (40, 40, 40), -1)
            cv2.circle(frame, (cx + 15, 105), 5, (40, 40, 40), -1)
            vw.write(frame)
        vw.release()
        r = DF.check_deepfake(path, None, {"track_label": "USB Camera",
                                          "motion": {"sensor_present": True, "samples": 90, "variance": 0.2}})
        self.assertNotEqual(r["status"], "pass", r)
        self.assertIn(r["status"], ("unclear", "error", "fail"), r)
        # The drawn ellipse is not a YuNet face: the pulse leg must have
        # found nothing to measure — recorded honestly in the findings.
        self.assertFalse(r["findings"]["pulse"]["present"], r)

if __name__ == "__main__":
    unittest.main()
