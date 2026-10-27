"""Session-5 diagnosis fixes (2026-10-26): five defects found by
bit-for-bit reproduction on a real NG NIN slip capture, each pinned
here with SYNTHETIC fixtures only (invented values throughout — no
owner data in this file).

  1. framing: the segmentation quad measured aspect ~1.40 against the
     document's true ~2.20; the warp stretched the slip ~1.57x and
     downstream checks consumed the distortion -> quad quality gate.
  2. templates: the classification number-zone rule needed ONE >=5
     alnum token, but a stretched/shattered digit line reads as 1-3
     char tokens -> zone assembly against the type's own format.
  3. fieldtemplates: a 4-char alphabetic header token after the
     number anchor was adopted by the invalid-fallback and converted
     not-found into a hard FAIL; extraction also judged only the
     winning OCR pass -> fallback discipline + union of passes.
  4. identity: the read-back called that same broken read 'complete'
     (presence-only, format-invalid number adopted) -> format-valid
     number + both names required where the template carries both.
  5. engine: face_match had no applicability path (portrait-less
     types auto-rejected forever) and its template source disagreed
     with itself on nin_slip -> template-driven applicability, full
     template as the single source of truth.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from server import framing as F
from server import templates as T
from server import fieldtemplates as FT
from server import identity as I
from server import engine as E
from server import docregistry as R


# ----------------------------------------------------------------------
# Fix 1 — framing quad quality gate
# ----------------------------------------------------------------------

def _distorted_scene():
    """A wide sheet (1100x500, aspect 2.20) with a hard printed border
    and print texture, photographed over a bright desk surface that
    fades softly below it. Blurred-luminance segmentation merges
    sheet + desk glow into one taller blob (aspect ~1.45 — the
    measured distortion class); the edge family traces the sheet's
    printed border at the true aspect."""
    import cv2
    img = np.full((1100, 1240, 3), 42, np.uint8)
    sx, sy, sw, sh = 70, 60, 1100, 500
    yy = np.mgrid[0:1100, 0:1240][0].astype(np.float32)
    d = np.clip(yy - (sy + sh), 0, None)
    desk = (42 + (198 - 42) * np.exp(-((d / 430.0) ** 2))).astype(np.uint8)
    band = yy >= (sy + sh)
    img[band] = np.maximum(img[band], desk[band][:, None])
    cv2.rectangle(img, (sx, sy), (sx + sw, sy + sh), (208, 208, 208), -1)
    cv2.rectangle(img, (sx + 12, sy + 12), (sx + sw - 12, sy + sh - 12), (60, 60, 60), 4)
    rng = np.random.default_rng(3)
    for row in range(6):
        y = sy + 50 + row * 70
        x = sx + 40
        while x < sx + 720:
            ln = int(rng.integers(30, 110))
            cv2.rectangle(img, (x, y), (min(x + ln, sx + 730), y + 8), (92, 92, 92), -1)
            x += ln + int(rng.integers(12, 30))
    cv2.rectangle(img, (sx + 830, sy + 60), (sx + 1010, sy + 300), (150, 150, 150), -1)
    cv2.ellipse(img, (sx + 920, sy + 160), (42, 58), 0, 0, 360, (95, 95, 95), -1)
    return img


class TestAspectConflictResolution(unittest.TestCase):
    def test_midrange_quad_wins(self):
        # range 1.2-2.8 -> central band 1.6-2.4: edge 2.25 is
        # mid-range, segmentation 1.446 is outer-band.
        self.assertEqual(F._resolve_aspect_conflict(2.25, 1.446, (1.2, 2.8)),
                         ("edges", "midrange_preferred"))
        self.assertEqual(F._resolve_aspect_conflict(1.5, 2.2, (1.2, 2.8)),
                         ("segmentation", "midrange_preferred"))

    def test_in_range_beats_out_of_range(self):
        self.assertEqual(F._resolve_aspect_conflict(3.5, 1.5, (1.2, 2.8)),
                         ("segmentation", "in_range_preferred"))

    def test_no_range_prefers_edge(self):
        self.assertEqual(F._resolve_aspect_conflict(2.25, 1.446, None),
                         ("edges", "edge_preferred"))

    def test_equally_placed_is_ambiguous(self):
        group, why = F._resolve_aspect_conflict(1.7, 2.3, (1.2, 2.8))   # both mid-range
        self.assertIsNone(group)
        self.assertEqual(why, "ambiguous_both_in_range")
        group, why = F._resolve_aspect_conflict(3.5, 3.1, (1.2, 2.8))   # both out of range
        self.assertIsNone(group)
        self.assertEqual(why, "ambiguous_neither_in_range")


class TestFramingGateOnDistortedScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cv2
        cls.img = _distorted_scene()
        cls.png = cv2.imencode(".png", cls.img)[1].tobytes()

    def test_gate_prefers_edge_quad_with_range(self):
        a = F.analyse_image(self.img, (1.2, 2.8))
        self.assertIsNotNone(a["aspect_conflict"], a)
        self.assertAlmostEqual(a["aspect_conflict"]["segmentation_aspect"], 1.446, delta=0.15)
        self.assertEqual(a["aspect_conflict"]["resolution"], "midrange_preferred")
        # the analysis (and therefore the warp) carries the TRUE aspect
        self.assertAlmostEqual(a["aspect"], 2.25, delta=0.1)
        self.assertTrue(a["accepted"])

    def test_gate_prefers_edge_quad_without_range(self):
        a = F.analyse_image(self.img)
        self.assertIsNotNone(a["aspect_conflict"], a)
        self.assertEqual(a["aspect_conflict"]["resolution"], "edge_preferred")
        self.assertAlmostEqual(a["aspect"], 2.25, delta=0.1)

    def test_check_passes_on_true_geometry(self):
        r = F.check_document_framing(data=self.png, expected_aspect_range=(1.2, 2.8))
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertAlmostEqual(r["findings"]["aspect"], 2.25, delta=0.1)
        self.assertTrue(r["findings"]["warp_applied"])
        self.assertIsNotNone(r["findings"]["aspect_conflict"])

    def test_unresolvable_conflict_is_unclear_rescan(self):
        # A claimed range so wide that BOTH shapes sit mid-range:
        # the gate cannot prefer either -> rescan, never a warped guess.
        r = F.check_document_framing(data=self.png, expected_aspect_range=(0.9, 2.9))
        self.assertEqual(r["status"], "unclear", r["findings"])
        self.assertIn("document_aspect_ambiguous", r["reason_codes"])
        self.assertFalse(r["findings"]["quad_found"])


# ----------------------------------------------------------------------
# Fix 2 — classification number-zone assembly
# ----------------------------------------------------------------------

def _word(text, x0, y0, x1, y1):
    return {"text": text, "conf": 90, "box": (x0, y0, x1, y1)}


class TestNumberZoneAssembly(unittest.TestCase):
    def _classify(self, words):
        import tempfile
        from PIL import Image
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as tf:
            Image.new("RGB", (1240, 620), "white").save(tf, format="PNG")
            path = tf.name
        try:
            return T.check_classification(path, "NG", "nin_slip",
                                          ocr_text="NATIONAL IDENTITY NIN",
                                          words=words)
        finally:
            os.unlink(path)

    def test_shattered_digit_line_assembles(self):
        # The NIN zone is (0.02, 0.16, 0.46, 0.40). Three fragments,
        # each too short for the single-token rule (< 5 alnum), on one
        # line with print-grouping gaps.
        words = [_word("1234", 0.05, 0.22, 0.13, 0.30),
                 _word("5678", 0.15, 0.22, 0.23, 0.30),
                 _word("901", 0.25, 0.22, 0.30, 0.30)]
        r = self._classify(words)
        zone = r["findings"]["elements"]["number_zone"]
        self.assertTrue(zone["read"], r["findings"])
        self.assertEqual(zone["assembled"], "12345678901")

    def test_wrong_shape_assembly_does_not_count(self):
        words = [_word("1234", 0.05, 0.22, 0.13, 0.30),
                 _word("5678", 0.15, 0.22, 0.23, 0.30)]   # 8 digits, not an 11-digit NIN
        r = self._classify(words)
        zone = r["findings"]["elements"]["number_zone"]
        self.assertFalse(zone["read"], r["findings"])
        self.assertNotIn("assembled", zone)

    def test_single_token_path_unchanged(self):
        words = [_word("12345678901", 0.05, 0.22, 0.30, 0.30)]
        r = self._classify(words)
        zone = r["findings"]["elements"]["number_zone"]
        self.assertTrue(zone["read"], r["findings"])
        self.assertEqual(zone["tokens"], ["12345678901"])


# ----------------------------------------------------------------------
# Fix 3 — extraction fallback discipline + union of OCR passes
# ----------------------------------------------------------------------

class TestFallbackDiscipline(unittest.TestCase):
    def test_header_token_after_anchor_is_not_found_not_fail(self):
        # The slip's own header contains the number label; the word
        # after the title is a header word, not a misread number.
        text = "National Identification Number Slip\nSURNAME SAMPLETON\nFIRST NAME EXAMPLE"
        r = FT.extract_fields(None, "NG", "nin_slip", ocr_text=text, words=[])
        f = r["findings"]["fields"]
        self.assertIsNone(f["number"]["value"], f)
        self.assertNotEqual(r["status"], "fail", r)
        self.assertNotIn("field_number_format_invalid", r["reason_codes"])

    def test_header_token_in_word_boxes_is_discarded(self):
        words = [_word("NATIONAL", 0.30, 0.06, 0.44, 0.11),
                 _word("IDENTIFICATION", 0.45, 0.06, 0.66, 0.11),
                 _word("NUMBER", 0.67, 0.06, 0.76, 0.11),
                 _word("SLIP", 0.77, 0.06, 0.83, 0.11),
                 _word("SURNAME", 0.36, 0.32, 0.46, 0.37),
                 _word("SAMPLETON", 0.50, 0.32, 0.63, 0.37)]
        r = FT.extract_fields(None, "NG", "nin_slip", ocr_text="", words=words)
        f = r["findings"]["fields"]
        self.assertIsNone(f["number"]["value"], f)
        self.assertNotEqual(r["status"], "fail", r)
        self.assertEqual(f["surname"]["value"], "SAMPLETON", f)

    def test_digit_bearing_bad_number_still_fails(self):
        # A short DIGIT string after the anchor IS the number, read
        # and wrong: the format FAIL must still surface.
        r = FT.extract_fields(None, "NG", "nin_slip",
                              ocr_text="NIN 12345\nSURNAME SAMPLETON", words=[])
        f = r["findings"]["fields"]
        self.assertEqual(f["number"]["value"], "12345", f)
        self.assertIs(f["number"]["format_valid"], False)
        self.assertEqual(r["status"], "fail")
        self.assertIn("field_number_format_invalid", r["reason_codes"])

    def test_plausibility_boundaries(self):
        self.assertTrue(FT._plausible_number_fallback("12345"))       # digit-bearing
        self.assertTrue(FT._plausible_number_fallback("D1234567"))    # digit-bearing
        self.assertFalse(FT._plausible_number_fallback("SLIP"))       # header word
        self.assertFalse(FT._plausible_number_fallback("NUMBER"))     # label word itself
        self.assertTrue(FT._plausible_number_fallback("IBO5SB"))      # fully confusable-mappable, len 6


class TestUnionOfPasses(unittest.TestCase):
    def test_fields_read_from_non_winning_pass(self):
        # The winning pass read the surname only; a second pass read
        # the given names and the number. Extraction must judge the
        # union, not the winner alone.
        r = FT.extract_fields(None, "NG", "nin_slip",
                              ocr_text="SURNAME SAMPLETON",
                              ocr_texts=["FIRST NAME EXAMPLE\nNIN 12345678901"],
                              words=[])
        f = r["findings"]["fields"]
        self.assertEqual(f["surname"]["value"], "SAMPLETON", f)
        self.assertIn("EXAMPLE", f["given_names"]["value"] or "", f)
        self.assertEqual(f["number"]["value"], "12345678901", f)
        self.assertIs(f["number"]["format_valid"], True)
        self.assertEqual(r["status"], "pass", r)


# ----------------------------------------------------------------------
# Fix 4 — read-back contract
# ----------------------------------------------------------------------

def _fields(**kw):
    base = {"surname": {"value": None, "source": None},
            "given_names": {"value": None, "source": None},
            "dob": {"value": None, "source": None},
            "expiry": {"value": None, "source": None},
            "number": {"value": None, "source": None, "format_valid": None}}
    base.update(kw)
    return base


class TestReadBackContract(unittest.TestCase):
    def setUp(self):
        self.slip = R.get_document("NG", "nin_slip")   # no MRZ, prints no DOB

    def test_format_invalid_number_is_reported_missing(self):
        fields = _fields(surname={"value": "SAMPLETON", "source": "label"},
                         given_names={"value": "EXAMPLE", "source": "label"},
                         number={"value": "SLIP", "source": "label", "format_valid": False})
        ident = I.derive_document_identity(fields, None, {})
        self.assertEqual(ident["number"], "SLIP")          # adopted, but stamped
        self.assertIs(ident["number_format_valid"], False)
        self.assertIn("number", I.missing_read_fields(ident, self.slip))

    def test_one_name_of_two_carried_is_reported_missing(self):
        fields = _fields(surname={"value": "SAMPLETON", "source": "zone"},
                         number={"value": "12345678901", "source": "label", "format_valid": True})
        ident = I.derive_document_identity(fields, None, {})
        self.assertIn("surname", ident["name_fields_carried"])
        self.assertIn("given_names", ident["name_fields_carried"])
        self.assertIn("name", I.missing_read_fields(ident, self.slip))

    def test_complete_read_stays_complete(self):
        fields = _fields(surname={"value": "SAMPLETON", "source": "label"},
                         given_names={"value": "EXAMPLE", "source": "label"},
                         number={"value": "12345678901", "source": "label", "format_valid": True})
        ident = I.derive_document_identity(fields, None, {})
        self.assertIs(ident["number_format_valid"], True)
        self.assertEqual(I.missing_read_fields(ident, self.slip), [])

    def test_mrz_number_is_format_valid_by_construction(self):
        mrz = {"valid": True, "document_number": "L898902C3", "dob_yymmdd": "740812",
               "expiry_yymmdd": "320415",
               "names": {"surname": "SAMPLETON", "given_names": "EXAMPLE"}}
        ident = I.derive_document_identity(_fields(), mrz, {})
        self.assertIs(ident["number_format_valid"], True)
        self.assertEqual(ident["name_fields_carried"], ["surname", "given_names"])

    def test_legacy_dict_without_evidence_keeps_presence_rule(self):
        ident = {"first_name": "EXAMPLE", "last_name": None,
                 "dob": None, "number": "12345678901", "expiry": None}
        self.assertEqual(I.missing_read_fields(ident, self.slip), [])


# ----------------------------------------------------------------------
# Fix 5 — face_match applicability (engine side)
# ----------------------------------------------------------------------

def _all_pass_except(**over):
    res = {t: {"status": "pass", "reason_codes": []} for t in E.required_for(2)}
    res.update(over)
    return res


class TestFaceMatchApplicability(unittest.TestCase):
    def test_nin_slip_full_template_is_source_of_truth(self):
        # The FULL NG/nin_slip template (real layout: the slip prints
        # a portrait) is what the engine consults. get_template's
        # COARSE builder encodes the opposite rule for the same kind
        # (`portrait_expected: kind != "nin_slip"`) — staged here with
        # a temporary registry entry for a country that has the kind
        # but no full template, which is the only way the coarse
        # builder ever speaks. The disagreement is latent today (every
        # registry type resolves full/generic) and must not leak into
        # the decision path for NG/nin_slip.
        R.DOCUMENT_REGISTRY.setdefault("ZZ", {})["nin_slip"] = {
            "label": "NIN slip", "sides": 1, "has_expiry": False, "mrz": False, "aspect": 2.0}
        try:
            coarse_tpl, level = T.get_template("ZZ", "nin_slip")
            self.assertEqual(level, "coarse")
            self.assertFalse(coarse_tpl["portrait_expected"])   # the disagreement itself
            self.assertTrue(E.face_match_applicable("NG", "nin_slip"))
        finally:
            del R.DOCUMENT_REGISTRY["ZZ"]

    def test_portrait_less_template_is_not_applicable(self):
        self.assertFalse(E.face_match_applicable(template={"portrait_expected": False}))
        self.assertTrue(E.face_match_applicable(template={"portrait_expected": True}))
        self.assertTrue(E.face_match_applicable("XX", "no_such_type"))   # fail closed

    def test_not_applicable_face_match_neither_fails_nor_blocks(self):
        res = _all_pass_except(face_match={"status": "not_applicable", "reason_codes": []})
        outcome, reasons = E.decide(2, res)
        self.assertEqual(outcome, "approved", reasons)

    def test_unclear_face_match_still_rejects(self):
        res = _all_pass_except(face_match={"status": "unclear",
                                           "reason_codes": ["no_face_in_document"]})
        outcome, reasons = E.decide(2, res)
        self.assertEqual(outcome, "rejected")
        self.assertIn("face_match_not_pass", reasons)

    def test_biometric_evidence_treats_not_applicable_as_satisfied(self):
        cf = {"track_label": "live_track"}   # device_signals leg present + passing
        res = _all_pass_except(face_match={"status": "not_applicable", "reason_codes": []})
        ev = E.biometric_evidence(res, cf)
        self.assertEqual(ev["components"]["face_match"], "not_applicable")
        self.assertTrue(ev["all_passing"], ev)
        # ...while an ABSENT face match (never recorded) still blocks
        res2 = _all_pass_except()
        del res2["face_match"]
        self.assertFalse(E.biometric_evidence(res2, cf)["all_passing"])


class TestWeakGeometryGate(unittest.TestCase):
    """Decision-grade geometry (owner session-5, second act): an
    accepted quad in the outer quartile of the claimed type's aspect
    range on weak border evidence is a guess, not a measurement —
    framing must answer unclear/document_geometry_weak (a rescan),
    never pass a warp that bakes the distortion in."""

    def _run_with(self, aspect, border):
        import cv2
        from server import framing as F
        img = _distorted_scene()
        buf = cv2.imencode(".png", img)[1].tobytes()
        real = F.analyse_image
        def fake(im, rng=None):
            a = real(im, rng)
            if a and a.get("quad") is not None:
                a = dict(a); a["aspect"] = aspect; a["border_support"] = border
            return a
        F.analyse_image = fake
        try:
            return F.check_document_framing(data=buf,
                                            expected_aspect_range=(1.2, 2.8))
        finally:
            F.analyse_image = real

    def test_outer_band_weak_border_is_unclear(self):
        res = self._run_with(1.40, 0.30)
        self.assertTrue(res["findings"].get("quad_found"), res["findings"])
        self.assertEqual(res["status"], "unclear")
        self.assertEqual(res["reason_codes"], ["document_geometry_weak"])

    def test_mid_range_weak_border_still_passes(self):
        res = self._run_with(2.20, 0.30)
        self.assertTrue(res["findings"].get("quad_found"), res["findings"])
        self.assertEqual(res["status"], "pass")


if __name__ == "__main__":
    unittest.main()
