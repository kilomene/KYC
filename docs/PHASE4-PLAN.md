# Phase 4 Plan — from advanced scanner to certified-grade platform

Status: DRAFT for owner approval (presented 2026-10-26). Nothing in this
plan executes before the owner approves it. Ordering follows the owner's
sequence decision (2026-10-26): scanner build first, then this plan,
then execution. It also absorbs the independent repo assessment the
owner reviewed the same day, whose gaps matched our own not-done lists.

## Workstream 0 — Claims-vs-code audit (do first, it is cheap and honest)
- File-by-file audit: every README/docs claim checked against the code
  that actually runs (checks, engine, auth, tenant isolation, flow).
- Output: a written gap list — implemented / partial / documented-only —
  with each gap assigned to a workstream below. Fix the deployment lag
  in the README (the product is live; docs said "local").
- No feature work hides in this workstream; it only tells the truth.

## Workstream 1 — Fortified Vision OCR engine (the owner's headline)
- Per-document field-extraction templates for ALL 16 launch countries
  (today: NG + US full templates, generic TD3, coarse for the rest):
  field zones, label anchors, number formats per document type.
- Full semantic validation of decoded data: AAMVA payload parsing,
  NG NIN-slip QR payload, Aadhaar secure QR, PhilID QR.
- Labelled accuracy benchmark: a synthetic + licensed specimen corpus,
  field-level accuracy measured per document type, published internally
  with error bars. Font-consistency calibration completed against it.
- Exit measure: field-extraction accuracy numbers exist per priority
  document type; nothing is claimed without them.

## Workstream 2 — Biometric measurement and attack resistance
- FAR/FRR benchmark for face match + tracking: across lighting, device
  tiers, skin tones, age bands; thresholds set per use case from data,
  not defaults.
- Presentation-attack suite: printed photo, screen replay, video
  replay, mask, and a deepfake corpus run against liveness + tracking +
  deepfake signals; catch rates measured per attack family.
- rPPG hardening: longer/higher-quality capture window so the pulse
  signal can carry graded weight; today it is evidence-only because
  4.5s compressed clips measure weakly (proven on real captures).
- Passive-liveness evaluation and a provider-adapter interface so our
  models are benchmarked against specialist providers, not believed.

## Workstream 3 — Security hardening, verified not described
- Tenant-isolation test battery (API, DB, files, console) run as tests.
- Reviewer MFA + secure sessions (today: named tokens), role matrix
  enforced and tested; API-key rotation; rate limits + abuse controls.
- Webhook retries with backoff, dead-letter queue, replay protection.
- Encryption at rest for stored media, backup + RESTORE test,
  dependency/vulnerability scanning in CI; external penetration test
  commissioned when the above is green.

## Workstream 4 — Authoritative data (stop grading our own homework)
- Live business registries where access is authorized: NG CAC, UK
  Companies House, + US/CA/AU equivalents — replacing format-only KYB.
- Maintained sanctions/PEP/adverse-media sources with freshness stamps
  and false-positive handling (today: OFAC SDN only).
- National identity verification integrations where authorized
  (Nigeria first), reported honestly where no official API exists.
- NFC chip reading for e-passports/ID cards (Android route; iOS web
  cannot — stated in-product, never faked).

## Workstream 5 — Production architecture
- Heavy checks (OCR, biometrics, screening) moved to background jobs
  with queueing; staging environment with synthetic data; monitoring,
  alerting, incident runbook; disaster-recovery drill.
- Final hosting per decision D4: Cloudflare — with a benchmark of what
  stays on the origin server vs what can move to Workers, based on
  measured CPU/memory of the OpenCV/OCR/biometric workloads.

## Workstream 6 — Platform and business layer
- JavaScript SDK + mobile integration (the flow is phone-only by
  design), developer dashboard, test-key provisioning.
- Usage metering, tenant quotas, billing automation — BLOCKED on the
  owner's per-level prices (decision D7, still open).
- Idempotency keys, session-status polling, audit exports.

## Workstream 7 — Fraud intelligence network effects
- Duplicate face/document detection across sessions (privacy-preserving:
  hashed embeddings, no cross-tenant data exposure).
- Cross-session velocity and coordinated-abuse signals; risk-adaptive
  step-up: extra checks only when risk rises.

## Workstream 8 — Independent assurance (only when earned)
- SOC 2 readiness path; iBeta-style PAD evaluation for liveness;
  publish ONLY claims backed by Workstreams 1–3 measurements.
