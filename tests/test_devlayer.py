"""Developer layer (2026-10-27): webhook endpoint self-service
(DELETE own endpoint), the platform tenant-delete API
(confirm-gated, retains the audit/financial trail), and the
tenant dashboard page."""
import os, sqlite3, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, make_tenant, PLATFORM_ADMIN


class TestWebhookSelfService(unittest.TestCase):
    def test_delete_own_endpoint(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, ep = call(srv, "POST", "/v1/webhooks",
                          {"url": "https://example.com/hook", "events": ["session.completed"]}, key=key)
            self.assertEqual(st, 201, ep)
            st, r = call(srv, "GET", "/v1/webhooks", key=key)
            self.assertEqual(len(r["endpoints"]), 1)
            st, r = call(srv, "DELETE", "/v1/webhooks/" + ep["id"], key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["deleted"], ep["id"])
            st, r = call(srv, "GET", "/v1/webhooks", key=key)
            self.assertEqual(r["endpoints"], [])
            st, r = call(srv, "DELETE", "/v1/webhooks/" + ep["id"], key=key)
            self.assertEqual(st, 404, r)

    def test_cannot_delete_another_tenants_endpoint(self):
        with Server() as srv:
            _, key_a, _ = make_tenant(srv, "Tenant A")
            _, key_b, _ = make_tenant(srv, "Tenant B")
            st, ep = call(srv, "POST", "/v1/webhooks",
                          {"url": "https://example.com/a", "events": []}, key=key_a)
            self.assertEqual(st, 201, ep)
            st, r = call(srv, "DELETE", "/v1/webhooks/" + ep["id"], key=key_b)
            self.assertEqual(st, 404, r)
            st, r = call(srv, "GET", "/v1/webhooks", key=key_a)
            self.assertEqual(len(r["endpoints"]), 1)


class TestTenantDelete(unittest.TestCase):
    def test_gates_and_cascade(self):
        with Server() as srv:
            tid, key, _ = make_tenant(srv, "Doomed Tenant")
            # give the tenant some operational data
            st, app = call(srv, "POST", "/v1/applicants",
                           {"identity_source": "document", "country": "NG"}, key=key)
            self.assertEqual(st, 201, app)
            # no admin header -> 403
            st, r = call(srv, "DELETE", "/v1/platform/tenants/" + tid, {"confirm": tid})
            self.assertEqual(st, 403, r)
            # wrong confirm -> 422
            st, r = call(srv, "DELETE", "/v1/platform/tenants/" + tid, {"confirm": "nope"},
                         raw_headers={"X-Platform-Admin": PLATFORM_ADMIN})
            self.assertEqual(st, 422, r)
            # correct -> 200, operational data gone, key dead
            st, r = call(srv, "DELETE", "/v1/platform/tenants/" + tid, {"confirm": tid},
                         raw_headers={"X-Platform-Admin": PLATFORM_ADMIN})
            self.assertEqual(st, 200, r)
            self.assertGreaterEqual(r["counts"]["api_keys"], 2)
            self.assertGreaterEqual(r["counts"]["applicants"], 1)
            self.assertIn("audit_log", r["retained"])
            st, r = call(srv, "GET", "/v1/sessions", key=key)
            self.assertEqual(st, 401, r)
            # the deletion itself is on the retained record
            conn = sqlite3.connect(os.path.join(srv.data_dir, "kyc.db"))
            n = conn.execute("SELECT COUNT(*) FROM deletions WHERE target_id=? AND kind='tenant_delete'",
                             (tid,)).fetchone()[0]
            self.assertEqual(n, 1)
            a = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='tenant.delete' AND target_id=?",
                             (tid,)).fetchone()[0]
            self.assertEqual(a, 1)
            # second delete -> 404
            st, r = call(srv, "DELETE", "/v1/platform/tenants/" + tid, {"confirm": tid},
                         raw_headers={"X-Platform-Admin": PLATFORM_ADMIN})
            self.assertEqual(st, 404, r)


class TestDashboard(unittest.TestCase):
    def test_dashboard_page_served(self):
        with Server() as srv:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/dashboard", timeout=10) as resp:
                html = resp.read().decode()
            self.assertIn("tenant dashboard", html)
            self.assertIn("/v1/usage", html)


if __name__ == "__main__":
    unittest.main()
