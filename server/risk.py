"""Explainable risk engine (Phase 2).

Every check result contributes NAMED points. Nothing is a black box:
the output lists exactly which check/reason contributed how much, the
sum is the score (capped at 100), and the band is a pure function of the
score. Bands feed ROUTING only (auto-approve requires band 'low'); risk
alone never rejects anyone — rejections stay with the decision
engine's decisive check outcomes (server/engine.py).
"""
# Points for specific reason codes (override the per-status base points).
REASON_POINTS = {
    "mrz_check_digit_failed": 40,
    "document_expired": 50,
    "underage": 50,
    "face_mismatch": 45,
    "liveness_static_replay": 45,
    "liveness_face_absent": 30,
    "suspected_tamper": 40,
    "suspected_recapture_or_edit": 40,
    "name_mismatch": 35,
    "dob_mismatch": 35,
    "screening_hit_pending": 30,
    "ip_document_country_mismatch": 25,
    "ip_country_mismatch": 15,
    "velocity_high": 25,
    "injection_signal_present": 15,
    "image_blurred": 15,
    "document_not_detected": 25,
    "document_too_small_in_frame": 15,
    "authenticity_signals_present": 15,
    "face_match_near_threshold": 12,
    "liveness_challenge_incomplete": 12,
    "mrz_viz_mismatch": 35,
    "code_decode_mismatch": 30,
    "document_on_screen": 35,
    "portrait_region_tamper": 25,
    "internal_data_unreadable": 30,
    "internal_mismatch": 30,
    "deepfake_suspected": 45,
    "virtual_camera_detected": 45,
    "deepfake_signals_present": 15,
    "document_classification_mismatch": 30,
    "data_inconsistency": 25,
    "altered_text_suspect": 25,
    "compositing_suspect": 25,
    "suspicious_edges": 15,
    "missing_pattern": 15,
    # Neutral unknowns (2026-10-26): recorded honestly on the case but
    # worth ZERO points — an unreachable intel lookup, a local/dev
    # request with no geo header, or a document without a decodable
    # code are availability facts, not applicant risk. Without these
    # explicit zeroes the generic unclear base points (8 each) stack
    # up and push provably clean sessions over the approve ceiling.
    "vpn_check_unknown": 0,
    "ip_country_unknown": 0,
    "no_machine_code_found": 0,
    "deepfake_not_run": 0,
    "face_track_not_run": 0,
}
STATUS_POINTS = {"fail": 20, "unclear": 8, "error": 10, "not_run": 10, "pass": 0}

def band_for(score):
    if score <= 20:
        return "low"
    if score <= 50:
        return "medium"
    return "high"

def compute_risk(check_results):
    """check_results: {type: {"status":..., "reason_codes":[...]}}.
    Returns {score, band, contributions:[{source, points, detail}]}."""
    contributions = []
    for ctype in sorted(check_results):
        res = check_results[ctype] or {}
        status = res.get("status", "not_run")
        reasons = list(res.get("reason_codes") or [])
        specific = [(r, REASON_POINTS[r]) for r in reasons if r in REASON_POINTS]
        if specific:
            for reason, pts in specific:
                contributions.append({"source": ctype, "points": pts, "detail": reason})
        else:
            pts = STATUS_POINTS.get(status, 10)
            if pts:
                detail = reasons[0] if reasons else f"{ctype}_{status}"
                contributions.append({"source": ctype, "points": pts, "detail": detail})
    raw = sum(c["points"] for c in contributions)
    score = min(100, raw)
    return {"score": score, "band": band_for(score), "contributions": contributions, "raw_points": raw}
