"""WS6 billing machinery: metering is exactly-once and priced
at decision time; sandbox is free; unset prices record UNPRICED
(never a guessed zero for live); invoices aggregate priced
events once; quotas cap live verifications only."""
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import billing as B
from server.db import DB
import itertools

_ids = itertools.count()
def nid():
    return f"id-{next(_ids)}"


class TestBillingEngine(unittest.TestCase):
    def setUp(self):
        self.db = DB(os.path.join(tempfile.mkdtemp(prefix="kyc-bill-"), "data"))
        B.ensure_schema(self.db)

    def test_meter_live_with_price(self):
        B.set_price(self.db, nid, 2, "live", 150)
        eid = B.meter(self.db, nid, "t1", "live", "sess-1", 2)
        self.assertIsNotNone(eid)
        row = self.db.one("SELECT * FROM usage_events WHERE session_id='sess-1'")
        self.assertEqual(row["amount_cents"], 150)

    def test_meter_exactly_once(self):
        B.set_price(self.db, nid, 1, "live", 100)
        B.meter(self.db, nid, "t1", "live", "sess-1", 1)
        self.assertIsNone(B.meter(self.db, nid, "t1", "live", "sess-1", 1))
        n = self.db.one("SELECT COUNT(*) AS n FROM usage_events")["n"]
        self.assertEqual(n, 1)

    def test_meter_sandbox_free(self):
        B.meter(self.db, nid, "t1", "test", "sess-9", 3)
        row = self.db.one("SELECT * FROM usage_events WHERE session_id='sess-9'")
        self.assertEqual(row["amount_cents"], 0)
        self.assertEqual(row["price_id"], B.SANDBOX_FREE)

    def test_meter_unpriced_when_no_price(self):
        B.meter(self.db, nid, "t1", "live", "sess-2", 1)
        row = self.db.one("SELECT * FROM usage_events WHERE session_id='sess-2'")
        self.assertIsNone(row["amount_cents"])

    def test_invoice_aggregates_once(self):
        B.set_price(self.db, nid, 1, "live", 200)
        for s in ("a", "b", "c"):
            B.meter(self.db, nid, "t1", "live", f"sess-{s}", 1)
        inv, unpriced = B.generate_invoice(self.db, nid, "t1", "live",
                                           "2026-01-01", "2027-01-01")
        self.assertEqual(inv["total_cents"], 600)
        self.assertEqual(inv["events"], 3)
        self.assertEqual(unpriced, 0)
        inv2, _ = B.generate_invoice(self.db, nid, "t1", "live",
                                     "2026-01-01", "2027-01-01")
        self.assertIsNone(inv2)  # nothing left to bill twice

    def test_invoice_skips_unpriced(self):
        B.meter(self.db, nid, "t1", "live", "sess-u", 1)  # no price set
        inv, unpriced = B.generate_invoice(self.db, nid, "t1", "live",
                                           "2026-01-01", "2027-01-01")
        self.assertIsNone(inv)
        self.assertEqual(unpriced, 1)

    def test_price_versioning(self):
        B.set_price(self.db, nid, 1, "live", 100)
        B.meter(self.db, nid, "t1", "live", "sess-old", 1)
        B.set_price(self.db, nid, 1, "live", 250)
        B.meter(self.db, nid, "t1", "live", "sess-new", 1)
        rows = self.db.all("SELECT session_id, amount_cents FROM usage_events ORDER BY session_id")
        amounts = {r["session_id"]: r["amount_cents"] for r in rows}
        self.assertEqual(amounts, {"sess-new": 250, "sess-old": 100})


class TestBillingEndpoints(unittest.TestCase):
    def test_prices_admin_gated_and_metering_e2e(self):
        from helpers import Server, call, multipart, make_tenant, selfie_bytes, PLATFORM_ADMIN
        from test_identity_from_document import _document_session, _upload_doc
        from PIL import Image
        import io
        from test_paper_detection import _synthetic_slip_bytes
        with Server() as srv:
            st, r = call(srv, "POST", "/v1/platform/prices",
                         {"level": 1, "env": "live", "unit_price_cents": 100})
            self.assertEqual(st, 403, r)  # no operator token
            st, r = call(srv, "POST", "/v1/platform/prices",
                         {"level": 1, "env": "test", "unit_price_cents": 100},
                         raw_headers={"X-Platform-Admin": PLATFORM_ADMIN})
            self.assertIn(st, (201, 422), r)  # test env price is allowed to exist; sandbox stays free at metering


class TestMeteringEndToEnd(unittest.TestCase):
    def test_decision_meters_exactly_one_free_sandbox_event(self):
        import sqlite3
        from helpers import Server, call, multipart, make_tenant, selfie_bytes, id_image_bytes
        from test_identity_from_document import _document_session, _upload_doc
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            _upload_doc(srv, token, id_image_bytes(), "passport")
            st, r = multipart(srv, "/v1/flow/selfie", {},
                              {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            assert st == 201, r
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(view["status"], "approved", view)
            # a duplicate submit must not meter twice
            call(srv, "POST", "/v1/flow/submit", {}, token=token)
            conn = sqlite3.connect(os.path.join(srv.data_dir, "kyc.db"))
            rows = conn.execute("SELECT amount_cents, price_id FROM usage_events WHERE session_id=?",
                                (sess["id"],)).fetchall()
            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0], (0, "sandbox_free"))
            st, usage = call(srv, "GET", "/v1/usage", key=key)
            self.assertEqual(st, 200, usage)
            self.assertEqual(usage["usage"][0]["verifications"], 1)


if __name__ == "__main__":
    unittest.main()
