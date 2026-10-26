"""Reviewer MFA: TOTP second factor (RFC 6238), stdlib only.

Implemented directly on hmac/hashlib — no new dependency. Secrets are
160-bit, base32-encoded, generated with `secrets`. Verification uses
a ±1 step window (90 s of clock tolerance) and replay protection: the
caller stores the highest consumed counter per user and passes it in;
a code whose counter was already consumed never verifies twice.

Policy (enforced in server/app.py, documented in docs/SECURITY.md):
  * A reviewer WITH MFA enabled must present a valid code in the
    `X-Reviewer-TOTP` header on privileged actions (case decide /
    confirm / hit disposition, KYB registry decision). Missing,
    wrong, expired or replayed code -> 401, fail closed.
  * A reviewer WITHOUT MFA enrolled keeps working (named-token auth
    is the pre-WS3 behaviour) UNLESS the operator sets
    KYC_REQUIRE_REVIEWER_MFA=1 — then privileged actions are refused
    with 403 until the reviewer enrols. Fail closed by configuration.
  * Recovery fails closed: there is no bypass code and no self-service
    reset. A tenant admin (API key, audited) resets a user's MFA via
    POST /v1/users/{id}/mfa/reset, which clears the secret and forces
    re-enrolment. A reviewer token alone cannot reset its own MFA.
"""
import base64, hashlib, hmac, secrets, struct, time

STEP = 30
DIGITS = 6
ISSUER = "Nova KYC"

def new_secret():
    """160-bit secret, base32 (RFC 4226/6238 standard encoding)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def _decode_secret(secret_b32):
    s = (secret_b32 or "").strip().upper().replace(" ", "")
    pad = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + pad)

def hotp(secret_b32, counter, digits=DIGITS):
    """RFC 4226 HOTP for one counter value."""
    key = _decode_secret(secret_b32)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)

def totp(secret_b32, at_time=None, digits=DIGITS):
    at_time = time.time() if at_time is None else at_time
    return hotp(secret_b32, int(at_time // STEP), digits)

def verify(secret_b32, code, at_time=None, last_counter=-1, window=1):
    """Verify a presented code. Returns the matched counter, or None.
    A match is accepted only when its counter is strictly greater
    than `last_counter` (the highest counter already consumed for
    this user) — that is what makes a captured code non-replayable.
    Codes are compared in constant time; malformed codes never match.
    """
    if not secret_b32 or not isinstance(code, str):
        return None
    code = code.strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    at_time = time.time() if at_time is None else at_time
    current = int(at_time // STEP)
    for counter in range(current + window, current - window - 1, -1):
        if counter <= last_counter:
            continue
        if hmac.compare_digest(hotp(secret_b32, counter), code):
            return counter
    return None

def provisioning_uri(secret_b32, account_name):
    """otpauth:// URI for authenticator enrolment (shown once, with
    the secret, at enrolment time only)."""
    from urllib.parse import quote
    label = quote(f"{ISSUER}:{account_name}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP}")
