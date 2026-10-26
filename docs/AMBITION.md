# KYC — The Bar: More Advanced Than the Incumbents

*Owner's standing order, 2026-10-26: "Everything you will build, you
build it more advanced, even more advanced than the one we know. It will
be more advanced than Sumsub, Persona or Onfido."*

This is the quality target for every phase. It is a **target to earn, not
a claim to print**: we say "more advanced" in public only about a
specific capability we have built, tested, and measured against them.
Until then, this document is our internal scorecard.

*STATUS (WS0 audit, 2026-10-26): rows in the table below are targets.
Two need explicit correction against the built system: "passive
liveness" is NOT built (liveness is an active movement challenge;
passive liveness is Phase 4 WS2), and the reviewer assist is a
deterministic pre-read, not an AI summary. "AI-prepared case summaries"
remains a target. See docs/CLAIMS-AUDIT.md.*

## Where we intend to beat Sumsub, Persona, and Onfido

| Dimension | Incumbent weakness to exploit | Our target |
|---|---|---|
| Completion on real phones | Flows tuned for flagships and fast networks | Best-in-class completion on low-end Android + slow data: smart auto-capture, real-time guidance, progressive upload, **resumable sessions** — a dropped connection never restarts a verification |
| Emerging-market documents | African/Asian documents often second-class, higher false rejects | Nigeria/Africa/Asia document coverage as first-class citizens, tested per document, with per-document accuracy published internally |
| Decision explainability | "Declined" with thin reasoning | Every decision fully explainable: per-check findings, reason codes, rules version — for tenants, reviewers, and (at the right level) applicants |
| Reviewer speed | Consoles that make humans the bottleneck | Reviewer console faster than theirs: side-by-side evidence, AI-prepared case summaries (human still decides), keyboard-first, four-eyes only where risk demands it |
| Fraud depth | Single-shot checks | Layered defence: document authenticity + face match + passive liveness + deepfake/injection signals + device & velocity risk, combined in one explainable risk engine |
| Reusable identity | Users re-verify from zero at every business | **Verified-once identity**: with the applicant's consent, a completed verification can be re-shared to another Nova tenant as a signed, revocable credential — no raw images move, tenants get the decision + proof |
| Developer experience | Weeks of integration and sales calls | Self-serve sandbox with a realistic test-document generator, one link or one API call to start, live in an afternoon |
| Pricing honesty | Opaque, per-check nickel-and-diming | Transparent per-verification pricing; no charge for expired-untouched sessions or our errors |
| Privacy | Collect-everything defaults | Minimum collection, shortest retention, deletion that verifiably deletes — privacy as a selling point, not a policy page |

## Advanced capabilities on the roadmap (beyond the incumbents' basics)

1. **Explainable risk engine** — document, biometric, device, behaviour,
   and screening signals fused into one score where every point of risk
   names its source signal. (Foundation: Phase 1 data model; engine:
   Phase 2–3.)
2. **Deepfake & injection defence** — virtual-camera / emulator /
   replay / synthetic-face signals feeding liveness decisions.
   (Phase 2.)
3. **Reusable verified credential** — consent-based re-sharing across
   tenants, selective disclosure (prove "over 18, verified" without
   handing over the ID image), revocable by the applicant. (Phase 3.)
4. **No-code verification builder** — tenants compose flows per country
   and level (which documents, which checks, which thresholds) without
   code; every flow versioned like the rules engine. (Phase 3–4.)
5. **Reviewer AI assist** — case pre-read: extracted facts, cross-field
   mismatches highlighted, suggested disposition with its evidence.
   Suggestions never become decisions on their own. (Phase 3.)
6. **Continuous trust** — ongoing screening, document-expiry watch, and
   risk-triggered re-verification for already-approved users, instead of
   verify-once-and-forget. (Phase 3–4.)
7. **Unified KYC + KYB graph** — people and the businesses they own/run
   in one relationship view, so a business decision sees its humans and
   a human decision can see their businesses. (Phase 3–4.)

## What this order changes in Phase 1 (now)

- Architecture stays check-granular and rules-versioned (already in the
  blueprint) — nothing in Phase 1 may hard-code a decision that the risk
  engine will later need to own.
- Sessions are resumable from their link; risk signals (device, IP
  country, velocity) are collected proportionately and stored as
  signals, not silently acted on.
- The console and flow are built to the completion/speed targets above,
  not to "good enough for an MVP".

## The honesty rule (unchanged)

Advanced is proven, not declared: benchmarks, tests, and measured
completion/accuracy numbers — or it doesn't ship with the claim.
