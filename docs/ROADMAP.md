# KYC — Roadmap

*Each phase ships only when its acceptance criteria pass on real devices
and real test data. A phase is not "done" because its code exists.*

## Phase 0 — Blueprint ✅ DONE

- [x] Repo created (public, owner's instruction): kilomene/KYC
- [x] Full blueprint, architecture, data model, API draft, compliance,
      security, roadmap, open decisions — in this repo
- [x] Owner decisions in DECISIONS.md answered (2026-10-26, incl. the
      expanded worldwide coverage correction the same day)
- **Exit:** ✅ owner approved the blueprint and Phase 1 ("Approve it —
  go with the recommendations and start Phase 1", 2026-10-26).

## Phase 1 — MVP: hosted flow + manual review ✅ BUILT LOCALLY (2026-10-26)

The smallest *real* product: a tenant can verify a real person end-to-end,
with humans making the final call while automation assists.
Built local-first (Python stdlib + Pillow + tesseract, SQLite, local
private storage) behind the docs/API.md contract. Not deployed anywhere.

- [x] Tenant creation, API keys (test/live, hashes only, shown once,
      revocable), webhook endpoints with HMAC-signed deliveries, logged.
- [x] Hosted applicant flow: consent, details, document capture, selfie
      capture, status — **resumable sessions** (reopening the link keeps
      uploaded steps). Document coverage per DECISIONS D3 as expanded:
      passports for all 16 launch countries; licence/national ID for
      NG/GB/US/CA/AU/DE/GH (`SUPPORTED_DOCUMENTS` map in server/app.py).
- [x] Capture-quality, OCR + MRZ (check digits), expiry/age and
      cross-field consistency checks — all real, all tested. Plus
      proportionate risk signals at submit (IP country vs document
      country, user-agent/device class, tenant velocity) stored as a
      structured `fraud_signals` check — signals route to review when
      elevated, never auto-reject.
- [x] Review console v1: queue, side-by-side document + selfie case view
      (audited image endpoint), approve / reject / request-more,
      **reason mandatory**, full append-only audit log.
- [x] Decision states + fail-closed engine + signed webhooks; test/live
      env separation (sandbox = data separation with the *same real
      checks* — no faked deterministic outcomes).
- [x] Retention helper (CLI) and applicant erasure — both run and tested,
      deletion verified in the filesystem, not just the UI.
- [x] Tests: `python3 -m unittest discover tests` (38 tests, green) and
      `scripts/e2e_local.py` live end-to-end run (green).
- **Acceptance — met:** two tenants fully isolated (tested); an unrun /
  error / unclear required check can never produce an approval (tested);
  deletion actually deletes (tested). **Not yet done:** end-to-end run on
  a physical low-end Android phone over a slow connection (needs the
  owner's phone test after a deploy exists).
- **Deliberately NOT in Phase 1:** face match / liveness (Phase 2 —
  recorded `not_run`, which blocks Level 2/3 auto-approval and sends the
  case to the human side-by-side comparison), document authenticity
  beyond OCR/MRZ/consistency (Phase 2), PoA + screening (Phase 3), KYB
  (Phase 3), billing, webhook backoff/replay.

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
