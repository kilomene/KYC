"""Rectification build (2026-10-26): paper document model.

The owner's real Nigerian NIN slip — a wide, bowed, laminated PAPER
printout (~2.18:1 in frame) — could never pass the scanner: the
registry carried it at aspect 1.41 with a card-style ±10% gate, the
client detector searched for rigid straight edges, and server framing
found no quad in his frame (largest_contour_ratio 0.0142). These
tests pin the fix:

  * registry geometry: paper/booklet types carry aspect RANGES,
    plastic keeps a point aspect;
  * client detector sims (Node harness running the SHIPPED flow.html
    detector code): curved paper slip with glare + hand occlusion
    detects; room / blank / small card / screen do not;
  * server framing finds and warps a synthetic curved paper sheet
    and still fails room-like negatives;
  * a synthetic wide slip drawn to the real layout classifies as
    NG/nin_slip and extracts its (synthetic) fields.

No owner data appears in any fixture — the wide slip below uses
invented values throughout.
"""
import io, json, os, shutil, subprocess, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from helpers import selfie_bytes, structured_photo
from server import docregistry as R
from server import framing as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPaperRegistryGeometry(unittest.TestCase):
    def test_nin_slip_is_paper_with_range(self):
        e = R.get_document("NG", "nin_slip")
        self.assertEqual(e["physical"], "paper")
        self.assertEqual((e["aspect_min"], e["aspect_max"]), (1.2, 2.8))
        self.assertEqual(e["guide_aspect"], 2.0)
        # sides / expiry / MRZ facts unchanged by the geometry fix
        self.assertEqual(e["sides"], 1)
        self.assertFalse(e["has_expiry"])
        self.assertFalse(e["mrz"])

    def test_green_id_book_is_booklet_with_range(self):
        e = R.get_document("ZA", "green_id_book")
        self.assertEqual(e["physical"], "booklet")
        self.assertLess(e["aspect_min"], e["aspect_max"])

    def test_cards_keep_point_aspect(self):
        for country, kind in (("NG", "passport"), ("US", "drivers_license"), ("NG", "nin_card")):
            e = R.get_document(country, kind)
            self.assertEqual(e["physical"], "card", f"{country}/{kind}")
            self.assertNotIn("aspect_min", e)
            self.assertEqual(e["guide_aspect"], e["aspect"])

    def test_every_entry_has_geometry(self):
        for country, docs in R.DOCUMENT_REGISTRY.items():
            for kind, e in docs.items():
                self.assertIn("physical", e, f"{country}/{kind}")
                self.assertIn("guide_aspect", e, f"{country}/{kind}")
                if e["physical"] == "card":
                    self.assertIn("aspect", e, f"{country}/{kind}")
                else:
                    self.assertLess(e["aspect_min"], e["guide_aspect"], f"{country}/{kind}")
                    self.assertLess(e["guide_aspect"], e["aspect_max"], f"{country}/{kind}")


def _curved_paper_bytes():
    """A wide paper sheet, bowed top/bottom, print rows, portrait box
    and a glare spot, on a dark background (OpenCV drawing)."""
    import cv2
    img = np.full((800, 1240, 3), 42, np.uint8)
    x0, x1, yt, yb = 70, 1170, 250, 700
    pts = []
    for x in range(x0, x1 + 1, 20):
        pts.append([x, yt + int(16 * np.sin(np.pi * (x - x0) / (x1 - x0)))])
    for x in range(x1, x0 - 1, -20):
        pts.append([x, yb - int(13 * np.sin(np.pi * (x - x0) / (x1 - x0)))])
    cv2.fillPoly(img, [np.array(pts, np.int32)], (208, 208, 208))
    # print: header rule + text dashes + portrait box
    cv2.line(img, (x0 + 30, yt + 60), (x1 - 30, yt + 74), (90, 90, 90), 3)
    rng = np.random.default_rng(7)
    for row in range(5):
        y = yt + 110 + row * 62
        x = x0 + 40
        while x < 800:
            ln = int(rng.integers(30, 110))
            cv2.rectangle(img, (x, y), (min(x + ln, 810), y + 7), (92, 92, 92), -1)
            x += ln + int(rng.integers(12, 30))
    cv2.rectangle(img, (950, yt + 90), (1120, yb - 70), (150, 150, 150), -1)
    cv2.ellipse(img, (1035, yt + 190), (42, 58), 0, 0, 360, (95, 95, 95), -1)
    # glare spot overlapping the top-right corner
    for yy in range(800):
        for xx in range(1240):
            d = np.hypot(xx - 1080, yy - 215)
            if d < 55:
                img[yy, xx] = np.clip(img[yy, xx].astype(int) + int((55 - d) * 2.2), 0, 255)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _room_bytes():
    """A room-like scene: mid-grey walls, one bright window — the
    hallucination case the framing gates exist to refuse."""
    import cv2
    img = np.full((800, 1240, 3), 105, np.uint8)
    cv2.rectangle(img, (820, 90), (1150, 430), (196, 196, 196), -1)   # window
    cv2.rectangle(img, (975, 90), (990, 430), (80, 80, 80), -1)
    cv2.rectangle(img, (820, 250), (1150, 262), (80, 80, 80), -1)
    cv2.rectangle(img, (70, 560), (1170, 800), (74, 74, 74), -1)      # sofa band
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class TestServerFramingPaper(unittest.TestCase):
    def test_curved_paper_passes_and_warps(self):
        r = F.check_document_framing(data=_curved_paper_bytes())
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertTrue(r["findings"]["quad_found"])
        self.assertTrue(r["findings"]["warp_applied"])
        self.assertGreaterEqual(r["findings"]["aspect"], 1.2)
        self.assertLessEqual(r["findings"]["aspect"], 2.8)

    def test_room_window_still_fails(self):
        r = F.check_document_framing(data=_room_bytes())
        self.assertEqual(r["status"], "fail", r["findings"])
        self.assertIn(r["reason_codes"][0], ("document_not_detected", "document_too_small_in_frame"))

    def test_negatives_still_fail(self):
        buf = io.BytesIO(); Image.new("RGB", (1240, 800), "white").save(buf, format="PNG")
        self.assertEqual(F.check_document_framing(data=buf.getvalue())["status"], "fail")
        buf = io.BytesIO(); structured_photo().save(buf, format="PNG")
        self.assertEqual(F.check_document_framing(data=buf.getvalue())["status"], "fail")
        self.assertEqual(F.check_document_framing(data=selfie_bytes())["status"], "fail")

    def test_warp_rendition_for_photographed_sheet(self):
        import tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as tf:
            tf.write(_curved_paper_bytes()); path = tf.name
        try:
            warped = F.warped_rendition(path)
            self.assertIsNotNone(warped)
            im = Image.open(warped)
            self.assertGreater(im.width / im.height, 1.6)   # wide, flat
            self.assertLess(im.width / im.height, 2.6)
        finally:
            os.unlink(path)


def _synthetic_slip_bytes():
    """The real NIN-slip layout class with INVENTED values."""
    W, H = 1240, 620
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    d.text((300, 26), "National Identity Management System", fill="black", font=font)
    d.text((360, 66), "National Identification Number Slip (NINS)", fill="black", font=small)
    d.line([(20, 120), (1220, 120)], fill="black", width=3)
    d.text((30, 150), "Tracking ID: S1EXXX000000000", fill="black", font=small)
    d.text((30, 250), "NIN: 12345678901", fill="black", font=font)
    d.text((470, 150), "Surname: SAMPLETON", fill="black", font=small)
    d.text((470, 250), "First Name: EXAMPLE", fill="black", font=small)
    d.text((470, 330), "Middle Name: TEST", fill="black", font=small)
    d.text((470, 410), "Gender: F", fill="black", font=small)
    d.text((30, 430), "Issue Date: N/A", fill="black", font=small)
    d.text((30, 500), "Note: The National Identification Number (NIN) is your identity. It is confidential.",
           fill="black", font=tiny)
    d.rectangle([990, 140, 1180, 380], outline="black", width=3)
    d.ellipse([1030, 180, 1140, 300], outline="black", width=3)
    buf = io.BytesIO(); im.save(buf, format="PNG")
    return buf.getvalue()


class TestSyntheticWideSlip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        from server import vision as V
        cls._tmp = tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False)
        cls._tmp.write(_synthetic_slip_bytes()); cls._tmp.close()
        cls.path = cls._tmp.name
        cls.ocr = V.read_document_text(cls.path, expect_mrz=False)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.path)

    def test_classifies_as_nin_slip(self):
        from server import templates as T
        r = T.check_classification(self.path, "NG", "nin_slip", ocr_text=self.ocr["text"])
        self.assertEqual(r["status"], "pass", r["findings"])
        self.assertGreaterEqual(r["findings"]["score"], 70)
        aspect = r["findings"]["elements"]["aspect"]
        self.assertEqual(aspect["range"], [1.2, 2.8])
        self.assertEqual(aspect["match"], 1.0)

    def test_extracts_fields(self):
        from server import fieldtemplates as FT
        r = FT.extract_fields(self.path, "NG", "nin_slip", ocr_text=self.ocr["text"])
        f = r["findings"]["fields"]
        self.assertEqual(f["number"]["value"], "12345678901")
        self.assertIs(f["number"]["format_valid"], True)
        self.assertEqual(f["surname"]["value"], "SAMPLETON")
        self.assertIn("EXAMPLE", f["given_names"]["value"])
        # the standard slip prints no DOB — nothing may be invented
        self.assertIsNone(f["dob"]["value"])

    def test_full_frame_scan_gets_no_fragment_warp(self):
        # The flat scan's only framing quad is its photo box; the warp
        # gate must refuse it so classification reads the whole slip.
        self.assertIsNone(F.warped_rendition(self.path))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TestClientDetectorSims(unittest.TestCase):
    def test_harness_fixtures(self):
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "detector_harness.js")],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        results = json.loads(out.stdout)
        self.assertGreaterEqual(len(results), 10)
        for r in results:
            self.assertEqual(r["state"], r["expect"], f"scenario {r['name']}")


if __name__ == "__main__":
    unittest.main()
