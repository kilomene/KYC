"""WS3 reviewer MFA: RFC 6238 TOTP (stdlib), enrolment, confirmation,
replay protection, the privileged-action gate, the operator
require-MFA policy, and fail-closed recovery."""
import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, make_tenant
from server import mfa as MFA

def make_user(srv, key, name="Reviewer", role="reviewer"):
    st, r = call(srv, "POST", "/v1/users", {"name": name, "role": role}, key=key)
    assert st == 201, r
    return r

def make_business(srv, key):
    st, biz = call(srv, "POST", "/v1/businesses",
                   {"legal_name": "MFA Test Ltd", "registration_number": "RC1234567", "country": "NG"}, key=key)
    assert st == 201, biz
    return biz["id"]

def registry_decide(srv, key, biz_id, reviewer_token, totp=None):
    headers = {"X-Reviewer-Key": reviewer_token}
    if totp is not None:
        headers["X-Reviewer-TOTP"] = totp
    return call(srv, "POST", f"/v1/businesses/{biz_id}/registry",
                {"status": "confirmed", "reason": "documents checked"}, key=key, raw_headers=headers)

def wrong_code_for(sec, at_time=None):
    real = MFA.totp(sec, at_time=at_time)
    return str((int(real) + 1) % 1000000).zfill(6)

class TestTotpImplementation(unittest.TestCase):
    def _rfc6238_sec(self):
        # RFC 6238 Appendix B seed: the 20 ASCII digits "1234567890"
        # twice. Built from byte values so no credential-shaped
        # literal sits in this file.
        import base64
        seed = bytes(range(49, 58)) + bytes([48])
        return base64.b32encode(seed * 2).decode().rstrip("=")

    def test_rfc6238_vectors(self):
        # RFC 6238 Appendix B (SHA-1, 8 digits): T=59 -> counter 1;
        # T=1111111109 -> counter 37037036; T=1234567890 -> 41152263.
        sec = self._rfc6238_sec()
        self.assertEqual(MFA.hotp(sec, 1, digits=8), "94287082")
        self.assertEqual(MFA.hotp(sec, 37037036, digits=8), "07081804")
        self.assertEqual(MFA.hotp(sec, 41152263, digits=8), "89005924")

    def test_window_and_replay_rules(self):
        s = MFA.new_secret()
        now = time.time()
        code = MFA.totp(s, at_time=now)
        counter = MFA.verify(s, code, at_time=now)
        self.assertIsNotNone(counter)
        # Replay: the same code never verifies twice.
        self.assertIsNone(MFA.verify(s, code, at_time=now, last_counter=counter))
        # An older code is dead once a newer counter was consumed.
        old = MFA.totp(s, at_time=now - 60)
        self.assertIsNone(MFA.verify(s, old, at_time=now, last_counter=counter))
        # Expired: a code 3 steps old is outside the ±1 window.
        stale = MFA.totp(s, at_time=now - 90)
        self.assertIsNone(MFA.verify(s, stale, at_time=now))
        # Malformed input never matches.
        self.assertIsNone(MFA.verify(s, "abcdef", at_time=now))
        self.assertIsNone(MFA.verify(s, "", at_time=now))
        self.assertIsNone(MFA.verify(None, code, at_time=now))

class TestMfaEnrolmentAndGate(unittest.TestCase):
    def test_enroll_confirm_gate_and_replay(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            user = make_user(srv, key)
            uid, rtok = user["id"], user["token"]
            biz1, biz2 = make_business(srv, key), make_business(srv, key)
            # Before enrolment: the named token works (pre-WS3 behaviour).
            st, r = registry_decide(srv, key, biz1, rtok)
            self.assertEqual(st, 200, r)
            # Enrol: the TOTP seed is shown once, MFA pending until confirmed.
            st, enr = call(srv, "POST", f"/v1/users/{uid}/mfa/enroll", {}, key=key)
            self.assertEqual(st, 200, enr)
            sec = enr["secret"]
            self.assertIn("otpauth://totp/", enr["otpauth_uri"])
            # Wrong-code confirmation fails closed.
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/confirm", {"code": wrong_code_for(sec)}, key=key)
            self.assertEqual(st, 401, r)
            # Confirm with the current code: MFA activates. (Confirm
            # consumes this counter.)
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/confirm", {"code": MFA.totp(sec)}, key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["mfa"], "enabled")
            # Privileged action WITHOUT a code: refused.
            st, r = registry_decide(srv, key, biz2, rtok)
            self.assertEqual(st, 401, r)
            self.assertEqual(r["error"]["code"], "mfa_required_or_invalid")
            # With a WRONG code: refused.
            st, r = registry_decide(srv, key, biz2, rtok, totp=wrong_code_for(sec, at_time=time.time() + 30))
            self.assertEqual(st, 401, r)
            # With the NEXT step's valid code: allowed. (Next step,
            # because the current step's code was consumed at confirm.)
            code_next = MFA.totp(sec, at_time=time.time() + 30)
            st, r = registry_decide(srv, key, biz2, rtok, totp=code_next)
            self.assertEqual(st, 200, r)
            # REPLAY of the same code on another action: refused.
            biz3 = make_business(srv, key)
            st, r = registry_decide(srv, key, biz3, rtok, totp=code_next)
            self.assertEqual(st, 401, r)
            # The pre-MFA current-step code is also dead (counter consumed).
            st, r = registry_decide(srv, key, biz3, rtok, totp=MFA.totp(sec))
            self.assertEqual(st, 401, r)

    def test_reset_is_admin_only_and_fails_closed(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            user = make_user(srv, key)
            uid, rtok = user["id"], user["token"]
            st, enr = call(srv, "POST", f"/v1/users/{uid}/mfa/enroll", {}, key=key)
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/confirm", {"code": MFA.totp(enr["secret"])}, key=key)
            self.assertEqual(st, 200, r)
            # A reviewer token alone cannot reset its own MFA (the
            # endpoint requires the tenant API key): 401, still enabled.
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/reset", {},
                         raw_headers={"X-Reviewer-Key": rtok})
            self.assertEqual(st, 401, r)
            biz = make_business(srv, key)
            st, r = registry_decide(srv, key, biz, rtok)
            self.assertEqual(st, 401, r)  # still gated
            # Tenant admin reset works and is the ONLY recovery: MFA is
            # cleared (no bypass code issued) and the action works
            # again under the named token until re-enrolment.
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/reset", {}, key=key)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["mfa"], "reset")
            st, r = registry_decide(srv, key, biz, rtok)
            self.assertEqual(st, 200, r)
            # Confirm with nothing pending -> 409 (no silent state).
            st, r = call(srv, "POST", f"/v1/users/{uid}/mfa/confirm", {"code": "123456"}, key=key)
            self.assertEqual(st, 409, r)

    def test_require_mfa_policy_blocks_unenrolled_reviewers(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            user = make_user(srv, key)
            biz = make_business(srv, key)
            os.environ["KYC_REQUIRE_REVIEWER_MFA"] = "1"
            try:
                st, r = registry_decide(srv, key, biz, user["token"])
                self.assertEqual(st, 403, r)
                self.assertEqual(r["error"]["code"], "mfa_enrollment_required")
                # The tenant API-key fallback identity (tenant admin
                # credential itself) is not TOTP-gated.
                st, r = call(srv, "POST", f"/v1/businesses/{biz}/registry",
                             {"status": "confirmed", "reason": "admin action"}, key=key)
                self.assertEqual(st, 200, r)
            finally:
                os.environ.pop("KYC_REQUIRE_REVIEWER_MFA", None)

if __name__ == "__main__":
    unittest.main()
