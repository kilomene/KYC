"""PAD harness metrics: APCER counts only 'pass' as an attack
success; BPCER splits reject vs nonpass; ACER is their mean."""
import importlib.util, os, unittest
spec = importlib.util.spec_from_file_location(
    "pad_eval", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "scripts", "pad_eval.py"))
pad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pad)


class TestPadMetrics(unittest.TestCase):
    def test_metrics(self):
        m = pad.compute_metrics({
            "bona_fide": ["pass", "pass", "fail", "unclear"],
            "attack_static_photo": ["fail", "unclear"],
            "attack_replay": ["pass", "fail"],
        })
        self.assertAlmostEqual(m["apcer"]["attack_static_photo"], 0.0)
        self.assertAlmostEqual(m["apcer"]["attack_replay"], 0.5)
        self.assertAlmostEqual(m["apcer_overall"], 0.25)
        self.assertAlmostEqual(m["bpcer_reject"], 0.25)
        self.assertAlmostEqual(m["bpcer_nonpass"], 0.5)
        self.assertAlmostEqual(m["acer"], 0.25)


if __name__ == "__main__":
    unittest.main()
