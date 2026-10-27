"""Regression: numpy-typed check findings must serialize (2026-10-26).

Production root cause: the decision pipeline crashed at
record("face_track", ...) — the face track's findings contain numpy
float32 cosine scores, and record()'s json.dumps raised
"TypeError: Object of type float32 is not JSON serializable". The
pipeline died mid-pass (500) and the session was orphaned in
'processing'. The synthetic e2e face track never produced float32
findings, so this shipped — this test constructs them directly.
"""
import json
import unittest

import numpy as np

from server.app import _json_default


class TestNumpyFindingsSerialize(unittest.TestCase):
    def test_record_style_dumps_with_numpy_findings(self):
        # Exactly the two dumps calls record() makes, on a check result
        # shaped like the face track's (float32 scores, int64 counts).
        res = {
            "status": "pass",
            "reason_codes": [],
            "findings": {
                "median_cosine": np.float32(0.913),
                "min_cosine": np.float64(0.8125),
                "frames_seen": np.int64(25),
                "identity_stable": np.bool_(True),
                "per_frame": np.array([0.91, 0.88, 0.93], dtype=np.float32),
                "nested": {"presence": np.float32(0.96)},
            },
        }
        findings = json.loads(json.dumps(res.get("findings", {}),
                                         default=_json_default))
        self.assertAlmostEqual(findings["median_cosine"], 0.913, places=3)
        self.assertAlmostEqual(findings["min_cosine"], 0.8125, places=4)
        self.assertEqual(findings["frames_seen"], 25)
        self.assertIs(findings["identity_stable"], True)
        self.assertEqual(len(findings["per_frame"]), 3)
        self.assertAlmostEqual(findings["nested"]["presence"], 0.96,
                               places=2)
        codes = json.loads(json.dumps(res.get("reason_codes", []),
                                      default=_json_default))
        self.assertEqual(codes, [])

    def test_decision_style_dumps_with_numpy_contributions(self):
        # The decision INSERT's two dumps calls (reasons, risk
        # contributions) get the same converter.
        reasons = ["face_track_low"]
        contributions = [{"check": "face_track",
                          "points": np.int32(10),
                          "weight": np.float32(0.5)}]
        self.assertEqual(json.loads(json.dumps(
            reasons, default=_json_default)), reasons)
        out = json.loads(json.dumps(contributions, default=_json_default))
        self.assertEqual(out[0]["points"], 10)
        self.assertAlmostEqual(out[0]["weight"], 0.5, places=4)

    def test_native_values_unchanged(self):
        # The converter must not alter plain JSON values.
        plain = {"a": 1, "b": 2.5, "c": True, "d": "x", "e": [1, 2],
                 "f": None}
        self.assertEqual(
            json.dumps(plain, default=_json_default, sort_keys=True),
            json.dumps(plain, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
