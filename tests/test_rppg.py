"""rPPG hardening (Phase 4 WS2): POS + CHROM pulse legs, the
signal-quality gate, the combination rule, and the longer liveness
capture window the pulse leg needs.

Honest-scope contract (same as test_deepfake): a synthetic pulse in
the human band must read present on the POS/CHROM legs; a flat series
must be UNANALYSABLE (score None), never a fabricated present; and a
pulse measured through an unstable ROI must NOT count as present —
the quality gate is what makes 'pulse measured' mean something.
"""
import math, os, random, unittest

import numpy as np

from server import deepfake as DF

FPS = 30.0

def _skin_series(seconds=6, hz=1.25, seed=7, jitter_amp=0.0):
    rng = random.Random(seed)
    out = []
    for i in range(int(FPS * seconds)):
        p = math.sin(2 * math.pi * hz * (i / FPS))
        jit = rng.gauss(0, jitter_amp)
        out.append((100 * (1 + 0.008 * p) + jit,
                    150 * (1 + 0.020 * p) + jit,
                    110 * (1 + 0.010 * p) + jit))
    return out

class TestPosChromLegs(unittest.TestCase):
    def test_pos_reads_synthetic_pulse(self):
        r = DF.pulse_from_rgb_series(_skin_series(), FPS, "pos")
        self.assertIsNotNone(r["score"], r)
        self.assertTrue(r["present"], r)
        self.assertAlmostEqual(r["peak_hz"], 1.25, delta=0.35)

    def test_chrom_reads_synthetic_pulse(self):
        r = DF.pulse_from_rgb_series(_skin_series(), FPS, "chrom")
        self.assertIsNotNone(r["score"], r)
        self.assertTrue(r["present"], r)

    def test_flat_series_is_unanalysable(self):
        flat = [(100.0, 150.0, 110.0)] * 180
        for m in ("pos", "chrom"):
            r = DF.pulse_from_rgb_series(flat, FPS, m)
            self.assertIsNone(r["score"], (m, r))
            self.assertFalse(r["present"], (m, r))

    def test_short_series_is_unanalysable(self):
        r = DF.pulse_from_rgb_series(_skin_series(seconds=1), FPS, "pos")
        self.assertIsNone(r["score"], r)
        self.assertFalse(r["present"], r)

class TestQualityGate(unittest.TestCase):
    def test_smooth_track_is_quality_ok(self):
        centres = [(0.5 + 0.001 * i, 0.5) for i in range(100)]
        q = DF.signal_quality(centres, [0.4] * 100, 0.95)
        self.assertTrue(q["quality_ok"], q)

    def test_jittery_roi_fails_quality(self):
        centres = [(0.5 if i % 2 else 0.2, 0.5) for i in range(100)]
        q = DF.signal_quality(centres, [0.4] * 100, 0.95)
        self.assertFalse(q["quality_ok"], q)

    def test_low_presence_fails_quality(self):
        centres = [(0.5, 0.5)] * 100
        q = DF.signal_quality(centres, [0.4] * 100, 0.4)
        self.assertFalse(q["quality_ok"], q)

class TestCombinePulse(unittest.TestCase):
    def _legs(self, pos_present=True):
        pos = {"score": 0.4, "present": pos_present, "peak_hz": 1.2, "frames": 180, "seconds": 6.0}
        chrom = {"score": 0.4, "present": True, "peak_hz": 1.2, "frames": 180, "seconds": 6.0}
        green = {"score": 0.4, "present": True, "peak_hz": 1.2, "frames": 180, "seconds": 6.0}
        return green, pos, chrom

    def test_pos_present_plus_quality_is_present(self):
        green, pos, chrom = self._legs()
        q = {"face_ratio": 0.95, "centre_jitter": 0.002, "size_cv": 0.02, "quality_ok": True}
        out = DF.combine_pulse(green, pos, chrom, q)
        self.assertTrue(out["present"], out)
        self.assertEqual(out["method_used"], "pos")
        self.assertIn("pos", out["methods_present"])

    def test_quality_gate_blocks_present(self):
        green, pos, chrom = self._legs()
        q = {"face_ratio": 0.95, "centre_jitter": 0.3, "size_cv": 0.02, "quality_ok": False}
        out = DF.combine_pulse(green, pos, chrom, q)
        self.assertFalse(out["present"], out)
        self.assertEqual(out.get("reason"), "signal_quality_gate")
        # The legs' own verdicts are preserved, not rewritten.
        self.assertTrue(out["pos"]["present"])

    def test_pos_unanalysable_falls_back_to_green_labelled(self):
        green, pos, chrom = self._legs()
        pos = {"score": None, "present": False, "reason": "band_empty", "frames": 180}
        q = {"face_ratio": 0.95, "centre_jitter": 0.002, "size_cv": 0.02, "quality_ok": True}
        out = DF.combine_pulse(green, pos, chrom, q)
        self.assertTrue(out["present"], out)
        self.assertEqual(out["method_used"], "green_fallback")

class TestFlowWindow(unittest.TestCase):
    def test_flow_records_longer_higher_quality_liveness(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "public", "flow.html")
        with open(path) as f:
            html = f.read()
        # WS2: ~9 s window + raised bitrate so the pulse leg gets a
        # measurable clip (the old 4.5 s default measured no pulse on
        # real captures — see benchmarks/BIOMETRICS.md).
        self.assertIn("9000", html)
        self.assertNotIn("}, 4500)", html)
        self.assertIn("videoBitsPerSecond", html)

if __name__ == "__main__":
    unittest.main()
