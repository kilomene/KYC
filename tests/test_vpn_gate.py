"""VPN/proxy HARD GATE + location consistency (2026-10-26).

Unit level: verdict logic via an injected intel fetcher (proxy=true
detected; hosting+non-mobile detected; clean residential/mobile clean;
lookup failure -> unknown, NEVER a fake pass; private IPs are not even
looked up). API level: a detected IP blocks at consent (403, scanner
never starts) and a mid-flow VPN switch auto-rejects at submit."""
import tempfile, unittest
from unittest import mock

from helpers import Server, call, make_tenant, drive_flow
from server import vpncheck as VPN
from server.db import DB
import server

CLEAN = {"status": "success", "countryCode": "NG", "proxy": False, "hosting": False, "mobile": False, "isp": "Residential ISP", "org": "", "as": "AS1"}
PROXY = {**CLEAN, "countryCode": "NL", "proxy": True}
HOSTING = {**CLEAN, "hosting": True, "mobile": False}
HOSTING_MOBILE = {**CLEAN, "hosting": True, "mobile": True}

class TestVerdictLogic(unittest.TestCase):
    def setUp(self):
        self.db = DB(tempfile.mkdtemp(prefix="kyc-vpn-"))

    def test_proxy_true_is_detected(self):
        r = VPN.check_ip(self.db, "185.220.101.4", fetcher=lambda ip: PROXY)
        self.assertEqual(r["verdict"], "detected", r)
        self.assertEqual(r["ip_country"], "NL")

    def test_hosting_non_mobile_is_detected(self):
        r = VPN.check_ip(self.db, "203.0.113.9", fetcher=lambda ip: HOSTING)
        self.assertEqual(r["verdict"], "detected", r)

    def test_hosting_on_mobile_is_clean(self):
        r = VPN.check_ip(self.db, "105.112.0.1", fetcher=lambda ip: HOSTING_MOBILE)
        self.assertEqual(r["verdict"], "clean", r)

    def test_clean_residential_proceeds(self):
        r = VPN.check_ip(self.db, "41.203.10.25", fetcher=lambda ip: CLEAN)
        self.assertEqual(r["verdict"], "clean", r)
        self.assertEqual(r["ip_country"], "NG")

    def test_lookup_failure_is_unknown_never_a_fake_pass(self):
        def boom(ip): raise OSError("network unreachable")
        r = VPN.check_ip(self.db, "8.8.8.8", fetcher=boom)
        self.assertEqual(r["verdict"], "unknown", r)
        self.assertNotEqual(r["verdict"], "clean")

    def test_private_ip_is_unknown_and_never_fetched(self):
        calls = []
        r = VPN.check_ip(self.db, "192.168.1.5", fetcher=lambda ip: calls.append(ip) or CLEAN)
        self.assertEqual(r["verdict"], "unknown", r)
        self.assertEqual(calls, [], "private IPs must not hit the intel API")

    def test_per_ip_cache_means_one_fetch(self):
        calls = []
        VPN.check_ip(self.db, "41.203.10.25", fetcher=lambda ip: calls.append(ip) or CLEAN)
        VPN.check_ip(self.db, "41.203.10.25", fetcher=lambda ip: calls.append(ip) or CLEAN)
        self.assertEqual(len(calls), 1)

    def test_timezone_corroboration_is_recorded(self):
        r = VPN.check_ip(self.db, "41.203.10.25", device_tz="Europe/London",
                         declared_country="NG", fetcher=lambda ip: CLEAN)
        self.assertEqual(r["findings"]["tz_country"], "GB")
        self.assertTrue(r["findings"]["tz_mismatch_ip"])

class TestGateThroughAPI(unittest.TestCase):
    def test_consent_version_is_v2(self):
        self.assertEqual(server.CONSENT_TEXT_VERSION, "v2")

    def test_detected_vpn_blocks_at_consent(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants",
                           {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG", "email": "a@example.com"}, key=key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
            token = sess["flow_token"]
            with mock.patch.object(VPN, "_fetch_ip_api", return_value=PROXY):
                st, r = call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"},
                             token=token, raw_headers={"X-Client-IP": "185.220.101.4", "X-IP-Country": "NL"})
            self.assertEqual(st, 403, r)
            self.assertEqual(r["error"]["code"], "vpn_proxy_detected", r)

    def test_midflow_vpn_switch_auto_rejects_at_submit(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            intel = {"one": CLEAN, "two": PROXY}
            def fetcher(ip):
                return intel["one"] if ip.startswith("41.") else intel["two"]
            with mock.patch.object(VPN, "_fetch_ip_api", side_effect=fetcher):
                st, app = call(srv, "POST", "/v1/applicants",
                               {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG", "email": "a@example.com"}, key=key)
                st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
                token = sess["flow_token"]
                st, r = call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"},
                             token=token, raw_headers={"X-Client-IP": "41.203.10.25", "X-IP-Country": "NG"})
                self.assertEqual(st, 200, r)
                from helpers import multipart, id_image_bytes
                st, r = multipart(srv, "/v1/flow/document",
                                  {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna",
                                   "doc_last_name": "Eriksson", "doc_dob": "1974-08-12",
                                   "doc_expiry": "2032-04-15", "doc_number": "L898902C3"},
                                  {"front": ("front.png", id_image_bytes(), "image/png")}, token)
                self.assertEqual(st, 201, r)
                st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token,
                                raw_headers={"X-Client-IP": "185.220.101.4", "X-IP-Country": "NL"})
            self.assertEqual(view["status"], "rejected", view)
            self.assertEqual(view["checks_summary"]["vpn_proxy"], "fail", view)
            self.assertIn("vpn_proxy_detected", view["decision"]["reason_codes"], view)

    def test_location_pass_mismatch_and_masking(self):
        with Server() as srv, mock.patch.object(VPN, "_fetch_ip_api", return_value={**CLEAN, "mobile": True}):
            _, key, _ = make_tenant(srv)
            # Match: NG applicant, NG IP -> location pass, session approved.
            ctx = drive_flow(srv, key, level=1)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"],
                            raw_headers={"X-Client-IP": "41.203.10.25", "X-IP-Country": "NG"})
            # (consent happened inside drive_flow without geo headers, so
            # the submit-request IP is what the location check sees.)
            self.assertEqual(view["checks_summary"]["location_consistency"], "pass", view)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["client_ip_masked"], "41.203.x.x", view)
            # Mismatch: US IP for an NG applicant -> unclear + the +15
            # risk reason, but a mismatch ALONE never auto-rejects.
            ctx2 = drive_flow(srv, key, level=1)
            st, view2 = call(srv, "POST", "/v1/flow/submit", {}, token=ctx2["token"],
                             raw_headers={"X-Client-IP": "72.14.199.1", "X-IP-Country": "US"})
            self.assertEqual(view2["checks_summary"]["location_consistency"], "unclear", view2)
            self.assertIn("ip_country_mismatch", view2["decision"]["reason_codes"], view2)
            # Never an auto-REJECT on its own: at worst the risk engine
            # routes it to review (here the pre-existing fraud-signals
            # ip/document-country signal stacks with it over the ceiling).
            self.assertNotEqual(view2["status"], "rejected", view2)

    def test_location_unknown_without_geo_headers(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            ctx = drive_flow(srv, key, level=1)
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"])
            self.assertEqual(view["checks_summary"]["location_consistency"], "unclear", view)
            self.assertIn("ip_country_unknown",
                          [c["detail"] for c in view["decision"]["risk_contributions"]], view)

if __name__ == "__main__":
    unittest.main()
