"""Biometrics benchmark harness (Phase 4 WS2) — smoke + metric tests.

The PURE metric functions are tested on synthetic score records
(always run). The LFW harness test runs a SMALL subset (40 pairs)
through the production pipeline and asserts the harness produces
metrics and detection works; it skips when the corpus has not been
downloaded/extracted (the corpus is gitignored — see
benchmarks/BIOMETRICS.md for sources).

Calibration note: full-run numbers live in benchmarks/BIOMETRICS.md /
benchmarks/biometrics.json. Floors here are sanity floors far below
the measured full-run values, set so a real pipeline regression
(broken detection, broken embeddings) trips them — they are not the
benchmark result.
"""
import os, tempfile, unittest

from scripts import benchmark_biometrics as B

CORPUS_READY = (os.path.isfile(B.PAIRS_FILE)
                and os.path.isdir(B.IMAGES_DIR)
                and any(os.path.isdir(os.path.join(B.IMAGES_DIR, d)) for d in os.listdir(B.IMAGES_DIR))
                ) if os.path.isdir(B.IMAGES_DIR) else False

def _records(separable=True):
    recs = []
    if separable:
        for i in range(100):
            recs.append((0.8, True, i % 10))
            recs.append((0.1, False, i % 10))
        return recs
    # Genuinely overlapping: same ~ N(0.45, 0.10), diff ~ N(0.40, 0.10)
    # — no threshold separates them, so the EER must be substantial.
    # (An earlier version used constant 0.45/0.40 scores, which ARE
    # separable by any threshold in between and correctly gave
    # EER 0 — the fixture was wrong, not the metric.)
    import random
    rng = random.Random(42)
    for i in range(200):
        recs.append((min(1.0, max(0.0, rng.gauss(0.45, 0.10))), True, i % 10))
        recs.append((min(1.0, max(0.0, rng.gauss(0.40, 0.10))), False, i % 10))
    return recs

class TestPureMetrics(unittest.TestCase):
    def test_far_frr_on_separable_scores(self):
        m = B.far_frr(_records(), 0.363)
        self.assertEqual(m["far"], 0.0)
        self.assertEqual(m["frr"], 0.0)
        self.assertEqual(m["accuracy"], 1.0)

    def test_eer_on_separable_scores_is_zero(self):
        _curve, eer = B.sweep_and_eer(_records())
        self.assertEqual(eer["eer"], 0.0)

    def test_eer_on_overlapping_scores_is_high(self):
        _curve, eer = B.sweep_and_eer(_records(separable=False))
        self.assertGreater(eer["eer"], 0.3)

    def test_protocol_accuracy_runs(self):
        pa = B.protocol_accuracy(_records())
        self.assertEqual(pa["folds"], 10)
        self.assertGreater(pa["mean"], 0.99)

    def test_threshold_for_far(self):
        out = B.threshold_for_far(_records(), 0.001)
        self.assertIsNotNone(out["threshold"])
        self.assertLessEqual(out["far"], 0.001)

class TestPairsParsing(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(B.PAIRS_FILE), "pairs.txt not downloaded")
    def test_official_pairs_structure(self):
        pairs = B.load_pairs()
        self.assertEqual(len(pairs), 6000)
        self.assertEqual(sum(1 for p in pairs if p["same"]), 3000)
        self.assertEqual(sorted(set(p["fold"] for p in pairs)), list(range(10)))

class TestDegradations(unittest.TestCase):
    def test_degradations_preserve_shape(self):
        import numpy as np
        img = (np.random.RandomState(3).rand(250, 250, 3) * 255).astype(np.uint8)
        for name, fn in B.DEGRADATIONS.items():
            out = fn(img.copy())
            self.assertEqual(out.shape, img.shape, name)
            self.assertEqual(out.dtype, np.uint8, name)

@unittest.skipUnless(CORPUS_READY, "LFW corpus not extracted")
class TestSmallHarnessRun(unittest.TestCase):
    def test_small_subset_produces_metrics(self):
        from server import bioprovider
        if not bioprovider.get_provider("own:sface").available():
            self.skipTest("face models not fetched")
        image_root = B.ensure_corpus()
        pairs = [p for p in B.load_pairs() if p["fold"] == 0]
        subset = pairs[:20] + pairs[300:320]  # 20 same + 20 different, fold 0
        cache = os.path.join(tempfile.mkdtemp(prefix="kyc-bio-test-"), "emb")
        store = B.EmbeddingStore(cache, image_root)
        records, failures = B.pair_scores(subset, store)
        self.assertGreater(len(records), 30, f"only {len(records)} scored, {failures} detection failures")
        s = B.summarise(records, failures, len(subset))
        self.assertIsNotNone(s["eer"])
        # Sanity floor only: SFace on LFW fold-0 pairs is far above
        # this in the full run (benchmarks/biometrics.json).
        self.assertGreaterEqual(s["at_production_threshold"]["accuracy"], 0.8,
                                f"small-subset accuracy {s['at_production_threshold']} below sanity floor")
        self.assertLessEqual(s["detection_failure_rate"], 0.25)

if __name__ == "__main__":
    unittest.main()
