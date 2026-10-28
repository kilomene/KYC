"""Authenticity recalibration (2026-10-28): the verdict rules fitted
to the owner's labelled corpus census. Genuine phone photos pile up
ELA/font points — that alone must never hard-fail a document; a
points fail needs corroboration from >= 2 independent non-edit
signal families. The labelled fake (provenance + portrait) must
still fail, and the screen rule is unchanged."""
import unittest

from server import authenticity as AUTH

NAMES = ("ela", "metadata", "moire", "pixel_grid", "gloss", "gamut",
         "portrait", "font_consistency", "compositing_edges",
         "border_edges", "pattern_presence", "format")


def signals(**strengths):
    return [{"name": n, "strength": strengths.get(n, "none")} for n in NAMES]


class TestCorroborationRule(unittest.TestCase):
    def test_genuine_passport_profile_not_failed(self):
        # census gen_ca_passport: 83 points, edit family + border only
        v = AUTH._verdict_from_signals(signals(
            ela="strong", font_consistency="strong", border_edges="moderate"))
        self.assertEqual(v["findings"]["signal_points"], 83)
        self.assertNotEqual(v["status"], "fail")

    def test_genuine_slip_profile_not_failed(self):
        # census gen_slip_a: 90 points, edit + structure families
        v = AUTH._verdict_from_signals(signals(
            ela="strong", font_consistency="strong", border_edges="strong"))
        self.assertEqual(v["findings"]["signal_points"], 90)
        self.assertNotEqual(v["status"], "fail")

    def test_genuine_pvc_profile_not_failed(self):
        # census gen_pvc_front: 77 points, ONE non-edit family (portrait)
        v = AUTH._verdict_from_signals(signals(
            ela="moderate", portrait="moderate", font_consistency="strong",
            compositing_edges="moderate"))
        self.assertEqual(v["findings"]["signal_points"], 77)
        self.assertNotEqual(v["status"], "fail")
        self.assertEqual(v["findings"]["corroborating_families"], ["portrait"])

    def test_labelled_fake_still_fails(self):
        # census FAKE_ca_id: metadata strong + portrait moderate + font
        v = AUTH._verdict_from_signals(signals(
            metadata="strong", portrait="moderate", font_consistency="strong"))
        self.assertEqual(v["status"], "fail")
        self.assertIn("suspected_recapture_or_edit", v["reason_codes"])
        self.assertIn("altered_text_suspect", v["reason_codes"])
        self.assertTrue(v["findings"]["corroborated"])

    def test_altered_text_annotation_needs_provenance(self):
        # census gen_ca_dl_front: ela moderate + font strong, no metadata
        v = AUTH._verdict_from_signals(signals(
            ela="moderate", font_consistency="strong"))
        self.assertEqual(v["status"], "unclear")
        self.assertNotIn("altered_text_suspect", v["reason_codes"])

    def test_screen_rule_unchanged(self):
        v = AUTH._verdict_from_signals(signals(
            moire="strong", pixel_grid="moderate"))
        self.assertEqual(v["status"], "fail")
        self.assertIn("document_on_screen", v["reason_codes"])

    def test_clean_document_passes(self):
        v = AUTH._verdict_from_signals(signals())
        self.assertEqual(v["status"], "pass")
        self.assertEqual(v["reason_codes"], [])

    def test_two_non_edit_families_below_points_line_not_failed(self):
        # corroboration without the points mass is scrutiny, not a fail
        v = AUTH._verdict_from_signals(signals(
            portrait="moderate", gamut="moderate"))
        self.assertNotEqual(v["status"], "fail")


if __name__ == "__main__":
    unittest.main()
