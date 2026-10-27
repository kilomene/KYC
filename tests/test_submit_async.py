"""Asynchronous, idempotent submit (2026-10-26).

The decision pipeline takes 60-120s on a real session while the tunnel
caps a request at ~30s, so POST /v1/flow/submit now claims the session
atomically, runs the pipeline on ONE background thread, and answers
202 {"status":"processing"} when the pass outlives a bounded grace
(fast passes still answer 200 with the decision, as before). These
tests pin the contract:
  * two submits racing start exactly ONE pipeline pass; the loser
    gets 202, the winner the decision;
  * a submit after the decision returns that same decision (200);
  * a FRESH 'processing' claim refuses a new pass (202);
  * a STALE claim (>10 min — its worker died) is reclaimed and runs.
"""
import threading
import unittest
from datetime import datetime, timedelta, timezone

from helpers import Server, call, make_tenant, drive_flow
from server.db import DB


def _count(srv, sql, params):
    db = DB(srv.data_dir)
    return db.one(sql, params)[0]


class TestSubmitAsync(unittest.TestCase):
    def test_racing_submits_single_pass_then_decision_returned(self):
        with Server() as srv:
            _tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            sid = ctx["session"]["id"]
            results = {}

            def do_submit(name):
                results[name] = call(srv, "POST", "/v1/flow/submit", {},
                                     token=ctx["token"])

            threads = [threading.Thread(target=do_submit, args=(n,))
                       for n in ("a", "b")]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=180)
            self.assertEqual(len(results), 2, results)
            codes = sorted(st for st, _v in results.values())
            self.assertEqual(codes, [200, 202], results)
            loser = [v for st, v in results.values() if st == 202][0]
            self.assertEqual(loser["status"], "processing")
            winner = [v for st, v in results.values() if st == 200][0]
            self.assertIsNotNone(winner["decision"], winner)
            # Exactly ONE pipeline pass ran: one decision, and a check
            # type the pipeline records exactly once per pass.
            self.assertEqual(
                _count(srv, "SELECT COUNT(*) FROM decisions WHERE session_id=?",
                       (sid,)), 1)
            self.assertEqual(
                _count(srv, "SELECT COUNT(*) FROM checks WHERE session_id=? AND type='capture_quality'",
                       (sid,)), 1)
            # A submit AFTER the decision returns the same decision.
            st, view = call(srv, "POST", "/v1/flow/submit", {},
                            token=ctx["token"])
            self.assertEqual(st, 200, view)
            self.assertEqual(view["decision"]["id"],
                             winner["decision"]["id"])

    def test_fresh_processing_claim_refuses_new_pass(self):
        with Server() as srv:
            _tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            sid = ctx["session"]["id"]
            db = DB(srv.data_dir)
            db.execute(
                "UPDATE sessions SET status='processing', processing_started_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), sid))
            st, view = call(srv, "POST", "/v1/flow/submit", {},
                            token=ctx["token"])
            self.assertEqual(st, 202, view)
            self.assertEqual(view["status"], "processing")
            self.assertEqual(
                _count(srv, "SELECT COUNT(*) FROM decisions WHERE session_id=?",
                       (sid,)), 0)

    def test_stale_processing_claim_is_reclaimed(self):
        with Server() as srv:
            _tid, test_key, _ = make_tenant(srv)
            ctx = drive_flow(srv, test_key, level=2)
            sid = ctx["session"]["id"]
            db = DB(srv.data_dir)
            stale = (datetime.now(timezone.utc)
                     - timedelta(minutes=11)).isoformat()
            db.execute(
                "UPDATE sessions SET status='processing', processing_started_at=? WHERE id=?",
                (stale, sid))
            st, view = call(srv, "POST", "/v1/flow/submit", {},
                            token=ctx["token"])
            self.assertEqual(st, 200, view)
            self.assertIsNotNone(view["decision"], view)
            self.assertEqual(
                _count(srv, "SELECT COUNT(*) FROM decisions WHERE session_id=?",
                       (sid,)), 1)


if __name__ == "__main__":
    unittest.main()
