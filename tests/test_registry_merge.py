"""Phase 4 WS1 registry merge: the researched document types for the
remaining launch countries, with their researched facts — no-expiry
types, the ZA green-book validity window, holder-branch notes — all
validating through the existing registry plumbing (flow offers them,
unsupported country/kind combinations still 422)."""
import unittest
from datetime import date

from server import checks as C
from server import docregistry as R
from tests.helpers import Server, call, make_tenant, id_image_bytes
from tests.helpers import multipart

class TestMergedFacts(unittest.TestCase):
    def test_india_no_expiry_pair(self):
        a = R.get_document("IN", "aadhaar")
        self.assertIsNotNone(a)
        self.assertFalse(a["has_expiry"]); self.assertEqual(a["sides"], 2)
        p = R.get_document("IN", "pan_card")
        self.assertIsNotNone(p)
        self.assertFalse(p["has_expiry"]); self.assertEqual(p["sides"], 1)

    def test_philid_and_umid(self):
        ph = R.get_document("PH", "philid")
        self.assertIsNotNone(ph)
        # Citizen rule is the registry default; the resident-alien
        # 1-year branch is recorded honestly as a note.
        self.assertFalse(ph["has_expiry"])
        self.assertIn("Resident aliens", ph["note"])
        self.assertIsNotNone(R.get_document("PH", "umid"))
        self.assertFalse(R.get_document("PH", "umid")["has_expiry"])

    def test_singapore_nric_no_printed_expiry(self):
        n = R.get_document("SG", "nric")
        self.assertIsNotNone(n)
        self.assertFalse(n["has_expiry"])
        self.assertIn("re-register at age 30 and 55", n["note"])

    def test_kenya_two_generations_opposite_rules(self):
        old = R.get_document("KE", "national_id")
        new = R.get_document("KE", "maisha_card")
        self.assertFalse(old["has_expiry"])   # 2nd generation: no expiry
        self.assertTrue(new["has_expiry"])    # Maisha Card: 10 years

    def test_za_smart_id_and_green_book(self):
        self.assertFalse(R.get_document("ZA", "smart_id")["has_expiry"])
        g = R.get_document("ZA", "green_id_book")
        self.assertIsNotNone(g)
        self.assertFalse(g["has_expiry"])                 # nothing printed
        self.assertEqual(g["validity_end"], "2028-03-31")  # but legally time-bombed

    def test_ae_emirates_id_always_expires(self):
        e = R.get_document("AE", "emirates_id")
        self.assertIsNotNone(e); self.assertTrue(e["has_expiry"])

    def test_fr_nl_ie_types(self):
        self.assertIsNotNone(R.get_document("FR", "national_id"))
        self.assertIn("pink paper", R.get_document("FR", "drivers_licence")["note"])
        self.assertIsNotNone(R.get_document("NL", "national_id"))
        self.assertIsNotNone(R.get_document("NL", "drivers_licence"))
        pc = R.get_document("IE", "passport_card")
        self.assertIsNotNone(pc); self.assertTrue(pc["has_expiry"])
        self.assertFalse(R.get_document("IE", "age_card")["has_expiry"])

    def test_every_entry_carries_the_plumbing_facts(self):
        for country, docs in R.DOCUMENT_REGISTRY.items():
            for kind, entry in docs.items():
                for key in ("label", "sides", "has_expiry", "mrz", "aspect"):
                    self.assertIn(key, entry, f"{country}/{kind} missing {key}")
                self.assertIn(entry["sides"], (1, 2))

    def test_unsupported_combos_still_absent(self):
        self.assertIsNone(R.get_document("KE", "nin_slip"))
        self.assertIsNone(R.get_document("ZA", "voter_card"))
        self.assertIsNone(R.get_document("US", "aadhaar"))
        self.assertIsNone(R.get_document("IN", "emirates_id"))

class TestValidityWindow(unittest.TestCase):
    def test_green_book_valid_before_cutoff(self):
        r = C.check_expiry_age(None, doc_dob="1990-01-01", applicant_dob="1990-01-01",
                               has_expiry=False, validity_end="2028-03-31", today=date(2026, 10, 26))
        self.assertEqual(r["status"], "pass", r)

    def test_green_book_invalid_after_cutoff(self):
        r = C.check_expiry_age(None, doc_dob="1990-01-01", applicant_dob="1990-01-01",
                               has_expiry=False, validity_end="2028-03-31", today=date(2028, 4, 1))
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("document_validity_window_ended", r["reason_codes"])

    def test_window_applies_even_with_printed_expiry(self):
        r = C.check_expiry_age(None, doc_expiry="2035-01-01", doc_dob="1990-01-01",
                               has_expiry=True, validity_end="2028-03-31", today=date(2029, 1, 1))
        self.assertEqual(r["status"], "fail", r)

class TestNoExpiryNeverFailsExpiry(unittest.TestCase):
    def test_all_no_expiry_registry_types_pass_without_dates(self):
        for country, docs in R.DOCUMENT_REGISTRY.items():
            for kind, entry in docs.items():
                if entry["has_expiry"]:
                    continue
                if entry.get("validity_end"):
                    continue  # window types are covered above
                r = C.check_expiry_age(None, doc_dob="1990-01-01", applicant_dob="1990-01-01",
                                       has_expiry=entry["has_expiry"], today=date(2026, 10, 26))
                self.assertEqual(r["status"], "pass", f"{country}/{kind}: {r}")
                self.assertIsNone(r["findings"]["expiry"])

class TestFlowPlumbing(unittest.TestCase):
    def _upload(self, srv, key, country, kind):
        st, app = call(srv, "POST", "/v1/applicants",
                       {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": country}, key=key)
        assert st == 201, app
        st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
        assert st == 201, sess
        call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=sess["flow_token"])
        return multipart(srv, "/v1/flow/document",
                         {"kind": kind, "issuing_country": country},
                         {"front": ("f.png", id_image_bytes(), "image/png")}, sess["flow_token"])

    def test_merged_types_are_offered(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            for country, kind in (("IN", "aadhaar"), ("ZA", "green_id_book"), ("PH", "philid"),
                                  ("SG", "nric"), ("AE", "emirates_id"), ("FR", "national_id"),
                                  ("IE", "passport_card"), ("KE", "maisha_card")):
                st, r = self._upload(srv, key, country, kind)
                self.assertEqual(st, 201, f"{country}/{kind}: {r}")

    def test_unsupported_combo_still_422(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, r = self._upload(srv, key, "KE", "nin_slip")
            self.assertEqual(st, 422, r)

if __name__ == "__main__":
    unittest.main()
