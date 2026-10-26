"""Vision OCR layer (2026-10-26): multi-pass reading, MRZ<->VIZ
cross-validation, machine-readable code decoding. All fail-closed:
decoded/internal data must AGREE with the printed document or it
counts against it; absence is recorded, never faked."""
import tempfile, unittest

from helpers import id_image_bytes
from server import checks as C
from server import vision as V

def _tmp(data, suffix=".png"):
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(data); f.close()
    return f.name

class TestMultiPassOCR(unittest.TestCase):
    def test_reads_fixture_with_pass_metadata(self):
        r = V.read_document_text(_tmp(id_image_bytes()))
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual(r["findings"]["engine"], "vision-multipass")
        names = [p["name"] for p in r["findings"]["passes"]]
        self.assertIn("plain", names); self.assertIn("adaptive", names); self.assertIn("mrz_band", names)
        self.assertIn("ERIKSSON", r["text"])

    def test_band_pass_recovers_a_valid_mrz(self):
        # Full-page passes do NOT segment the drawn MRZ (measured); the
        # dedicated band pass must recover it, check-digit valid.
        r = V.read_document_text(_tmp(id_image_bytes()))
        parsed = C.parse_mrz(r["text"])
        self.assertIsNotNone(parsed, r["text"])
        self.assertTrue(parsed["valid"], parsed)
        self.assertEqual(C.check_mrz(r["text"])["status"], "pass")

    def test_corrupt_mrz_stays_visible_and_fails(self):
        r = V.read_document_text(_tmp(id_image_bytes(corrupt_mrz=True)))
        parsed = C.parse_mrz(r["text"])
        self.assertIsNotNone(parsed, "a corrupted MRZ must be surfaced, not dropped")
        self.assertFalse(parsed["valid"])
        self.assertEqual(C.check_mrz(r["text"])["status"], "fail")

class TestMrzVizCrossCheck(unittest.TestCase):
    def _parsed(self):
        l1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
        from helpers import _mrz_line2
        return C.parse_mrz(l1 + "\n" + _mrz_line2("1974-08-12", "2032-04-15"))

    def test_agreeing_zones_pass(self):
        text = ("PASSPORT\nANNA ERIKSSON\nDOB 1974-08-12\nEXPIRY 2032-04-15\n"
                "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n")
        from helpers import _mrz_line2
        text += _mrz_line2("1974-08-12", "2032-04-15")
        r = V.cross_check_mrz_viz(text, self._parsed())
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual(r["findings"]["mismatches"], [])

    def test_labelled_viz_expiry_disagreement_fails(self):
        # The visual zone claims a different expiry than the MRZ: a
        # forged/altered document that fooled only one zone.
        from helpers import _mrz_line2
        text = ("PASSPORT\nANNA ERIKSSON\nDOB 1974-08-12\nEXPIRY 2040-01-01\n"
                "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n" + _mrz_line2("1974-08-12", "2032-04-15"))
        r = V.cross_check_mrz_viz(text, self._parsed())
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("mrz_viz_mismatch", r["reason_codes"])
        self.assertIn("expiry", r["findings"]["mismatches"])

    def test_no_comparable_viz_data_is_unclear_not_pass(self):
        from helpers import _mrz_line2
        text = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n" + _mrz_line2("1974-08-12", "2032-04-15")
        r = V.cross_check_mrz_viz(text, self._parsed())
        self.assertEqual(r["status"], "unclear", r)
        self.assertIn("mrz_viz_insufficient_data", r["reason_codes"])

class TestCodeDecode(unittest.TestCase):
    def test_no_code_on_plain_card_is_unclear_honest(self):
        r = V.decode_codes(_tmp(id_image_bytes()), None, {"doc_number": "L898902C3"})
        self.assertEqual(r["status"], "unclear", r)
        self.assertIn("no_machine_code_found", r["reason_codes"])
        self.assertFalse(r["findings"]["found_any"])

    def test_aamva_agreement_and_mismatch(self):
        # A licence-back PDF417 payload (via a stubbed decoder): fields
        # agreeing with the document pass; a different licence number
        # is a material mismatch — decoded data is evidence, not truth.
        payload = "DAQD1234567\nDCSERIKSSON\nDACANNA\nDBB08121974\nDBA04152032\n"
        orig = V._decode_barcodes
        V._decode_barcodes = lambda p: [{"format": "PDF417", "text": payload}]
        try:
            ok = V.decode_codes(_tmp(id_image_bytes()), None,
                                {"doc_number": "D1234567", "doc_dob": "1974-08-12",
                                 "doc_expiry": "2032-04-15", "doc_last_name": "ERIKSSON"})
            self.assertEqual(ok["status"], "pass", ok)
            self.assertTrue(ok["findings"]["found_any"])
            self.assertEqual(ok["findings"]["aamva"]["number"], "D1234567")
            bad = V.decode_codes(_tmp(id_image_bytes()), None,
                                 {"doc_number": "X9999999", "doc_dob": "1974-08-12",
                                  "doc_expiry": "2032-04-15", "doc_last_name": "ERIKSSON"})
            self.assertEqual(bad["status"], "fail", bad)
            self.assertIn("code_decode_mismatch", bad["reason_codes"])
            self.assertIn("number", bad["findings"]["mismatches"])
        finally:
            V._decode_barcodes = orig

    def test_real_qr_roundtrip_when_a_writer_exists(self):
        # zxing-cpp ships a writer; if unavailable here, the OpenCV QR
        # path is covered by the no-code test above and this skips.
        try:
            import numpy as np
            import zxingcpp
            from PIL import Image
            bc = zxingcpp.create_barcode("NIN:12345678901", zxingcpp.BarcodeFormat.QRCode)
            arr = np.asarray(zxingcpp.write_barcode_to_image(bc, scale=8))
            path = _tmp(b"", suffix=".png")
            Image.fromarray(arr).convert("RGB").save(path)
        except Exception as e:
            self.skipTest(f"no barcode writer available: {e}")
        r = V.decode_codes(path, None, {})
        self.assertEqual(r["status"], "pass", r)
        self.assertIn("NIN:12345678901", r["findings"]["qr"]["data"])

if __name__ == "__main__":
    unittest.main()
