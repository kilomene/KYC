"""US date-order + AAMVA label anchoring (calibration 2026-10-28).

Root incident: a genuine Wisconsin licence was falsely expired.
Its dates print month-first ('04/20/2031'); parse_date_value only
read day-first, so the EXP line's date was unparseable, the label
steps for both date fields failed ('3DOB' is also a fused token
the old matcher could not anchor), and the zone scoops borrowed
the ISSUE date into both slots. These tests pin the fixes:
validity-driven order swap, locale month-first for US/PH, fused
AAMVA label prefixes, numbered composite labels, and the
cross-field borrowed-date gate."""
import unittest

from server import fieldtemplates as FT


def _d(s, mdy=False):
    d = FT.parse_date_value(s, mdy=mdy)
    return d.isoformat() if d else None


class TestDateOrder(unittest.TestCase):
    def test_day_first_still_default(self):
        self.assertEqual(_d("20/04/2031"), "2031-04-20")
        self.assertEqual(_d("03/04/2023"), "2023-04-03")

    def test_validity_swap_when_month_impossible(self):
        # 'month 20' cannot exist -> the only reading is month-first,
        # even without a locale hint.
        self.assertEqual(_d("04/20/2031"), "2031-04-20")
        self.assertEqual(_d("04/20/1966"), "1966-04-20")
        self.assertEqual(_d("10/31/2027"), "2027-10-31")

    def test_mdy_locale_disambiguates(self):
        self.assertEqual(_d("04/03/2023", mdy=True), "2023-04-03")
        self.assertEqual(_d("04/03/2023", mdy=False), "2023-03-04")

    def test_iso_and_month_names_untouched(self):
        self.assertEqual(_d("2031-04-20"), "2031-04-20")
        self.assertEqual(_d("20 APR 2031"), "2031-04-20")
        self.assertEqual(_d("APRIL 20, 2031"), "2031-04-20")

    def test_impossible_dates_stay_none(self):
        self.assertIsNone(_d("13/13/2020"))
        self.assertIsNone(_d("no date here"))


class TestAamvaLabels(unittest.TestCase):
    def _line(self, toks):
        return [{"text": t} for t in toks]

    def test_fused_numeric_prefix_anchors(self):
        line = self._line(["3DOB", "04/20/1966"])
        self.assertEqual(FT._label_span(line, ["DOB"]), ("DOB", 1))

    def test_fused_prefix_with_subletter(self):
        line = self._line(["4BEXP", "04/20/2031"])
        self.assertEqual(FT._label_span(line, ["EXP"]), ("EXP", 1))

    def test_composite_numbered_labels(self):
        line = self._line(["4b", "EXP", "04/20/2031"])
        self.assertEqual(FT._label_span(line, ["4B EXP", "EXP"]), ("4B EXP", 2))
        line = self._line(["4d", "LIC", "NO", "5361-1606-217A"])
        hit = FT._label_span(line, ["4D LIC NO", "LIC NO"])
        self.assertEqual(hit, ("4D LIC NO", 3))

    def test_prefix_rule_does_not_eat_values(self):
        # A bare value token is never its own label.
        line = self._line(["450", "IB"])
        self.assertIsNone(FT._label_span(line, ["DOB", "EXP"]))


def _word(text, x, y, w=0.05, h=0.02):
    return {"text": text, "box": (x, y, x + w, y + h), "conf": 90, "src": "test"}


class TestWisconsinShape(unittest.TestCase):
    """The incident card's merged-line shape, synthetically: DOB and
    EXP share a row, the ISS date sits on the row above, '3DOB' is
    fused. Extraction must return the printed DOB and EXP — not the
    issue date in both slots."""

    def _words(self):
        ws = []
        # ISS row
        ws += [_word("4a", 0.55, 0.60), _word("ISS", 0.58, 0.60),
               _word("04/03/2023", 0.64, 0.60)]
        # DOB + EXP row (fused 3DOB, separate 4b EXP)
        ws += [_word("3DOB", 0.36, 0.66), _word("04/20/1966", 0.44, 0.66),
               _word("4b", 0.60, 0.66), _word("EXP", 0.63, 0.66),
               _word("04/20/2031", 0.68, 0.66)]
        return ws

    def test_dates_anchor_to_their_own_labels(self):
        r = FT.extract_fields(None, "US", "drivers_license",
                              ocr_text="", words=self._words(), ocr_texts=[])
        f = r["findings"]["fields"]
        self.assertEqual(f["dob"]["value"], "1966-04-20")
        self.assertEqual(f["expiry"]["value"], "2031-04-20")


if __name__ == "__main__":
    unittest.main()
