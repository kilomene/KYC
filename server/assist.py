"""Reviewer assist (Phase 3): a deterministic case pre-read.

Generated purely from the recorded evidence — no model, no guessing:
  * mismatches: concrete field-level conflicts in the check results
  * risk_summary: the risk engine's top contributions, in words
  * suggested_disposition + evidence_reasons: what the evidence points
    to. The console labels this "Assist — a human decides"; a suggestion
    never becomes a decision on its own.
"""

HARD_REJECT_REASONS = {"document_expired", "underage", "mrz_check_digit_failed",
                       "face_mismatch", "liveness_static_replay", "suspected_tamper",
                       "suspected_recapture_or_edit"}

def build_assist(check_results, required, pending_hits=0):
    """check_results: {type: {"status","reason_codes","findings"}}.
    Returns {mismatches, risk_summary, suggested_disposition, evidence_reasons}."""
    mismatches = []
    for ctype, res in sorted(check_results.items()):
        status = res.get("status")
        if status in ("fail", "unclear", "error", "not_run"):
            for r in (res.get("reason_codes") or [f"{ctype}_{status}"]):
                mismatches.append({"check": ctype, "status": status, "reason": r})
    from .risk import compute_risk
    risk = compute_risk(check_results)
    top = sorted(risk["contributions"], key=lambda c: -c["points"])[:3]
    risk_summary = (f"Risk {risk['score']}/100 ({risk['band']})" +
                    (": " + "; ".join(f"{c['source']} +{c['points']} ({c['detail']})" for c in top) if top else " — no risk contributions."))
    reasons = []
    all_reasons = {r for res in check_results.values() for r in (res.get("reason_codes") or [])}
    hard = sorted(all_reasons & HARD_REJECT_REASONS)
    not_pass = [t for t in required if check_results.get(t, {}).get("status") != "pass"]
    if pending_hits:
        suggestion = "request_more"
        reasons.append(f"{pending_hits} screening hit(s) pending — disposition the hit(s) before deciding.")
    elif hard:
        suggestion = "reject"
        reasons += [f"Hard-fail evidence: {r}" for r in hard]
    elif not not_pass:
        suggestion = "approve"
        reasons.append("Every required check passed.")
        if risk["band"] != "low":
            suggestion = "request_more"
            reasons.append(f"But risk band is {risk['band']} ({risk['score']}/100) — look before approving.")
    else:
        suggestion = "request_more"
        reasons += [f"Check not passed: {t} ({check_results.get(t, {}).get('status', 'missing')})" for t in not_pass]
    return {"mismatches": mismatches, "risk_summary": risk_summary,
            "suggested_disposition": suggestion, "evidence_reasons": reasons,
            "label": "Assist — a human decides."}
