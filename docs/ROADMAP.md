# KYC — Roadmap

*Each phase ships only when its acceptance criteria pass on real devices
and real test data. A phase is not "done" because its code exists.*

## Phase 0 — Blueprint (now)

- [x] Repo created (public, owner's instruction): kilomene/KYC
- [x] Full blueprint, architecture, data model, API draft, compliance,
      security, roadmap, open decisions — in this repo
- [ ] Owner decisions in DECISIONS.md answered
- **Exit:** owner approves the blueprint and the Phase 1 scope, in words.

## Phase 1 — MVP: hosted flow + manual review

The smallest *real* product: a tenant can verify a real person end-to-end,
with humans making the final call while automation assists.

- Tenant signup, dashboard, API keys (test/live), webhook endpoints.
- Hosted applicant flow: consent, details, document capture (passport +
  driver's licence + national ID for the launch countries in
  DECISIONS.md), selfie capture, status page.
- Capture-quality checks, OCR + MRZ extraction, expiry/age and
  cross-field consistency checks — all real, all tested.
- Review console v1: queue, side-by-side case view, approve / reject /
  request-more with reason codes, full audit log.
- Decision states + webhooks exactly as specced; sandbox mode.
- Retention jobs and applicant erasure working from day one.
- **Acceptance:** end-to-end run on a low-end Android phone over a slow
  connection; two tenants fully isolated (tested); an unrun check can
  never produce an approval (tested); deletion actually deletes
  (verified in storage, not just in the UI).

## Phase 2 — Automation: face match, liveness, authenticity

- Face match + liveness integrated behind the check interface;
  demographic performance testing per COMPLIANCE §3.
- Document authenticity signals beyond OCR (template, recapture,
  tamper signals).
- Decision engine auto-decides clean passes and clear fails; everything
  borderline routes to review.
- Fraud/velocity signals v1 (duplicate document/face/device per tenant,
  with privacy review before any cross-tenant signal is even considered —
  default: per-tenant only).
- **Acceptance:** published internal benchmarks (false accept / false
  reject on our test sets), reviewer overturn rate measured, provider
  outage drill → system degrades fail-closed.

## Phase 3 — Enhanced + KYB

- Proof of address, sanctions/PEP/adverse-media screening with human
  disposition of hits, ongoing monitoring + re-screening alerts.
- KYB: registry checks, directors/UBOs each verified at Level 2+.
- Four-eyes review option; reviewer roles and SLA tooling.

## Phase 4 — Scale & polish

- More document types/countries driven by tenant demand, each added with
  per-document tests before it is listed as supported.
- Embeddable SDK (JS/mobile web component) alongside the hosted flow.
- Billing automation per the pricing the owner settles in DECISIONS.md.
- Independent security audit + pen test report; compliance review per
  launch jurisdiction; certification path (e.g. SOC 2) **only** when the
  business is ready to actually earn it.

## Standing rule for every phase

Build and test locally first, watch it work, push once when green.
Real features only — if a check is listed, it runs.
