"""Deterministic decision engine. FAIL CLOSED.

A session is auto-approved ONLY if every required check for its level
(per the tenant's active flow config) is 'pass' AND the explainable risk
score is at or below the config's auto-approve ceiling (band 'low').
Hard fails (expired document, underage) auto-reject. Everything else
that is not a clean pass routes to a human (needs_review).

Phase 2/3: face_match / liveness (Phase 2) and poa / screening
(Phase 3) are real checks now. A check that is 'not_run', 'error',
'unclear' or 'fail' still blocks auto-approval — the invariant has not
moved since Phase 1; what changed is that the checks actually run.
Required-check lists live in server/flowconfig.py (tenant-configurable,
versioned); the defaults below mirror them for direct unit use.
"""
from . import RULES_VERSION
from .flowconfig import DEFAULT_REQUIRED

REQUIRED = DEFAULT_REQUIRED
HARD_FAIL_REASONS = {"document_expired", "underage"}

# Fraud/risk signals are NOT required checks and never auto-reject. An
# *elevated* signal only routes an otherwise-clean case to a human.
ELEVATED_SIGNAL_REASONS = {"velocity_high", "ip_document_country_mismatch", "injection_signal_present"}

def decide(level, check_results, config=None, risk_score=None):
    """check_results: {type: {"status":..., "reason_codes":[...]}}.
    config: the tenant's active flow config dict (or None for defaults).
    risk_score: output of server/risk.py compute_risk (or its score).
    Returns (outcome, reason_codes). Pure function — unit-tested."""
    reasons = []
    for c in check_results.values():
        reasons.extend(c.get("reason_codes", []))
    hard = [r for r in reasons if r in HARD_FAIL_REASONS]
    if hard:
        return "rejected", sorted(set(hard))
    if config and config.get("required_checks"):
        required = list(config["required_checks"])
    else:
        required = REQUIRED.get(level, REQUIRED[2])
    not_pass = [t for t in required if check_results.get(t, {}).get("status") != "pass"]
    elevated = sorted(set(reasons) & ELEVATED_SIGNAL_REASONS)
    ceiling = 20
    if config and config.get("risk_auto_approve_ceiling") is not None:
        ceiling = config["risk_auto_approve_ceiling"]
    score = None
    if isinstance(risk_score, dict):
        score = risk_score.get("score")
    elif isinstance(risk_score, (int, float)):
        score = risk_score
    risk_block = score is not None and score > ceiling
    if not not_pass and not elevated and not risk_block:
        return "approved", []
    review_reasons = sorted(set(reasons + [f"{t}_not_pass" for t in not_pass]))
    if risk_block:
        review_reasons.append("risk_above_auto_approve_ceiling")
    return "needs_review", sorted(set(review_reasons))

def required_for(level, config=None):
    if config and config.get("required_checks"):
        return list(config["required_checks"])
    return list(REQUIRED.get(level, REQUIRED[2]))
