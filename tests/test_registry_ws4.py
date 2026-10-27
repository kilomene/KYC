"""WS4 authoritative data: adapters fail closed, verify only on
a real registry record + name match, and the registry-check
endpoint stores its outcome without touching reviewer fields."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import registry as R


def _fetcher_factory(status, body):
    def fetch(url, headers):
        return status, body
    return fetch


class TestAdapters(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("KYC_REGISTRY_GB_KEY", None)
        os.environ.pop("KYC_REGISTRY_AU_GUID", None)

    def test_gb_unconfigured_fails_closed(self):
        r = R.lookup_business("GB", "12345678", "ACME LTD")
        self.assertEqual(r["status"], "not_configured")

    def test_gb_verified_on_record_and_name_match(self):
        os.environ["KYC_REGISTRY_GB_KEY"] = "test-key"
        f = _fetcher_factory(200, {"company_name": "ACME LIMITED",
                                   "company_number": "12345678",
                                   "company_status": "active",
                                   "date_of_creation": "2020-01-01"})
        r = R.lookup_business("GB", "12345678", "ACME LTD", fetcher=f)
        self.assertEqual(r["status"], "verified", r)
        self.assertEqual(r["source"], "companies_house")

    def test_gb_not_found(self):
        os.environ["KYC_REGISTRY_GB_KEY"] = "test-key"
        r = R.lookup_business("GB", "99999999", "GHOST LTD",
                              fetcher=_fetcher_factory(404, {}))
        self.assertEqual(r["status"], "not_found")

    def test_gb_name_mismatch(self):
        os.environ["KYC_REGISTRY_GB_KEY"] = "test-key"
        f = _fetcher_factory(200, {"company_name": "OTHER HOLDINGS LTD",
                                   "company_status": "active"})
        r = R.lookup_business("GB", "12345678", "ACME LTD", fetcher=f)
        self.assertEqual(r["status"], "name_mismatch")

    def test_gb_unavailable(self):
        os.environ["KYC_REGISTRY_GB_KEY"] = "test-key"
        r = R.lookup_business("GB", "12345678", "ACME LTD",
                              fetcher=_fetcher_factory(0, {}))
        self.assertEqual(r["status"], "unavailable")

    def test_ng_honest_not_configured(self):
        r = R.lookup_business("NG", "RC123456", "LAGOS WIDGETS LTD")
        self.assertEqual(r["status"], "not_configured")
        self.assertEqual(r["source"], "cac_nigeria")

    def test_national_id_ng_not_configured(self):
        r = R.verify_national_id("NG", "nin", "12345678901")
        self.assertEqual(r["status"], "not_configured")
        self.assertEqual(r["source"], "nimc")


class TestRegistryCheckEndpoint(unittest.TestCase):
    def test_endpoint_records_lookup(self):
        from helpers import Server, call, make_tenant
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, biz = call(srv, "POST", "/v1/businesses",
                           {"legal_name": "LAGOS WIDGETS LTD",
                            "registration_number": "RC123456",
                            "country": "NG"}, key=key)
            self.assertEqual(st, 201, biz)
            st, r = call(srv, "POST", f"/v1/businesses/{biz['id']}/registry-check",
                         {}, key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["registry_lookup"]["status"], "not_configured")
            self.assertEqual(r["registry_lookup"]["source"], "cac_nigeria")
            st, got = call(srv, "GET", f"/v1/businesses/{biz['id']}", key=key)
            self.assertEqual(got["registry_lookup_status"], "not_configured")
            self.assertEqual(got["registry_source"], "cac_nigeria")
            self.assertTrue(got["registry_checked_at"])


if __name__ == "__main__":
    unittest.main()
