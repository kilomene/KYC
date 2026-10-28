"""Deterministic decision engine. FAIL CLOSED, FULLY AUTOMATIC.

Owner's order (2026-10-26): this is AUTO verification, not a queue
for humans. In the standard document+selfie path the machine decides:

  * every required check passes AND the explainable risk score is at
    or below the tenant's auto-approve ceiling -> APPROVED.
  * any DECISIVE failure -> REJECTED, automatically:
      - a hard-fail reason (expired document, underage, or a
        submission made over a detected VPN/proxy),
      - any required check with status 'fail' (face mismatch,
        liveness static replay / face absent, MRZ check digits,
        suspected tamper, name/DOB mismatch, outdated PoA, blurred
        or invalid capture, ...),
      - document_framing 'unclear' -> reason document_quality_rescan
        (the live scanner gates capture on real document detection,
        so a submitted unclear framing is a bad capture, not a
        human's job),
      - any other required check left 'unclear' or 'not_run' at
        submit: the verification is incomplete or inconclusive —
        the applicant re-does it; nobody queues it for a human.

needs_review survives ONLY outside that standard path:
  * a screening hit is pending disposition (Level 3 — a human must
    dispose the hit; approval is blocked until then, app._decide),
  * tenant flow-config routing: risk score above the configured
    auto-approve ceiling, or an elevated fraud signal (signals route
    to a human; they never reject on their own),
  * a required check returned 'error': the PLATFORM failed (OCR
    binary missing, face models absent, ...) — an outage must not
    mass-reject applicants, so a human/ops looks.

document_framing is conditionally required: it decides document
sessions (the submit path always records it when a document was
captured). A credential-seeded session without a document has no
framing result — framing is evidence about one capture in one
session and is never inherited (server/credentials.py) — so its
absence there blocks nothing.

Required-check lists live in server/flowconfig.py (tenant-configurable,
versioned); the defaults below mirror them for direct unit use.

face_match applicability (Session-5 diagnosis, 2026-10-26): face_match
compares the selfie against the DOCUMENT PORTRAIT, so it can only
apply to document types that carry a portrait. The classification
template system (server/templates.py) is the single source of truth
for that fact — see face_match_applicable(). A face_match result
recorded with status "not_applicable" (the type carries no portrait)
neither fails nor blocks a decision; it is not an unclear read, it is
a check that does not exist for this document type. (Before this, a
portrait-less type auto-rejected at Level 2 forever: face_match could
only ever come back 'no face in document' -> unclear -> rejected.)
"""
from . import RULES_VERSION
from .flowconfig import DEFAULT_REQUIRED

REQUIRED = DEFAULT_REQUIRED
HARD_FAIL_REASONS = {"document_expired", "underage", "vpn_proxy_detected",
                     # NIN slip typed-number tally (owner's order,
                     # nin_slip only): the typed number must equal the
                     # number read off the slip; no claim at all is
                     # equally decisive — the tally is that type's
                     # corroboration, not an optional extra.
                     "nin_number_mismatch", "nin_number_not_provided"}

# Fraud/risk signals are NOT required checks and never auto-reject. An
# *elevated* signal only routes an otherwise-clean case to a human.
ELEVATED_SIGNAL_REASONS = {"velocity_high", "ip_document_country_mismatch", "injection_signal_present",
                           # WS7 fraud intelligence (2026-10-27):
                           # cross-session duplicates + coordinated
                           # velocity route to a human, never reject.
                           "duplicate_document", "duplicate_face_suspected",
                           "velocity_ip_high", "coordinated_abuse_suspected"}

def face_match_applicable(country=None, kind=None, template=None):
    """Whether face_match applies to a claimed document type at all:
    True unless the type's classification template says the document
    carries NO portrait (portrait_expected False).

    The template consulted is the FULL classification template from
    server/templates.py whenever one exists for the type — the full
    templates are the single source of truth. This matters today for
    nin_slip: get_template's COARSE fallback builder derives
    portrait_expected from `kind != "nin_slip"` (i.e. False), while
    the FULL (NG, nin_slip) template — written from the real layout,
    portrait zone and all — says True: current standard/premium slips
    DO print a portrait. Consulting the full template first keeps the
    two systems from disagreeing in the decision path; the coarse
    builder's contrary rule is flagged for reconciliation in
    templates.py itself.

    `template` may be passed directly (the dict get_template
    returned). Unknown types fail closed: face match still applies."""
    if template is not None:
        return bool(template.get("portrait_expected", True))
    if country and kind:
        from . import templates as TEMPLATES
        full = TEMPLATES.FULL_TEMPLATES.get(((country or "").upper(), kind))
        if full is not None:
            return bool(full.get("portrait_expected", True))
        tpl, _level = TEMPLATES.get_template(country, kind)
        if tpl is not None:
            return bool(tpl.get("portrait_expected", True))
    return True

def decide(level, check_results, config=None, risk_score=None):
    """check_results: {type: {"status":..., "reason_codes":[...]}}.
    config: the tenant's active flow config dict (or None for defaults).
    risk_score: output of server/risk.py compute_risk (or its score).
    Returns (outcome, reason_codes). Pure function — unit-tested."""
    reasons = set()
    for c in check_results.values():
        reasons.update(c.get("reason_codes", []))
    # 1. Hard fails are decisive, always.
    hard = sorted(reasons & HARD_FAIL_REASONS)
    if hard:
        return "rejected", hard
    if config and config.get("required_checks"):
        required = list(config["required_checks"])
    else:
        required = list(REQUIRED.get(level, REQUIRED[2]))

    def status(t):
        return check_results.get(t, {}).get("status")

    def applicable(t):
        # document_framing applies only when a framing result exists
        # (a document was captured in this session). See module docstring.
        # document_classification / data_consistency follow the same
        # rule: the app records them for every document session, so
        # absence means "not a document session" (e.g. credential
        # reuse), never a silent skip in the standard path.
        if t in ("document_framing", "document_classification", "data_consistency"):
            return t in check_results
        # face_match recorded "not_applicable" (the document type
        # carries no portrait — see face_match_applicable) is not a
        # missing or failed check: the comparison does not exist for
        # this type, so it can neither reject nor block.
        if t == "face_match" and status(t) == "not_applicable":
            return False
        # Same for mrz on document types that carry none (registry
        # fact — licences, ID cards, NIN slips): the check does not
        # exist for the type, so it can neither reject nor block.
        if t == "mrz" and status(t) == "not_applicable":
            return False
        return True

    # 2. Any required check that FAILED is decisive: automatic rejection
    #    with that check's own reason codes.
    decisive = []
    for t in required:
        if applicable(t) and status(t) == "fail":
            decisive.extend(check_results[t].get("reason_codes") or [f"{t}_failed"])
    # 3. Framing unclear -> automatic rejection (rescan), never review.
    #    Folded into the decisive set (not an early return) so a
    #    session that BOTH fails a hard check AND submitted an unclear
    #    frame reports every reason, rescan included.
    if "document_framing" in required and applicable("document_framing") and status("document_framing") == "unclear":
        decisive.append("document_quality_rescan")
        decisive.extend(check_results["document_framing"].get("reason_codes") or [])
    if decisive:
        return "rejected", sorted(set(decisive))
    # 4. Screening hit awaiting disposition -> a human disposes it (L3).
    if "screening_hit_pending" in reasons:
        return "needs_review", sorted(reasons)
    # 5. A required check ERRORED: the platform failed, not the
    #    applicant — route to a human/ops, never auto-reject.
    errored = [t for t in required if applicable(t) and status(t) == "error"]
    if errored:
        out = set(reasons) | {f"{t}_error" for t in errored}
        return "needs_review", sorted(out)
    # 6. Anything else not passed splits by WHY (2026-10-28, owner
    #    session 15 — a genuine applicant accumulated five inconclusive
    #    legs and the old single rule could only ever reject him):
    #    a. NOT RUN / MISSING required checks -> automatic rejection,
    #       unchanged: the verification is incomplete, and a risk
    #       score inflated BY the missing checks themselves must not
    #       park the case with a human — incomplete is rejected, not
    #       reviewed.
    #    b. face_match UNCLEAR -> automatic rejection with the rescan
    #       reasons: the document portrait was too weak or not
    #       detected, the flow coaches a closer re-scan, and the
    #       applicant CAN fix it by re-doing the capture. (Framing
    #       unclear is the other rescan class — rule 3 above.)
    #    c. Any OTHER required check UNCLEAR -> needs_review: the
    #       platform measured real evidence and could not conclude
    #       (a challenge movement half-made, a pulse a short clip
    #       could not carry, authenticity signals under the
    #       corroboration gate, an MRZ a document type does not
    #       print). Inconclusive evidence is a human's call — never
    #       an automatic rejection, never an automatic approval.
    missing = [t for t in required if applicable(t) and status(t) in (None, "not_run")]
    unclear = [t for t in required if applicable(t) and status(t) == "unclear"]
    if missing:
        out = set(reasons) | {f"{t}_not_pass" for t in missing + unclear}
        return "rejected", sorted(out)
    if unclear:
        if all(t == "face_match" for t in unclear):
            out = set(reasons) | {f"{t}_not_pass" for t in unclear}
            return "rejected", sorted(out)
        out = set(reasons) | {f"{t}_inconclusive" for t in unclear}
        return "needs_review", sorted(out)
    # 7. Tenant-config routing (all required checks passed): risk above
    #    the configured ceiling, or an elevated fraud signal, routes to
    #    a human. This is the config-requires-review path; signals never
    #    reject anyone.
    ceiling = 20
    if config and config.get("risk_auto_approve_ceiling") is not None:
        ceiling = config["risk_auto_approve_ceiling"]
    score = None
    if isinstance(risk_score, dict):
        score = risk_score.get("score")
    elif isinstance(risk_score, (int, float)):
        score = risk_score
    elevated = sorted(reasons & ELEVATED_SIGNAL_REASONS)
    risk_block = score is not None and score > ceiling
    if elevated or risk_block:
        out = set(reasons)
        if risk_block:
            out.add("risk_above_auto_approve_ceiling")
        return "needs_review", sorted(out)
    return "approved", []

def required_for(level, config=None):
    if config and config.get("required_checks"):
        return list(config["required_checks"])
    return list(REQUIRED.get(level, REQUIRED[2]))

# ---------- Verification layers (owner's "beyond" doctrine, 2026-10-26) --
# Every document verification must clear LAYERS, and the decision record
# must show HOW DEEP the verification actually went:
#   SURFACE  frame/detection + capture quality (framing, capture_quality)
#   TEXT     vision OCR of the printed fields
#   INTERNAL the document's encoded/hidden evidence: MRZ check digits,
#            MRZ<->VIZ agreement, decoded QR/PDF417 payload agreement,
#            authenticity signals (ELA/metadata/screen/portrait-region).
# Where a document type CARRIES internal data (registry mrz=true, or a
# machine-readable code was actually decoded from the image), the
# INTERNAL layer is REQUIRED for an automatic approval: unreadable
# internal data -> internal_data_unreadable; disagreeing internal data
# -> internal_mismatch; both auto-reject. A document type with no
# internal data and no decoded code records internal=not_available —
# honestly, instead of pretending the layer ran.

def _layer_status(statuses):
    ss = [s for s in statuses if s]
    if not ss:
        return "not_run"
    if any(s == "fail" for s in ss):
        return "fail"
    if all(s == "pass" for s in ss):
        return "pass"
    return "unclear"

def verification_layers(check_results, doc_entry=None, code_found=False):
    """-> (layers, forced_reason).

    layers: {"surface": ..., "text": ..., "internal": ...,
             "internal_required": bool, "internal_sources": [...]}
    forced_reason: "internal_data_unreadable" | "internal_mismatch" |
    None — when set, the caller MUST force an automatic rejection with
    this reason (the internal layer is decision-bearing)."""
    def st(t):
        return check_results.get(t, {}).get("status")
    surface = _layer_status([st("document_framing"), st("capture_quality"), st("document_classification")])
    text = _layer_status([st("ocr")])
    entry_mrz = bool(doc_entry and doc_entry.get("mrz"))
    internal_required = entry_mrz or bool(code_found)
    sources = []
    if entry_mrz:
        sources.append("mrz")
    if "mrz_viz_consistency" in check_results:
        sources.append("mrz_viz")
    if code_found:
        sources.append("code_decode")
    if "authenticity" in check_results:
        sources.append("authenticity")
    forced = None
    if entry_mrz and st("mrz") != "pass":
        # The type carries an MRZ but it is missing, unreadable, or its
        # check digits fail: the internal evidence cannot be trusted.
        internal = "fail"
        forced = "internal_data_unreadable"
    elif st("mrz_viz_consistency") == "fail" or st("code_decode") == "fail":
        internal = "fail"
        forced = "internal_mismatch"
    elif sources:
        internal = _layer_status([st("mrz"), st("mrz_viz_consistency"),
                                  st("code_decode") if code_found else None,
                                  st("authenticity")])
    else:
        internal = "not_available"
    layers = {"surface": surface, "text": text, "internal": internal,
              "internal_required": internal_required, "internal_sources": sources}
    return layers, forced

# ---------- Biometric combination evidence (2026-10-26) ----------
# The biometric decision is a COMBINATION, never one check: continuous
# face track + liveness challenge + track-based face match + capture
# quality + device signals + deepfake/anti-spoofing. all_passing is
# what an automatic approval requires; any_failed is informational
# here (the required checks themselves already rejected the session).

def biometric_evidence(check_results, client_findings=None):
    """-> {"components": {...}, "all_passing": bool, "any_failed": bool}.
    client_findings: server/deepfake.client_signal_findings output for
    the capture signals sent with the uploads (device_signals leg)."""
    def st(t):
        return check_results.get(t, {}).get("status") or "absent"
    comp = {"face_track": st("face_track"), "liveness": st("liveness"),
            "face_match": st("face_match"), "capture_quality": st("capture_quality"),
            "deepfake": st("deepfake")}
    cf = client_findings or {}
    motion = cf.get("motion") or {}
    if cf.get("virtual_camera_hit"):
        comp["device_signals"] = "fail"
    elif cf.get("track_label") or motion.get("samples"):
        comp["device_signals"] = "pass"
    else:
        comp["device_signals"] = "absent"
    # Addition 8(f) words the deepfake leg as "not failing" (its rPPG
    # leg is evidence-combining on short webm — measured unmeasurable
    # on the owner's real captures 2026-10-26, artifact leg clean):
    # an unclear deepfake result does not block the combination; a
    # FAILED one does (and has already auto-rejected as a required
    # check). Every other component must be present and passing —
    # except face_match recorded "not_applicable" (the document type
    # carries no portrait, so there is nothing to match against): a
    # non-existent comparison is satisfied by definition, never a
    # blocker.
    others_pass = all(v == "pass" for k, v in comp.items()
                      if k != "deepfake"
                      and not (k == "face_match" and v == "not_applicable"))
    return {"components": comp,
            "all_passing": others_pass and comp["deepfake"] in ("pass", "unclear"),
            "any_failed": any(v == "fail" for v in comp.values())}

# ---------- Document evidence combination (Addition 10C) ----------
# The mirror of biometric_evidence, for the document: every decision
# shows the combined independent document evidence it rests on —
# layout classification, text extraction, machine-readable data,
# portrait analysis, image quality, security features. The gates
# themselves live in the required checks + internal layer; this block
# is the auditable record of the combination.

def document_evidence(check_results, authenticity_findings=None):
    """-> {"components": {...}, "all_passing": bool, "any_failed": bool}."""
    def st(t):
        return check_results.get(t, {}).get("status") or "absent"
    mr = [st("mrz"), st("code_decode")]
    if "fail" in mr:
        machine = "fail"
    elif "pass" in mr:
        machine = "pass"
    elif "unclear" in mr:
        machine = "unclear"
    else:
        machine = "not_available"
    portrait = "not_available"
    for s in ((authenticity_findings or {}).get("signals") or []):
        if s.get("name") == "portrait":
            portrait = {"strong": "fail", "moderate": "unclear", "none": "pass"}.get(s.get("strength"), "not_available")
    comp = {"layout_classification": st("document_classification"),
            "text_extraction": st("ocr"),
            "machine_readable": machine,
            "portrait": portrait,
            "image_quality": st("capture_quality"),
            "security_features": st("authenticity")}
    return {"components": comp,
            "all_passing": all(v in ("pass", "not_available") for v in comp.values()),
            "any_failed": any(v == "fail" for v in comp.values())}
