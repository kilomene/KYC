"""Unified dual-engine reader (server/ocr2.py + vision stream
merge): the merge and arbitration rules are pure functions over
canned streams/extractions — no Paddle runtime needed, so the
suite stays deterministic. The engine gate is fail-closed: without
KYC_OCR2=on every read returns None and the platform is exactly
the single-engine build."""
import os
import unittest

from server import ocr2, vision


def W(text, conf, box, src=None):
    w = {"text": text, "conf": conf, "box": box}
    if src:
        w["src"] = src
    return w


class TestEnabledGate(unittest.TestCase):
    def test_default_off(self):
        os.environ.pop("KYC_OCR2", None)
        self.assertFalse(ocr2.enabled())
        self.assertIsNone(ocr2.read_words("/nonexistent.png"))
        self.assertIsNone(ocr2.read_words_for_image_file("/nonexistent.png"))

    def test_explicit_off(self):
        os.environ["KYC_OCR2"] = "off"
        try:
            self.assertFalse(ocr2.enabled())
        finally:
            os.environ.pop("KYC_OCR2", None)


class TestMergeStreams(unittest.TestCase):
    def test_same_token_same_place_merges_with_both_sources(self):
        t = [W("AYANSIPE", 80, (0.10, 0.10, 0.30, 0.16))]
        p = [W("AYANSIPE", 95, (0.11, 0.10, 0.31, 0.16), "paddle")]
        m = vision.merge_word_streams(t, p)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["src"], "tesseract+paddle")
        self.assertEqual(m[0]["conf"], 95)

    def test_rival_token_higher_confidence_holds_the_place(self):
        t = [W("ZENAS", 60, (0.10, 0.10, 0.30, 0.16))]
        p = [W("ZEN4S", 92, (0.10, 0.10, 0.30, 0.16), "paddle")]
        m = vision.merge_word_streams(t, p)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["text"], "ZEN4S")

    def test_distinct_places_both_pass_through(self):
        t = [W("SURNAME", 90, (0.05, 0.10, 0.20, 0.15))]
        p = [W("AYANSIPE", 97, (0.25, 0.10, 0.45, 0.15), "paddle")]
        m = vision.merge_word_streams(t, p)
        self.assertEqual(len(m), 2)
        self.assertEqual({w["text"] for w in m}, {"SURNAME", "AYANSIPE"})

    def test_inputs_not_mutated(self):
        t = [W("ABC", 50, (0.0, 0.0, 0.1, 0.1))]
        p = [W("ABC", 90, (0.0, 0.0, 0.1, 0.1), "paddle")]
        vision.merge_word_streams(t, p)
        self.assertNotIn("src", t[0])

    def test_empty_paddle_returns_tesseract_stream(self):
        t = [W("ABC", 50, (0.0, 0.0, 0.1, 0.1))]
        m = vision.merge_word_streams(t, [])
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["src"], "tesseract")


class TestArbitrate(unittest.TestCase):
    def test_union_adopts_single_engine_find(self):
        adopted, dis = ocr2.arbitrate(
            {"surname": "AYANSIPE"},
            {"surname": "AYANSIPE", "given_names": "ZENAS"},
            {"surname": "AYANSIPE"})
        self.assertEqual(adopted.get("given_names"), ("ZENAS", "tesseract"))
        self.assertEqual(dis, [])

    def test_both_engines_agree_adopted(self):
        adopted, _ = ocr2.arbitrate({}, {"number": "12345678901"},
                                    {"number": "1234 567 8901"})
        self.assertEqual(adopted.get("number"), ("12345678901", "both_engines"))

    def test_number_conflict_adopts_neither(self):
        adopted, dis = ocr2.arbitrate(
            {}, {"number": "11111111111"}, {"number": "22222222222"})
        self.assertNotIn("number", adopted)
        self.assertEqual(len(dis), 1)
        self.assertEqual(dis[0]["field"], "number")

    def test_merged_value_stands_over_conflict(self):
        adopted, dis = ocr2.arbitrate(
            {"number": "12345678901"}, {"number": "11111111111"},
            {"number": "22222222222"})
        self.assertNotIn("number", adopted)  # merged already holds it
        self.assertEqual(len(dis), 1)  # conflict still surfaced

    def test_superset_witness_repairs_partial_given_names(self):
        # Owner session 16 (2026-10-29): the unified read adopted the
        # middle name alone ('OLATUNDE', from the text scan) while the
        # Tesseract witness held the full two-cell name. The strict
        # superset witness is adopted over the fragment.
        adopted, dis = ocr2.arbitrate(
            {"surname": "AYANSIPE", "given_names": "OLATUNDE"},
            {"surname": "AYANSIPE", "given_names": "ZENAS OLATUNDE"},
            {"surname": "AYANSIPE", "given_names": "NAMEZENAS NAMEOLATUNDE SAK"})
        self.assertEqual(adopted.get("given_names"),
                         ("ZENAS OLATUNDE", "tesseract_superset"))
        self.assertTrue(any(d.get("resolution") == "superset_witness_adopted"
                            for d in dis))

    def test_subset_witness_does_not_shrink_merged(self):
        # The merged read legitimately carries MORE than one engine
        # saw; a subset witness must not shrink it.
        adopted, _ = ocr2.arbitrate(
            {"surname": "AYANSIPE", "given_names": "ZENAS OLATUNDE SSR SAK"},
            {"surname": "AYANSIPE", "given_names": "ZENAS OLATUNDE"},
            {"surname": "AYANSIPE", "given_names": "ZENAS OLATUNDE SSR SAK"})
        self.assertNotIn("given_names", adopted)

    def test_superset_must_pass_plausibility(self):
        # A superset built from document furniture is not a name.
        adopted, _ = ocr2.arbitrate(
            {"given_names": "OLATUNDE"},
            {"given_names": "FEDERAL REPUBLIC OLATUNDE"},
            {})
        self.assertNotIn("given_names", adopted)

    def test_extraction_fields_shape(self):
        ext = {"findings": {"fields": {
            "surname": {"value": "AYANSIPE", "source": "label"},
            "dob": {"value": None, "source": "label"}}}}
        self.assertEqual(ocr2.extraction_fields(ext), {"surname": "AYANSIPE"})
        self.assertEqual(ocr2.extraction_fields(None), {})
        self.assertEqual(ocr2.extraction_fields({}), {})

    def test_triad(self):
        self.assertTrue(ocr2.triad_complete(
            {"surname": "A", "given_names": "B", "number": "1"}))
        self.assertFalse(ocr2.triad_complete({"surname": "A"}))


if __name__ == "__main__":
    unittest.main()
