# KYC — Claims-vs-Code Audit (Phase 4, Workstream 0)

Date: 2026-10-26. Scope: every public or implementation-describing claim in
README.md, docs/*.md, public/*.html (the live landing page and flow copy),
docs/API.md, and the server module docstrings — checked against the code
that actually runs and the test suite that actually passes.

Status legend: **IMPLEMENTED** (built + covered by tests), **PARTIAL**
(built in a narrower form than the words suggest), **TARGET** (design or
roadmap language, not built), **CORRECTED** (was false or stale; fixed in
this workstream).

## 1. Headline claims verified as true

- Live camera scanner only; no gallery/file-upload path in the flow;
  detection-gated automatic capture; automatic back-side prompt for
  two-sided documents. (public/flow.html; test_live_scanner) — IMPLEMENTED
- Automatic decisions in the standard path; `needs_review` only for
  tenant-required review, L3 screening hits, KYB, and platform errors.
  (server/engine.py; test_autodecision) — IMPLEMENTED
- Per-country document registry driving validation, back-side prompts,
  expiry rules, and scanner aspect gates; no-expiry document types never
  fail on a missing expiry date. (server/docregistry.py) — IMPLEMENTED
- Multi-pass OCR with a dedicated MRZ-band pass, MRZ↔VIZ cross-validation,
  QR/PDF417 decoding with AAMVA cross-checks, verification layers
  (surface/text/internal) with the internal layer required where the
  document type carries one. (server/vision.py; test_vision) — IMPLEMENTED
- Screen/forgery evidence pack (moiré, pixel grid, gloss, gamut, portrait
  splice, font consistency, compositing edges, border edges, pattern
  presence). (server/authenticity.py; test_evidence_pack) — IMPLEMENTED
- Continuous face tracking with identity continuity, track-median face
  match, active movement-challenge liveness, deepfake evidence block,
  six-component biometric combination gate. (server/facetrack.py,
  server/deepfake.py, server/engine.py) — IMPLEMENTED, with the honest
  limit recorded in README: rPPG is evidence-only on short compressed
  clips; it measured no pulse on the owner's real captures.
- Voice guidance, phone-only desktop QR handoff, IP harvest with
  location-consistency risk, VPN/proxy hard gate. (public/flow.html,
  server/vpncheck.py; test_vpn_gate) — IMPLEMENTED
- Country-template document classification (full NG + US, generic TD3,
  coarse for the rest). (server/templates.py; test_classification) —
  IMPLEMENTED at that stated depth, no deeper.
- KYB is format validation + document + reviewer confirmation, with NO
  live government registry connection — labelled that way in the API,
  console, and README. — IMPLEMENTED as labelled
- Screening runs against the list files actually loaded; the real OFAC
  SDN list loads via scripts/fetch_ofac.py; no lists → `error`, never a
  silent pass. PEP/adverse-media exist only when such a list is loaded.
  — IMPLEMENTED as labelled
- Signed webhooks (one attempt, logged), reusable HMAC-signed verified
  credentials (claims only), four-eyes review, retention CLI, applicant
  erasure. — IMPLEMENTED

## 2. False or stale claims corrected in WS0

| Where | Claim | Truth | Fix |
|---|---|---|---|
| public/index.html (the LIVE landing page) | "Phase 1 local MVP… runs locally… not a public deployment"; face match/liveness/PoA/screening/KYB "not yet built" | All of it shipped; the service is live | Page rewritten with the real live capability list and the real honest-limits list |
| README status block | "Runs locally only — not deployed"; "97 automated tests" | Live at kyc.novamail.store via a Cloudflare tunnel to the origin service; suite is 169 tests | Status block rewritten; counts updated |
| README tenant creation | "Unauthenticated only in this local build" | The endpoint was still unauthenticated in production (see §3) | Endpoint gated (code fix) + docs updated |
| README verification levels | L1 = "document number format & expiry"; L3 included "duplicate & fraud signals" | L1 runs the full document pipeline; duplicate detection is NOT built | Table rewritten to the actual required checks; duplicate detection moved to WS7 where it belongs |
| README build rules | "A human can always review. Automation proposes" | Superseded by the owner's automatic-decision spec | Rewritten: automation decides; humans audit and override with reason + four-eyes |
| README product summary | Decision "sent to a human reviewer" as a normal outcome | Only the named exceptions route to a human | Rewritten with the exception list |
| README/registry coverage | "National ID" listed for GB/CA/AU/DE/GH and (in code) the US | A general national identity card does not exist as a document class in the US/UK/CA/AU | Generic `national_id` removed for US/GB/CA/AU in code + tests; kept for NG/DE/GH; coverage text rewritten |
| docs/API.md | Error shape includes `request_id`; `429` rate limits; `Idempotency-Key` honoured | None of the three exist in the code | Corrected; marked as WS3/WS6 work |
| docs/API.md | `GET /v1/documents/{id}`, API-only upload endpoints, webhook replay listed beside implemented routes | Draft only | Each marked NOT IMPLEMENTED (draft) |
| docs/API.md | Erasure "async" | Synchronous | Corrected |
| docs/ARCHITECTURE.md | Supabase + Cloudflare Pages architecture presented as the plan | Supabase dropped (D4); built system is Python + SQLite + local storage behind a Cloudflare tunnel | Superseded banner added |
| docs/DATA-MODEL.md | Postgres/RLS, PII "encrypted at rest" | SQLite; isolation in application code; no column encryption yet | Status banner added |
| docs/SECURITY.md | §2 "baseline controls (from the first commit)" | Several are partial or unbuilt (see §4) | Status banner added; per-control status in §4 |
| docs/COMPLIANCE-AND-PRIVACY.md | Rules read as current behaviour throughout | Core rules implemented; exports/DPA/incident rehearsal/fairness testing/expiry watch are not | Status banner added |
| docs/BLUEPRINT.md | File-upload fallback; passive-first liveness; reviewer-path alternative evidence | Superseded by the owner's live-scanner spec | Status banner added |
| docs/AMBITION.md | "Passive liveness" as a fraud-depth component; "AI-prepared case summaries" | Active liveness only; assist is a deterministic pre-read | Status note added |
| docs/ROADMAP.md | "Built locally / not deployed" in present tense; old Phase 4 sketch | Live since 2026-10-26; Phase 4 governed by PHASE4-PLAN.md | Current-status banner added; Phase 4 section points to the plan |
| docs/DECISIONS.md D4/D5 | "Not deployed yet"; "plug a provider first" | Deployed via tunnel; own-model track shipped first, provider evaluation not yet run | Implementation-status notes added (decision text preserved) |
| server/__main__.py | CLI described as "KYC Phase 1 local MVP" | — | Description updated |
| server/app.py docstring | "Tenant creation is unauthenticated ONLY because this is the local MVP" | Was still true in production | Gate implemented; docstring corrected |

## 3. Security finding fixed in WS0 (not just documented)

**Open tenant bootstrap.** `POST /v1/tenants` required no authentication:
anyone on the internet could mint a tenant and receive live API keys.
Tenant isolation meant no other tenant's data was exposed, but the
platform itself was open for unauthenticated use. Fixed: the endpoint
now requires the platform operator token (`KYC_PLATFORM_ADMIN_TOKEN`
environment variable, presented as `X-Platform-Admin`); with no token
configured it returns 403 and tenant creation is disabled (fail closed).
Covered by `test_tenant_bootstrap_requires_platform_admin`. The systemd
unit takes the token from an optional `data/platform-admin.env` file.

## 4. Open gaps, assigned (the honest not-done list)

- **WS1 — Fortified Vision, finished.** Per-document field-extraction
  templates exist only for NG + US (generic TD3 + coarse elsewhere);
  semantic payload validation beyond AAMVA (NG NIN-slip QR, Aadhaar
  secure QR, PhilID QR) not built; no labelled accuracy benchmark;
  font-consistency calibration is fixture-based; registry facts for
  GB/CA/AU/DE/GH licences are generic ID-1 card facts pending the
  researched merge; state/provincial photo cards must be added as
  researched document types.
- **WS2 — Biometrics, measured.** No FAR/FRR benchmark; no
  presentation-attack suite results; demographic fairness testing
  (COMPLIANCE §3) not done; rPPG is evidence-only; passive liveness not
  built; the D5 provider-adapter evaluation has not run.
- **WS3 — Security, verified.** Reviewer authentication is named tokens,
  not MFA/password accounts; no rate limiting; webhook retries,
  dead-letter and replay not built; stored media is not encrypted at
  rest beyond host disk controls; no backup/restore test has run; no CI
  vulnerability scanning; no external penetration test; the app sets no
  CSP/HSTS headers itself (TLS terminates at Cloudflare); captures are
  type-checked but not malware-scanned or re-encoded.
- **WS4 — Authoritative data.** No live business-registry connection;
  sanctions coverage depends on locally loaded lists (OFAC SDN
  fetchable; PEP/adverse media not bundled); no national identity
  database integration; NFC chip reading not built (Android-only route).
- **WS5 — Production architecture.** Submit processing is synchronous
  (measured in tens of seconds under load on this VM); no staging
  environment; monitoring is a health hook, not full alerting; final
  Cloudflare-native hosting not done; no DR drill.
- **WS6 — Platform.** No embeddable SDK; no tenant self-serve dashboard
  beyond the review console; no usage metering or billing (blocked on
  the owner's D7 prices); idempotency keys not honoured.
- **WS7 — Fraud intelligence.** Duplicate face/document detection NOT
  built; velocity is a single basic signal (tenant sessions/hour);
  document-expiry watch not built; no cross-session coordinated-abuse
  signals.
- **WS8 — Independent assurance.** No SOC 2, iBeta, or ISO certification
  is held or claimed. These are earned only after WS1–WS3 measurements
  exist.

## 5. Audit rule going forward

No public sentence may claim a capability that is not IMPLEMENTED above
or in a later workstream's measured exit report. Design documents are
labelled as targets at the top; the README and the live landing page
describe only what runs.
