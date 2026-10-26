"""Phase 4 WS1 payload semantics: full AAMVA parsing + element format
validation, NG NIN-slip QR structure, Aadhaar secure-QR decompression
(structural+consistency — UIDAI signature NOT verified, and the
findings say so), PhilID QR structure. Decoded data must AGREE with
the printed document or it fails with code_decode_mismatch."""
import tempfile, unittest

from server import fieldtemplates as FT
from server import payloads as P
from server import vision as V
from tests.helpers import id_image_bytes

def _tmp(data, suffix=".png"):
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(data); f.close()
    return f.name

FULL_AAMVA = ("DAQD1234567\nDCSERIKSSON\nDACANNA\nDADMARIA\n"
              "DBB08121974\nDBA04152032\nDBD01022024\nDBC2\nDAJTX\nDAU510\n"
              "DAG12 MARINA ROAD\nDAH\nDAIHOUSTON\nDAK77001\nDCF DOCDISC123\nDCGUSA\n")

class TestAamva(unittest.TestCase):
    def test_full_element_parse(self):
        r = P.parse_aamva(FULL_AAMVA)
        self.assertIsNotNone(r)
        for eid in ("DAQ", "DCS", "DAC", "DAD", "DBB", "DBA", "DBC", "DAJ", "DAU", "DAG", "DAI", "DAK"):
            self.assertIn(eid, r["elements"], eid)
        f = r["fields"]
        self.assertEqual(f["number"], "D1234567")
        self.assertEqual(f["surname"], "ERIKSSON")
        self.assertEqual(f["first_name"], "ANNA")
        self.assertEqual(f["middle_names"], "MARIA")
        self.assertEqual(f["dob"], "1974-08-12")
        self.assertEqual(f["expiry"], "2032-04-15")
        self.assertEqual(f["sex"], "female")
        self.assertTrue(r["format_valid"], r["format"])
        self.assertEqual(r["validation_depth"], "semantic")

    def test_element_format_validation(self):
        bad = P.parse_aamva("DAQD1234567\nDCSERIKSSON\nDACANNA\nDBB02301974\nDBA04152032\nDBC7\nDAUABC\nDAJTEXAS\n")
        self.assertIsNotNone(bad)
        self.assertFalse(bad["format"]["DBB"])   # Feb 30 is not a date
        self.assertFalse(bad["format"]["DBC"])   # sex code outside {1,2,9}
        self.assertFalse(bad["format"]["DAU"])   # height not a format
        self.assertFalse(bad["format"]["DAJ"])   # jurisdiction not 2 letters
        self.assertFalse(bad["format_valid"])

    def test_non_aamva_text_is_none(self):
        self.assertIsNone(P.parse_aamva("just some text"))
        self.assertIsNone(P.parse_aamva(""))

    def test_cross_check_agreement_and_mismatch(self):
        parsed = P.parse_aamva(FULL_AAMVA)
        doc = {"doc_number": "D1234567", "doc_dob": "1974-08-12",
               "doc_expiry": "2032-04-15", "doc_last_name": "ERIKSSON"}
        mm, compared = P.cross_check_payload(parsed, doc)
        self.assertEqual(mm, []); self.assertGreaterEqual(compared, 4)
        mm, _ = P.cross_check_payload(parsed, {**doc, "doc_number": "X9999999"})
        self.assertIn("number", mm)

    def test_decode_codes_uses_full_parse(self):
        orig = V._decode_barcodes
        V._decode_barcodes = lambda p: [{"format": "PDF417", "text": FULL_AAMVA}]
        try:
            r = V.decode_codes(_tmp(id_image_bytes()), None,
                               {"doc_number": "D1234567", "doc_dob": "1974-08-12",
                                "doc_expiry": "2032-04-15", "doc_last_name": "ERIKSSON"},
                               country="US", kind="drivers_license")
            self.assertEqual(r["status"], "pass", r)
            self.assertIn("DAU", r["findings"]["payloads"][0]["elements_present"])
            self.assertTrue(r["findings"]["aamva_format_valid"])
        finally:
            V._decode_barcodes = orig

class TestNinQr(unittest.TestCase):
    PAYLOAD = "NIN: 12345678901\nSurname: ERIKSSON\nFirst Name: ANNA\nDOB: 12/08/1974"

    def test_structural_parse(self):
        r = P.parse_nin_qr(self.PAYLOAD)
        self.assertIsNotNone(r)
        self.assertEqual(r["fields"]["nin"], "12345678901")
        self.assertTrue(r["fields"]["nin_format_valid"])
        self.assertEqual(r["fields"]["surname"], "ERIKSSON")
        self.assertEqual(r["fields"]["dob"], "1974-08-12")
        # The honesty label: NIMC semantic verification is NOT done.
        self.assertEqual(r["validation_depth"], "structural")
        self.assertIn("NOT performed", r["depth_note"])

    def test_bad_nin_format_flagged(self):
        r = P.parse_nin_qr("NIN: 12345")
        self.assertIsNotNone(r)
        self.assertNotEqual(r["fields"].get("nin_format_valid"), True)

    def test_cross_check_mismatch(self):
        r = P.parse_nin_qr(self.PAYLOAD)
        mm, _ = P.cross_check_payload(r, {"doc_number": "99999999999", "doc_dob": "1974-08-12",
                                          "doc_last_name": "ERIKSSON"})
        self.assertIn("number", mm)

class TestAadhaarQr(unittest.TestCase):
    def _uid(self):
        base = "23456789012"
        return base + FT.verhoeff_digit(base)

    def test_secure_qr_roundtrip(self):
        uid = self._uid()
        payload = P.build_aadhaar_payload(uid, "ANNA ERIKSSON", "12-08-1974")
        r = P.parse_aadhaar_qr(payload)
        self.assertIsNotNone(r)
        self.assertEqual(r["fields"]["uid_last4"], uid[-4:])
        self.assertTrue(r["fields"]["uid_format_valid"])
        self.assertEqual(r["fields"]["name"], "ANNA ERIKSSON")
        self.assertEqual(r["fields"]["dob"], "1974-08-12")
        # Honesty: no UIDAI signature verification is claimed.
        self.assertIn("NOT verified", r["depth_note"])

    def test_tampered_uid_fails_verhoeff(self):
        uid = self._uid()
        bad_uid = uid[:5] + str((int(uid[5]) + 1) % 10) + uid[6:]
        payload = P.build_aadhaar_payload(bad_uid, "ANNA ERIKSSON", "12-08-1974")
        r = P.parse_aadhaar_qr(payload)
        self.assertIsNotNone(r)
        self.assertFalse(r["fields"]["uid_format_valid"])

    def test_cross_check_last4_and_dob(self):
        uid = self._uid()
        r = P.parse_aadhaar_qr(P.build_aadhaar_payload(uid, "ANNA ERIKSSON", "12-08-1974"))
        mm, compared = P.cross_check_payload(r, {"doc_number": uid, "doc_dob": "1974-08-12",
                                                 "doc_first_name": "ANNA", "doc_last_name": "ERIKSSON"})
        self.assertEqual(mm, []); self.assertGreaterEqual(compared, 3)
        mm, _ = P.cross_check_payload(r, {"doc_number": "999988887777", "doc_dob": "1974-08-12"})
        self.assertIn("number_last4", mm)

    def test_real_qr_image_roundtrip(self):
        # Encode the REAL secure-QR payload construction into an image
        # (zxing writer) and run the whole decode path on it.
        try:
            import numpy as np
            import zxingcpp
            from PIL import Image
        except Exception as e:
            self.skipTest(f"zxing writer unavailable: {e}")
        uid = self._uid()
        payload = P.build_aadhaar_payload(uid, "ANNA ERIKSSON", "12-08-1974")
        try:
            bc = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
            arr = np.asarray(zxingcpp.write_barcode_to_image(bc, scale=3))
        except Exception as e:
            self.skipTest(f"payload too large for a QR fixture at this scale: {e}")
        path = _tmp(b"")
        Image.fromarray(arr).convert("RGB").save(path)
        r = V.decode_codes(path, None, {"doc_number": uid, "doc_dob": "1974-08-12",
                                        "doc_first_name": "ANNA", "doc_last_name": "ERIKSSON"},
                           country="IN", kind="aadhaar")
        self.assertEqual(r["status"], "pass", r)
        stds = [p["standard"] for p in r["findings"]["payloads"]]
        self.assertIn("AADHAAR-SECURE-QR", stds)

class TestPhilIdQr(unittest.TestCase):
    PAYLOAD = '{"pcn":"1234567890123456","psn":"123456789012","surname":"ERIKSSON","first_name":"ANNA","dob":"1974-08-12"}'

    def test_structural_parse(self):
        r = P.parse_philid_qr(self.PAYLOAD)
        self.assertIsNotNone(r)
        self.assertEqual(r["fields"]["pcn"], "1234567890123456")
        self.assertEqual(r["fields"]["psn"], "123456789012")
        self.assertEqual(r["fields"]["surname"], "ERIKSSON")
        self.assertEqual(r["validation_depth"], "structural")
        self.assertIn("NOT performed", r["depth_note"])

    def test_cross_check(self):
        r = P.parse_philid_qr(self.PAYLOAD)
        mm, _ = P.cross_check_payload(r, {"doc_number": "1234567890123456", "doc_dob": "1974-08-12",
                                          "doc_last_name": "ERIKSSON"})
        self.assertEqual(mm, [])
        mm, _ = P.cross_check_payload(r, {"doc_number": "9999999999999999"})
        self.assertIn("number", mm)

    def test_unrelated_text_is_none(self):
        self.assertIsNone(P.parse_philid_qr("hello world"))

if __name__ == "__main__":
    unittest.main()
