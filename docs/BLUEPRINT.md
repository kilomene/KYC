# KYC — Full Product Blueprint

*Version 1 — 2026-10-26. This is the contract for what we build. When code
and this document disagree, this document is wrong or the code is wrong —
one of them gets fixed in the open, never silently.*

*STATUS (WS0 audit, 2026-10-26): design blueprint, not an implementation
report. Known divergences from the built system are recorded in
docs/CLAIMS-AUDIT.md — e.g. §4's file-upload fallback and passive-first
liveness were superseded by the owner's live-scanner spec (camera-only,
no upload path, active challenge), and §4's reviewer-path alternative
evidence is not part of the automatic standard path.*

---

## 1. Problem

Any business that opens accounts, moves money, pays out sellers, or lets
strangers transact must answer one question first: **is this person real,
and are they who they say they are?** Getting it wrong means fraud,
chargebacks, money laundering exposure, and regulators. Building the
answer yourself — document capture, OCR, forgery checks, face matching,
liveness, watchlist screening, human review, audit trails — is months of
specialist work that has nothing to do with your actual product.

## 2. Product promise

**Send us a person. Get back a defensible decision.**

- The applicant finishes in minutes, on a phone, with no app install.
- The business integrates once (hosted link, or API + webhooks) and never
  touches raw ID images unless it is entitled and needs to.
- Every decision can be explained afterwards: which checks ran, what each
  one found, who or what decided, and why.

## 3. Who exists in the system

| Actor | Who they are | What they do |
|---|---|---|
| **Applicant** | The person being verified | Completes the verification flow; can see their status; can request their data or its deletion through the tenant |
| **Tenant** | A business customer of KYC | Creates verification sessions, receives decisions, manages its API keys, billing, and its own reviewers |
| **Reviewer** | Tenant staff (or, later, KYC staff for managed review) | Works the review queue, inspects evidence, approves/rejects with reasons |
| **Tenant admin** | Tenant's owner/manager | Levels & rules for their account, team, webhooks, retention settings within allowed bounds |
| **Platform admin** | Us | Tenancy, abuse, system health, provider status. Sees applicant PII only under break-glass, audited access |
| **System** | The decision engine | Runs checks, applies the tenant's rules, proposes or makes decisions inside those rules |

## 4. The applicant journey (step by step)

1. **Entry.** Tenant creates a session and gives the applicant a link
   (hosted flow) or embeds the flow. Link is single-applicant, signed,
   expiring (default 24h, tenant-configurable 1h–7d), and revocable.
2. **Consent screen — before anything is collected.** Plain language:
   what will be collected, why, who receives the result, how long it is
   kept, and the applicant's rights. No consent, no flow. Consent is
   recorded (timestamp, text version, locale).
3. **Details.** Legal first/last name, date of birth, country of residence,
   and (level-dependent) address. Pre-filled by the tenant where known;
   applicant can correct before submitting.
4. **Document capture.** Camera-first with a file-upload fallback.
   Live guidance: glare, blur, corners cut off, wrong document type.
   The applicant can retake. Both sides for two-sided documents.
5. **Selfie + liveness.** Camera selfie. Liveness is passive-first
   (texture/depth/motion signals from a short capture), escalating to an
   active challenge (turn head / follow prompt) when passive signals are
   weak or risk is high. A still image upload alone **never** satisfies
   liveness at Level 2+.
6. **Proof of address (Level 3).** Utility bill, bank statement, or official
   letter: dated within the tenant's window (default 3 months), name and
   address matching the applicant.
7. **Review screen + submit.** Applicant sees what they submitted and
   confirms. Then a status page: *received → processing → result*, with
   the result routed to the tenant. The applicant is told the outcome
   category (approved / more information needed / not approved) without
   exposing fraud-rule detail that would teach evasion.
8. **Retry and expiry.** Fixable failures (blur, glare, expired session)
   get a clear retry path with attempt limits. Sessions that expire say
   so plainly; the tenant can re-issue.

Accessibility and inclusion requirements: works on low-end Android phones
and slow connections; capture guidance in plain language; large-text and
screen-reader support in the hosted flow; a document-refusal is never the
end — the reviewer path can accept alternative evidence a tenant allows.

## 5. The checks (each one defined)

Every check returns one of: `pass`, `fail`, `unclear`, `not_run` — plus
structured findings and a confidence where relevant. **No check returns a
bare number with no explanation.**

### 5.1 Document checks
- **Capture quality:** blur, glare, resolution, all corners visible,
  document fully in frame.
- **Classification:** document type and issuing country recognised and
  matching what the applicant selected / the level allows.
- **OCR extraction:** names, DOB, document number, expiry, MRZ where
  present. MRZ check digits validated mathematically.
- **Cross-field consistency:** OCR face-page vs MRZ vs barcode (where a
  barcode exists and is readable) agree; name/DOB match the details the
  applicant entered (with transliteration tolerance, logged).
- **Expiry & validity:** document not expired; applicant age derived from
  DOB meets the tenant's minimum (default 18).
- **Authenticity signals:** template match for known documents, font /
  layout anomalies, photo-substitution signs, screen-recapture signs
  (moiré, bezel), digital-tamper signals on uploaded files, duplicate
  document presented by other applicants (fraud signal, see 5.5).

### 5.2 Biometric checks
- **Face detection & quality** on both the document portrait and selfie:
  one face, facing camera, eyes visible, no sunglasses/mask at capture.
- **Face match:** selfie face compared to document portrait; similarity
  score against a published-per-level threshold. Near-threshold = human
  review, never auto-pass and never auto-fail on score alone.
- **Liveness:** passive signals first; active challenge on escalation.
  Replay, screen, mask, and deepfake-injection signals are part of the
  check output. Failed liveness can be retried within attempt limits,
  then goes to review — it is not silently bypassed.

### 5.3 Data checks
- **Email / phone:** format, reachability signals, age/velocity abuse
  signals where a lawful data source exists. These are risk signals,
  not identity proof on their own.
- **Proof of address:** OCR on the PoA document; issuer, date, name, and
  address extracted and matched; document-type allowlist per tenant.

### 5.4 Screening (Level 3 / KYB)
- **Sanctions & watchlists:** name + DOB screened against the lists the
  tenant's jurisdictions require (e.g. OFAC, UN, EU, UK HMT — the exact
  list set is configuration, recorded per check).
- **PEP and adverse media:** screened with fuzzy matching; every
  potential hit goes to a human. **A fuzzy name match alone never
  auto-rejects an applicant** — false positives are real people.
- **Re-screening:** optional ongoing monitoring; a new hit on an approved
  applicant raises a case for the tenant.

### 5.5 Fraud & velocity signals
- Same document, same face, same device, or same contact details across
  many applicants; impossible travel / IP-country vs document-country
  mismatch; emulator / virtual-camera / rooted-device signals; session
  velocity per tenant. Signals raise risk and route to review; they are
  evidence, not verdicts.

## 6. The decision engine

- **Rules, not vibes.** Each tenant + level has an explicit rule set:
  which checks are required, which findings auto-reject (e.g. expired
  document, confirmed sanctions hit), which route to review (e.g.
  near-threshold face match, unclear authenticity), and which pass.
- **States:** `created → in_progress → submitted → processing →
  (approved | rejected | needs_review | needs_more_information |
  expired | cancelled)`. Every transition is timestamped and audited.
- **Fail closed:** a required check that errors, times out, or a provider
  outage = `needs_review` at best. Downstream, tenants are told a check
  is degraded; we never dress an unrun check as a pass.
- **Reasons are structured.** Decisions carry reason codes (e.g.
  `document_expired`, `face_match_low`, `liveness_failed`,
  `sanctions_hit_confirmed`) that tenants can act on and applicants can
  be told about at the right level of detail.
- **Reviewer supremacy.** A reviewer decision overrides the engine, with
  a mandatory reason. Overrides are first-class audit events.

## 7. The review console (tenant dashboard)

- **Queue:** cases sorted by SLA/risk, filterable by level, country,
  reason, age of case. Claim/lock so two reviewers never work one case
  blind.
- **Case view:** side-by-side document images and selfie, extracted
  fields vs entered fields, every check result with findings, screening
  hits with source data, fraud signals, prior applications by the same
  person/document, full audit timeline.
- **Actions:** approve, reject (reason required), request more
  information (applicant gets a fresh link for just the missing piece),
  escalate. Bulk actions never apply to identity decisions.
- **Four-eyes option:** tenants can require a second reviewer for
  approvals that override an engine rejection or a screening hit.
- **Operations views:** volumes, pass/review/reject rates, median times,
  check-level failure rates — so a tenant can spot a broken flow or a
  fraud attack early.

## 8. Tenant integration

- **Hosted flow (no-code):** create a session in the dashboard, send the
  applicant the link. Result by dashboard + email/webhook.
- **API:** sessions, applicants, status, decisions, webhooks (see
  docs/API.md). Sandbox mode with test documents and deterministic
  outcomes — clearly sandboxed, never touching production data.
- **Webhooks:** signed (HMAC), retried with backoff, replayable from the
  dashboard, with a delivery log.
- **Keys & environments:** separate live/test API keys, scoped, rotatable,
  revocable. A leaked key can be killed in one click.

## 9. KYB (business verification) — Phase 3 scope

Company registry lookup (registration number, status, address,
directors), document upload fallback where no registry API exists,
identification of directors and ultimate beneficial owners (≥25% or
tenant threshold), each UBO verified at Level 2+, and a business risk
decision assembled from the company check + the people checks.

## 10. Pricing shape (proposal — owner decides, see DECISIONS.md)

- Per-verification pricing by level (Basic < Standard < Enhanced),
  screening/monitoring as add-ons, KYB priced per business + per UBO.
- A free sandbox forever; first live verifications on a starter bundle.
- No charge for sessions that expire untouched or fail on our error.

## 11. What "the very best" means here — our differentiators

1. **Honest decisions.** Fail-closed engine, reason codes everywhere,
   human review that actually exists. We compete on trustworthiness of
   the decision, not on approving everyone fastest.
2. **Built for the phones people actually have.** Low-end Android,
   bad light, slow data — capture guidance and retries designed for it,
   Nigeria-first document coverage done properly, not as an afterthought.
3. **Reviewer experience.** The console is a product, not an admin page:
   fast, side-by-side, keyboard-driven, four-eyes where it matters.
4. **Privacy as a feature.** Minimum collection, clear consent, retention
   limits, deletion that works — tenants can show their users our flow
   with confidence.
5. **One integration, every level.** Basic to KYB behind the same session
   and webhook contract.

## 12. Explicitly out of scope (v1)

- Credit checks / credit scoring.
- Background checks (criminal, employment, education).
- Age estimation without a document.
- Verifying anyone without their knowledge and consent.
- Selling or sharing applicant data across tenants. **Never.**
- Any certification claim we do not hold.

## 13. Success measures

- Applicant completion rate and median time-to-complete, by device class.
- First-pass approval rate; review rate; reviewer overturn rate (too high
  = engine is weak, too low = reviewers are rubber-stamping).
- Fraud caught post-decision (tenant-reported) per 1,000 approvals.
- Decision latency: p50 under 2 minutes for automated Level 2 when no
  review is needed; review SLA configurable per tenant.
- Zero tolerance measures: unrun check marked pass (must be 0),
  unaudited PII access (must be 0), cross-tenant data exposure (must be 0).
