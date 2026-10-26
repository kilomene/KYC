"""Deterministic decision engine. FAIL CLOSED.

A session is auto-approved ONLY if every required check for its level is
'pass'. Hard fails (expired document, underage) auto-reject. Everything
else that is not a clean pass routes to a human (needs_review).

Phase 1 note: face_match and liveness do NOT exist yet (Phase 2). They are
recorded as required checks with status 'not_run' for levels 2 and 3,
which by the invariant above blocks auto-approval and opens a review case
where a human compares the document image and the selfie side by side.
Level 3 additionally requires poa and screening, also 'not_run' in Phase 1.
"""
from . import RULES_VERSION

REQUIRED = {
    1: ["capture_quality", "ocr", "expiry_age", "consistency"],
    2: ["capture_quality", "ocr", "mrz", "expiry_age", "consistency", "face_match", "liveness"],
    3: ["capture_quality", "ocr", "mrz", "expiry_age", "consistency", "face_match", "liveness", "poa", "screening_sanctions"],
}
HARD_FAIL_REASONS = {"document_expired", "underage"}

# Fraud/risk signals are NOT required checks and never auto-reject. An
# *elevated* signal only routes an otherwise-clean case to a human.
ELEVATED_SIGNAL_REASONS = {"velocity_high", "ip_document_country_mismatch"}

def decide(level, check_results):
    """check_results: {type: {"status":..., "reason_codes":[...]}}
    Returns (outcome, reason_codes). Pure function — unit-tested directly.
    Rules are data (the maps above), not scattered conditionals, so a
    later risk engine can own this function without a rewrite."""
    reasons = []
    for c in check_results.values():
        reasons.extend(c.get("reason_codes", []))
    # Hard fails first: an expired document or an underage applicant is a
    # rejection regardless of anything else.
    hard = [r for r in reasons if r in HARD_FAIL_REASONS]
    if hard:
        return "rejected", sorted(set(hard))
    required = REQUIRED.get(level, REQUIRED[2])
    not_pass = [t for t in required if check_results.get(t, {}).get("status") != "pass"]
    elevated = sorted(set(reasons) & ELEVATED_SIGNAL_REASONS)
    if not not_pass and not elevated:
        return "approved", []
    review_reasons = sorted(set(reasons + [f"{t}_not_pass" for t in not_pass]))
    return "needs_review", review_reasons

def required_for(level):
    return list(REQUIRED.get(level, REQUIRED[2]))
