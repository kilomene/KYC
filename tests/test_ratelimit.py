"""WS3 rate limits: per-API-key, per-IP and per-flow-token throttles
return real 429s with Retry-After, and windows reset."""
import json, os, sys, time, unittest, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, make_tenant

ENV_KEYS = ("KYC_RL_API_PER_MIN", "KYC_RL_FLOW_PER_MIN", "KYC_RL_IP_PER_MIN", "KYC_RL_WINDOW_SEC")

def raw_get(srv, path, key=None, token=None):
    h = {}
    if key: h["Authorization"] = f"Bearer {key}"
    if token: h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(srv.base + path, method="GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), json.loads(e.read() or b"{}")
        except Exception:
            return e.code, dict(e.headers), {}

class RateLimitCase(unittest.TestCase):
    LIMITS = {}
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ.update(self.LIMITS)
    def tearDown(self):
        for k in ENV_KEYS:
            if self._saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = self._saved[k]

class TestApiKeyLimit(RateLimitCase):
    LIMITS = {"KYC_RL_API_PER_MIN": "3", "KYC_RL_IP_PER_MIN": "100000", "KYC_RL_WINDOW_SEC": "60"}
    def test_limit_trips_with_429_and_retry_after(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            for i in range(3):
                st, _, _ = raw_get(srv, "/v1/keys", key=key)
                self.assertEqual(st, 200, f"request {i + 1}")
            st, headers, body = raw_get(srv, "/v1/keys", key=key)
            self.assertEqual(st, 429, body)
            self.assertEqual(body["error"]["code"], "rate_limited")
            self.assertIn("Retry-After", headers)
            self.assertGreaterEqual(int(headers["Retry-After"]), 1)

    def test_limits_are_per_key(self):
        with Server() as srv:
            _, key_a, _ = make_tenant(srv, "Tenant A")
            _, key_b, _ = make_tenant(srv, "Tenant B")
            for _ in range(3):
                raw_get(srv, "/v1/keys", key=key_a)
            st, _, _ = raw_get(srv, "/v1/keys", key=key_a)
            self.assertEqual(st, 429)
            st, _, _ = raw_get(srv, "/v1/keys", key=key_b)
            self.assertEqual(st, 200)  # B's bucket is untouched

class TestWindowReset(RateLimitCase):
    LIMITS = {"KYC_RL_API_PER_MIN": "2", "KYC_RL_IP_PER_MIN": "100000", "KYC_RL_WINDOW_SEC": "1"}
    def test_limit_resets_after_window(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            self.assertEqual(raw_get(srv, "/v1/keys", key=key)[0], 200)
            self.assertEqual(raw_get(srv, "/v1/keys", key=key)[0], 200)
            self.assertEqual(raw_get(srv, "/v1/keys", key=key)[0], 429)
            time.sleep(1.2)
            self.assertEqual(raw_get(srv, "/v1/keys", key=key)[0], 200)

class TestFlowTokenLimit(RateLimitCase):
    LIMITS = {"KYC_RL_API_PER_MIN": "100000", "KYC_RL_FLOW_PER_MIN": "2",
              "KYC_RL_IP_PER_MIN": "100000", "KYC_RL_WINDOW_SEC": "60"}
    def test_flow_endpoints_throttled_per_token(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants",
                           {"first_name": "Rate", "last_name": "Limited", "dob": "1990-01-01", "country": "NG"}, key=key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
            token = sess["flow_token"]
            self.assertEqual(raw_get(srv, "/v1/flow/session", token=token)[0], 200)
            self.assertEqual(raw_get(srv, "/v1/flow/session", token=token)[0], 200)
            st, headers, body = raw_get(srv, "/v1/flow/session", token=token)
            self.assertEqual(st, 429, body)
            self.assertEqual(body["error"]["code"], "rate_limited")

class TestIpLimit(RateLimitCase):
    LIMITS = {"KYC_RL_API_PER_MIN": "100000", "KYC_RL_IP_PER_MIN": "4", "KYC_RL_WINDOW_SEC": "60"}
    def test_ip_limit_trips_across_keys(self):
        with Server() as srv:
            # Even tenant creation counts toward the caller's IP.
            _, key_a, _ = make_tenant(srv, "Tenant A")
            _, key_b, _ = make_tenant(srv, "Tenant B")
            self.assertEqual(raw_get(srv, "/v1/keys", key=key_a)[0], 200)
            self.assertEqual(raw_get(srv, "/v1/keys", key=key_b)[0], 200)
            st, _, body = raw_get(srv, "/v1/keys", key=key_a)
            self.assertEqual(st, 429, body)

if __name__ == "__main__":
    unittest.main()
