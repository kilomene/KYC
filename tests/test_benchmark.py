"""Phase 4 WS1 labelled accuracy benchmark — harness smoke test.

Runs a SMALL corpus (2 priority types x 1 identity x clean+blur_light)
through the real extraction pipeline and asserts the harness produces
metrics and that CLEAN-corpus field accuracy meets the calibrated
floor.

CALIBRATION (measured 2026-10-26, this build): the full priority
corpus (12 types x 1 identity, clean) measured exact-match 1.000 /
mean CER 0.000. The floor below is set at 0.90 — below the measured
value, high enough that a real extraction regression (a lost label
anchor, a broken zone) trips it. The full-corpus numbers live in
benchmarks/RESULTS.md; this test guards the harness, not the corpus.
"""
import shutil, tempfile, unittest

TESS = shutil.which("tesseract") is not None

@unittest.skipUnless(TESS, "benchmark needs tesseract")
class TestBenchmarkHarness(unittest.TestCase):
    def test_small_corpus_metrics_and_clean_floor(self):
        from scripts import benchmark_vision as B
        workdir = tempfile.mkdtemp(prefix="kyc-bench-test-")
        results = B.run([("NG", "passport"), ("IN", "aadhaar")], 1,
                        ["clean", "blur_light"], workdir)
        agg = B.aggregate(results)
        self.assertEqual(agg["corpus" if "corpus" in agg else "overall"] is not None, True)
        self.assertEqual(agg["overall"]["documents"], 4)
        self.assertGreater(agg["overall"]["field_values"], 0)
        for t in ("NG/passport", "IN/aadhaar"):
            self.assertIn(t, agg["per_type"])
            self.assertIn("number", agg["per_type"][t]["per_field"])
        clean = agg["clean"]
        self.assertGreaterEqual(clean["exact_match"], 0.90,
                                f"clean exact-match {clean['exact_match']} below calibrated floor 0.90 (measured 1.000 at calibration)")
        self.assertLessEqual(clean["mean_cer"], 0.10)

if __name__ == "__main__":
    unittest.main()
