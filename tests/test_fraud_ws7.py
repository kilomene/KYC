"""WS7 fraud intelligence: duplicate document/face detection over
a hashed, tenant-scoped index; velocity + coordinated-abuse
signals; signals route to review, never reject (engine doctrine).
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import fraud as F
from server.db import DB
import tempfile

NOW = "2026-10-27T12:00:00+00:00"
HOUR = "2026-10-27T11:00:00+00:00"
DAY = "2026-10-26T12:00:00+00:00"


def _emb(seed):
    # deterministic pseudo-embedding (128-d), unit-ish
    import random
    r = random.Random(seed)
    return [r.uniform(-1, 1) for _ in range(128)]


class TestFraudIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kyc-fraud-")
        self.db = DB(os.path.join(self.tmp, "data"))
        F.ensure_schema(self.db)

    def _index(self, tid="t1", env="test", sess="s1", app="a1",
               number="AB1234567", emb=None, country="US", kind="drivers_license"):
        import itertools
        counter = itertools.count()
        F.index_session(self.db, lambda: f"id-{sess}-{next(counter)}",
                        tid, env, sess, app, country, kind, number, emb, NOW)

    def _eval(self, tid="t1", env="test", sess="s2", app="a2",
              number="AB1234567", emb=None, ip=None, country="US", kind="drivers_license"):
        return F.evaluate(self.db, tid, env, sess, app, ip, country, kind,
                          number, emb, NOW, HOUR, DAY)

    def test_document_duplicate_other_applicant(self):
        self._index()
        _, reasons = self._eval()
        self.assertIn(F.DOC_DUP_REASON, reasons)

    def test_document_same_applicant_no_signal(self):
        self._index(app="a1")
        _, reasons = self._eval(app="a1", sess="s9")
        self.assertNotIn(F.DOC_DUP_REASON, reasons)

    def test_document_number_normalisation(self):
        self._index(number="ab 123-4567")
        _, reasons = self._eval(number="AB1234567")
        self.assertIn(F.DOC_DUP_REASON, reasons)

    def test_tenant_isolation(self):
        self._index(tid="t1")
        _, reasons = self._eval(tid="t2")
        self.assertNotIn(F.DOC_DUP_REASON, reasons)

    def test_face_duplicate_same_embedding(self):
        e = _emb(42)
        self._index(emb=e, number="ZZ9999999")
        findings, reasons = self._eval(emb=e, number="QQ1111111")
        self.assertGreaterEqual(findings["duplicate_face_bands"], F._FACE_MIN_BAND_HITS)
        self.assertIn(F.FACE_DUP_REASON, reasons)

    def test_face_unrelated_no_signal(self):
        self._index(emb=_emb(1), number="ZZ9999999")
        _, reasons = self._eval(emb=_emb(987654), number="QQ1111111")
        self.assertNotIn(F.FACE_DUP_REASON, reasons)

    def test_no_raw_values_in_index(self):
        self._index(emb=_emb(3))
        rows = self.db.execute("SELECT key_hash FROM fraud_index").fetchall() \
            if hasattr(self.db, "execute") else []
        for r in rows:
            self.assertNotIn("AB1234567", str(r[0]))


class TestDuplicateEndToEnd(unittest.TestCase):
    """Two applicants present the SAME synthetic passport: the
    first verifies clean; the second is routed to review by the
    duplicate signal — never auto-rejected (WS7 doctrine)."""

    def test_second_applicant_same_document_routes_to_review(self):
        from helpers import Server, call, multipart, make_tenant, selfie_bytes, id_image_bytes
        from test_identity_from_document import _document_session, _upload_doc, _checks
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            outcomes = []
            for _ in range(2):
                app, sess, token = _document_session(srv, key, level=1)
                _upload_doc(srv, token, id_image_bytes(), "passport")
                st, r = multipart(srv, "/v1/flow/selfie", {},
                                  {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
                assert st == 201, r
                st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
                self.assertEqual(st, 200, view)
                outcomes.append((view, _checks(srv, key, sess["id"])))
            self.assertEqual(outcomes[0][0]["status"], "approved", outcomes[0][0])
            second_view, second_checks = outcomes[1]
            fs = second_checks["fraud_signals"]
            self.assertTrue(fs["findings"]["duplicate_document"], fs)
            self.assertIn("duplicate_document", fs["reason_codes"], fs)
            self.assertEqual(second_view["status"], "needs_review", second_view)


if __name__ == "__main__":
    unittest.main()
