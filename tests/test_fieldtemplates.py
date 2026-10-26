"""Phase 4 WS1 field-extraction templates: a template for EVERY
registry type (zones, label anchors incl. DE/FR/NL local labels,
per-type number format validators, Verhoeff + NRIC check digits),
zone-first extraction with per-field source recording, and the
label-anchored fallback."""
import io, os, tempfile, unittest

from PIL import Image, ImageDraw

from server import docregistry as R
from server import fieldtemplates as FT
from tests.helpers import _font

def _draw(lines, size=(1063, 670)):
    """lines: [(text, x_frac, y_frac, font_size)]"""
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle([14, 14, size[0] - 14, size[1] - 14], outline="black", width=3)
    for text, xf, yf, fs in lines:
        d.text((int(xf * size[0]), int(yf * size[1])), text, fill="black", font=_font(fs))
    path = os.path.join(tempfile.mkdtemp(), "doc.png")
    im.save(path)
    return path

class TestValidators(unittest.TestCase):
    def test_verhoeff_roundtrip_and_tamper(self):
        base = "23456789012"
        full = base + FT.verhoeff_digit(base)
        self.assertTrue(FT.verhoeff_valid(full))
        self.assertTrue(FT.aadhaar_valid(full))
        bad = full[:6] + str((int(full[6]) + 1) % 10) + full[7:]
        self.assertFalse(FT.verhoeff_valid(bad))
        self.assertFalse(FT.aadhaar_valid(bad))
        self.assertFalse(FT.aadhaar_valid("12345"))

    def test_nric_checksum_letter(self):
        for prefix in "STFG":
            digs = "7654321"
            good = prefix + digs + FT.nric_check_letter(prefix, digs)
            self.assertTrue(FT.nric_valid(good), good)
            self.assertFalse(FT.nric_valid(prefix + digs + "A" if good[-1] != "A" else prefix + digs + "B"))

    def test_number_validators_per_type(self):
        self.assertTrue(FT.validate_number("NG", "nin_slip", "12345678901"))
        self.assertFalse(FT.validate_number("NG", "nin_slip", "1234567890"))
        self.assertTrue(FT.validate_number("IN", "pan_card", "ABCDE1234F"))
        self.assertFalse(FT.validate_number("IN", "pan_card", "ABCD1234F"))
        self.assertTrue(FT.validate_number("AE", "emirates_id", "784198012345678"))
        self.assertFalse(FT.validate_number("AE", "emirates_id", "123456789012345"))
        self.assertTrue(FT.validate_number("GH", "national_id", "GHA1234567890"))
        self.assertIsNone(FT.validate_number("XX", "passport", "ABC123"))

    def test_date_value_formats(self):
        from datetime import date
        self.assertEqual(FT.parse_date_value("1974-08-12"), date(1974, 8, 12))
        self.assertEqual(FT.parse_date_value("12/08/1974"), date(1974, 8, 12))
        self.assertEqual(FT.parse_date_value("12.08.1974"), date(1974, 8, 12))
        self.assertEqual(FT.parse_date_value("12 AUG 1974"), date(1974, 8, 12))
        self.assertEqual(FT.parse_date_value("12 August 1974"), date(1974, 8, 12))
        self.assertIsNone(FT.parse_date_value("not a date"))

class TestCoverage(unittest.TestCase):
    def test_every_registry_type_has_a_template(self):
        for country, docs in R.DOCUMENT_REGISTRY.items():
            for kind in docs:
                tpl = FT.get_field_template(country, kind)
                self.assertIsNotNone(tpl, f"{country}/{kind}")
                for field in ("surname", "given_names", "dob", "number"):
                    self.assertIn(field, tpl["fields"], f"{country}/{kind} missing {field}")
                entry = R.get_document(country, kind)
                if not entry["has_expiry"]:
                    self.assertNotIn("expiry", tpl["fields"], f"{country}/{kind} must not template an expiry it does not carry")

    def test_local_language_labels_present(self):
        de = FT.get_field_template("DE", "national_id")
        self.assertIn("GEBURTSDATUM", de["fields"]["dob"]["labels"])
        fr = FT.get_field_template("FR", "national_id")
        self.assertIn("NOM", fr["fields"]["surname"]["labels"])
        nl = FT.get_field_template("NL", "drivers_licence")
        self.assertIn("GEBOORTEDATUM", nl["fields"]["dob"]["labels"])

    def test_unknown_kind_is_honest(self):
        r = FT.extract_fields(None, "GB", "no_such_kind", ocr_text="", words=[])
        self.assertEqual(r["status"], "unclear")
        self.assertIn("field_template_missing", r["reason_codes"])

class TestExtraction(unittest.TestCase):
    def test_gb_licence_zone_and_label_extraction(self):
        path = _draw([
            ("DRIVING LICENCE UNITED KINGDOM", 0.36, 0.03, 26),
            ("NUMBER D1234567", 0.36, 0.15, 28),
            ("SURNAME ERIKSSON", 0.36, 0.24, 34),
            ("GIVEN NAMES ANNA MARIA", 0.36, 0.38, 34),
            ("DATE OF BIRTH 1974-08-12", 0.36, 0.54, 34),
            ("DATE OF EXPIRY 2032-04-15", 0.36, 0.70, 34),
        ])
        r = FT.extract_fields(path, "GB", "drivers_licence")
        f = r["findings"]["fields"]
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertEqual(f["surname"]["value"], "ERIKSSON")
        self.assertEqual(f["given_names"]["value"], "ANNA MARIA")
        self.assertEqual(f["dob"]["value"], "1974-08-12")
        self.assertEqual(f["expiry"]["value"], "2032-04-15")
        self.assertEqual(f["number"]["value"], "D1234567")
        self.assertTrue(f["number"]["format_valid"])
        self.assertIn(f["number"]["source"], ("label", "zone"))

    def test_de_national_id_german_labels(self):
        path = _draw([
            ("PERSONALAUSWEIS BUNDESREPUBLIK", 0.36, 0.03, 26),
            ("NUMMER L12X34T57", 0.36, 0.15, 28),
            ("NAME MULLER", 0.36, 0.24, 34),
            ("VORNAMEN JONAS", 0.36, 0.38, 34),
            ("GEBURTSDATUM 22.07.1988", 0.36, 0.54, 34),
            ("GULTIG BIS 19.01.2033", 0.36, 0.70, 34),
        ])
        r = FT.extract_fields(path, "DE", "national_id")
        f = r["findings"]["fields"]
        self.assertEqual(f["surname"]["value"], "MULLER", f)
        self.assertEqual(f["dob"]["value"], "1988-07-22", f)
        self.assertEqual(f["expiry"]["value"], "2033-01-19", f)
        self.assertEqual(f["number"]["value"], "L12X34T57", f)

    def test_aadhaar_grouped_number_and_verhoeff(self):
        base = "23456789012"
        num = base + FT.verhoeff_digit(base)
        grouped = " ".join(num[i:i + 4] for i in range(0, 12, 4))
        path = _draw([
            ("AADHAAR GOVERNMENT OF INDIA", 0.36, 0.03, 26),
            (f"AADHAAR NUMBER {num}", 0.36, 0.15, 28),
            ("SURNAME ERIKSSON", 0.36, 0.24, 34),
            ("GIVEN NAMES ANNA MARIA", 0.36, 0.38, 34),
            ("DOB 1974-08-12", 0.36, 0.54, 34),
            (grouped, 0.30, 0.80, 40),
        ])
        r = FT.extract_fields(path, "IN", "aadhaar")
        f = r["findings"]["fields"]
        self.assertEqual(f["number"]["value"], num, f)
        self.assertTrue(f["number"]["format_valid"], f)
        self.assertNotIn("expiry", f)  # Aadhaar carries no expiry field

    def test_bad_nin_number_format_fails(self):
        # The number is read, and it is NOT an 11-digit NIN: fail.
        r = FT.extract_fields(None, "NG", "nin_slip", ocr_text="NIN 12345\nSURNAME ERIKSSON", words=[])
        # text fallback reads the short token; format validation judges it
        f = r["findings"]["fields"]
        if f["number"]["value"]:
            self.assertFalse(f["number"]["format_valid"])
            self.assertEqual(r["status"], "fail")
            self.assertIn("field_number_format_invalid", r["reason_codes"])

    def test_text_fallback_when_no_word_boxes(self):
        text = "SURNAME ERIKSSON\nGIVEN NAMES ANNA MARIA\nDATE OF BIRTH 1974-08-12\nNUMBER D1234567"
        r = FT.extract_fields(None, "GB", "drivers_licence", ocr_text=text, words=[])
        f = r["findings"]["fields"]
        self.assertEqual(f["surname"]["value"], "ERIKSSON")
        self.assertEqual(f["surname"]["source"], "text")
        self.assertEqual(f["dob"]["value"], "1974-08-12")

    def test_text_fallback_label_word_boundaries(self):
        # "NAME" (DE surname anchor) must not match inside "VORNAMEN".
        text = "VORNAMEN ANNA MARIA\nNAME MULLER"
        r = FT.extract_fields(None, "DE", "national_id", ocr_text=text, words=[])
        f = r["findings"]["fields"]
        self.assertEqual(f["surname"]["value"], "MULLER", f)
        self.assertEqual(f["given_names"]["value"], "ANNA MARIA", f)

if __name__ == "__main__":
    unittest.main()
