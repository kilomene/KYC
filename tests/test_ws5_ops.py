"""WS5 ops surface: the platform metrics endpoint is operator-
gated (fail closed) and reports queue state."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, PLATFORM_ADMIN


class TestPlatformMetrics(unittest.TestCase):
    def test_metrics_requires_operator_token(self):
        with Server() as srv:
            st, r = call(srv, "GET", "/v1/platform/metrics")
            self.assertEqual(st, 403, r)

    def test_metrics_shape_with_token(self):
        import urllib.request, json as _json
        with Server() as srv:
            req = urllib.request.Request(srv.base + "/v1/platform/metrics",
                                         headers={"X-Platform-Admin": PLATFORM_ADMIN})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = _json.loads(resp.read().decode())
            self.assertIn("queue", body)
            self.assertIn("processing_now", body["queue"])
            self.assertIn("decisions_by_outcome", body)
            self.assertIn("fraud_index_rows", body)


if __name__ == "__main__":
    unittest.main()
