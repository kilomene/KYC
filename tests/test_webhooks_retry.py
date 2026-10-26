"""WS3 webhooks: retries with backoff, dead-letter queue, replay,
and the SSRF guard — all against a LOCAL test receiver. No external
webhooks are ever fired."""
import os, sys, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, make_tenant
from server.db import DB
from server import webhooks as WH

class Receiver:
    """A controllable webhook receiver: fails the first `fail_first`
    requests with HTTP 500, then answers 200. Records every hit."""
    def __init__(self, fail_first=0):
        self.fail_first = fail_first
        self.hits = []  # (body_bytes, headers dict)
        self._lock = threading.Lock()
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                with outer._lock:
                    outer.hits.append((body, dict(self.headers)))
                    count = len(outer.hits)
                code = 500 if count <= outer.fail_first else 200
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/hook"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
    def __enter__(self):
        self.thread.start()
        return self
    def __exit__(self, *a):
        self.httpd.shutdown(); self.httpd.server_close()

ENV_KEYS = ("KYC_ALLOW_PRIVATE_WEBHOOKS", "KYC_WEBHOOK_BACKOFF_SEC", "KYC_WEBHOOK_MAX_ATTEMPTS")

class WebhookCase(unittest.TestCase):
    ENV = {"KYC_ALLOW_PRIVATE_WEBHOOKS": "1", "KYC_WEBHOOK_BACKOFF_SEC": "0.05", "KYC_WEBHOOK_MAX_ATTEMPTS": "3"}
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ.update(self.ENV)
    def tearDown(self):
        for k in ENV_KEYS:
            if self._saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = self._saved[k]

    def _endpoint(self, srv, key, url):
        st, ep = call(srv, "POST", "/v1/webhooks", {"url": url, "events": []}, key=key)
        assert st == 201, ep
        return ep

    def _only_delivery(self, srv, tid):
        db = DB(srv.data_dir)
        rows = db.all("SELECT * FROM webhook_deliveries WHERE tenant_id=? ORDER BY created_at", (tid,))
        assert len(rows) == 1, rows
        return db, rows[0]

class TestRetryThenSuccess(WebhookCase):
    def test_transient_failure_retries_and_delivers(self):
        with Receiver(fail_first=1) as rx, Server() as srv:
            tid, key, _ = make_tenant(srv)
            ep = self._endpoint(srv, key, rx.url)
            db = DB(srv.data_dir)
            WH.fire(db, tid, "test", "session.completed", {"probe": 1})
            db, row = self._only_delivery(srv, tid)
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["attempts"], 1)
            self.assertIsNotNone(row["next_attempt_at"])
            time.sleep(0.1)
            out = WH.process_due(db)
            self.assertEqual(out["delivered"], 1, out)
            db, row = self._only_delivery(srv, tid)
            self.assertEqual(row["status"], "delivered")
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(len(rx.hits), 2)
            # The retry carried a VALID signature for the endpoint secret.
            body, headers = rx.hits[1]
            lowered = {k.lower(): v for k, v in headers.items()}
            self.assertTrue(WH.verify(ep["secret"], body, lowered.get("kyc-signature", "")))

class TestDeadLetterAndReplay(WebhookCase):
    def test_budget_exhaustion_dead_letters_then_replay_delivers(self):
        with Receiver(fail_first=99) as rx, Server() as srv:
            tid, key, _ = make_tenant(srv)
            self._endpoint(srv, key, rx.url)
            db = DB(srv.data_dir)
            WH.fire(db, tid, "test", "session.completed", {"probe": 2})
            for _ in range(2):
                time.sleep(0.1)
                WH.process_due(db)
            db, row = self._only_delivery(srv, tid)
            self.assertEqual(row["status"], "dead_letter", row["response_summary"])
            self.assertEqual(row["attempts"], 3)
            self.assertIsNotNone(row["dead_lettered_at"])
            # The DLQ is visible to the tenant, filtered by status.
            st, r = call(srv, "GET", "/v1/webhooks/deliveries?status=dead_letter", key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual([d["id"] for d in r["deliveries"]], [row["id"]])
            # Receiver recovers; an operator replay re-signs + delivers.
            rx.fail_first = 0
            hits_before = len(rx.hits)
            st, r = call(srv, "POST", f"/v1/webhooks/deliveries/{row['id']}/replay", {}, key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["delivery"]["status"], "delivered")
            self.assertGreater(len(rx.hits), hits_before)
            # Replay of another tenant's delivery: 404.
            _, key_b, _ = make_tenant(srv, "Tenant B")
            st, r = call(srv, "POST", f"/v1/webhooks/deliveries/{row['id']}/replay", {}, key=key_b)
            self.assertEqual(st, 404, r)

class TestSsrfGuard(unittest.TestCase):
    ENV = {}  # guard fully on: no private-webhook override
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
    def tearDown(self):
        for k in ENV_KEYS:
            if self._saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = self._saved[k]

    def test_url_allowed_blocks_non_public_targets(self):
        for url in ("http://169.254.169.254/latest/meta-data/",
                    "http://127.0.0.1:8790/healthz",
                    "http://localhost:8790/admin",
                    "http://10.0.0.5/hook",
                    "http://192.168.1.10/hook",
                    "http://[::1]/hook",
                    "file:///etc/passwd",
                    "gopher://example.com/"):
            ok, why = WH.url_allowed(url)
            self.assertFalse(ok, (url, why))
        ok, why = WH.url_allowed("https://93.184.216.34/hook")  # public IP literal (no DNS needed)
        self.assertTrue(ok, why)

    def test_blocked_delivery_is_recorded_and_never_sent(self):
        with Receiver(fail_first=0) as rx, Server() as srv:
            tid, key, _ = make_tenant(srv)
            st, ep = call(srv, "POST", "/v1/webhooks", {"url": rx.url, "events": []}, key=key)
            self.assertEqual(st, 201, ep)
            db = DB(srv.data_dir)
            WH.fire(db, tid, "test", "session.completed", {"probe": 3})
            rows = db.all("SELECT * FROM webhook_deliveries WHERE tenant_id=?", (tid,))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "failed")
            self.assertIn("SSRF guard", rows[0]["response_summary"])
            self.assertEqual(len(rx.hits), 0)  # nothing was ever sent

if __name__ == "__main__":
    unittest.main()
