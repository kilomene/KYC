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
- Paper-document geometry + detection (rectification 2026-10-26, after
  the owner's real NIN slip failed the live scanner at a card-style
  1.41 aspect gate): registry carries aspect RANGES for paper/booklet
  types (NG nin_slip 1.2–2.8, guide 2.0; ZA green_id_book booklet);
  client paper detector in flow.html (luminance segmentation, bowed
  quadratic borders, paper thresholds side ≥ 0.30 / mean ≥ 0.45,
  canvas-squash aspect correction) with the card path unchanged and
  the screen refusal keeping precedence; server framing is
  multi-strategy with texture/border/ring gates (segmentation quads
  must meet pass size bars), and OCR/classification/extraction read
  the perspective warp when a check-grade quad exists.
  (server/docregistry.py, public/flow.html, server/framing.py,
  server/vision.py, server/templates.py, server/fieldtemplates.py;
  tests/test_paper_detection.py + tests/detector_harness.js) —
  IMPLEMENTED, measured on the owner's frames
  (data/owner-frame-proof/proof.json): clearer frame — framing pass
  (aspect 2.204), client doc_hold, classification 100/100, surname +
  given names extracted; darker frame — client doc_hold, server
  framing fail. **Honest limit:** the NIN digits themselves do not
  OCR from the owner's capture (grey print under the NIMC watermark;
  20+ OCR configurations tried) — the number field stays unextracted
  there rather than guessed; extraction is proven on a synthetic
  layout-faithful slip. Aadhaar was NOT converted to a paper range
  (the registry type is the PVC card layout; the A4 printout is a
  different layout), nor the Ghana voter card (a fixed-size cut card)
  or the French pink paper licence (insufficient layout research).
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
  IMPLEMENTED at that stated depth, no deeper. **WS1 update
  (2026-10-26): FULL layout templates now cover every registry type;
  non-NG/US passports use the generic TD3 template; the coarse
  fallback remains only for future untemplated types, and findings
  state the level that ran.**
- Per-document field-extraction templates for every registry type
  (zones, label anchors incl. DE/FR/NL local labels, per-type number
  format validators, Verhoeff + NRIC check digits), recorded on the
  case as the `field_extraction` check. (server/fieldtemplates.py;
  test_fieldtemplates) — IMPLEMENTED (WS1)
- Payload semantics: AAMVA parsed in full with element format
  validation (semantic); Aadhaar secure QR decompressed and
  cross-checked (structural+consistency — UIDAI signature NOT
  verified); NG NIN-slip QR and PhilID QR structurally validated with
  cross-checks (issuers publish no payload grammar in the research
  corpus). (server/payloads.py; test_payloads) — IMPLEMENTED at the
  labelled depths (WS1)
- Labelled extraction-accuracy benchmark over a synthetic,
  template-conformant corpus with named degradations.
  (scripts/benchmark_vision.py; benchmarks/RESULTS.md;
  test_benchmark) — IMPLEMENTED with the synthetic-corpus limit
  recorded in RESULTS.md (WS1)
- FAR/FRR benchmark of the production face-match pipeline on the
  full LFW View-2 protocol (6,000 official pairs, real faces):
  EER 1.07%; at the production threshold 0.363 → FAR 0.10%,
  FRR 2.00%, accuracy 98.95%; protocol accuracy 99.13% ± 0.38%;
  simulated condition slices (dark/downscale/blur, labelled).
  Threshold verdict from the measured curve: 0.363 KEPT;
  high-assurance option 0.413 recorded. (scripts/
  benchmark_biometrics.py; benchmarks/BIOMETRICS.md +
  biometrics.json; test_biometrics_benchmark) — IMPLEMENTED with
  the corpus limit recorded (funneled LFW is pre-cropped faces;
  demographic slicing UNMEASURED — LFW carries no attributes)
  (WS2)
- Presentation-attack suite against the production defences:
  replay family on REAL artefacts (genuine videos vs fresh
  challenges, liveness passed 0/6); print/screen/mask/deepfake
  families SIMULATED with documented methods — physical masks and
  DNN face-swap corpora UNMEASURED (cannot be produced here).
  No artefact auto-approved; per-family rejected/blocked rates in
  benchmarks/BIOMETRICS.md. (scripts/benchmark_attacks.py;
  benchmarks/attacks.json; test_attacks) — IMPLEMENTED at the
  labelled depths (WS2)
- rPPG hardened to POS + CHROM + green under a signal-quality gate;
  re-measured on the owner's real captures — plausible POS peak,
  still below the evidentiary bar on 4.5 s clips, so the leg
  remains evidence-only (attack suite also measured it firing on
  jittered photo presentations). Flow liveness window extended to
  ~9 s at raised bitrate. (server/deepfake.py; public/flow.html;
  test_rppg) — IMPLEMENTED, claim stays at evidence-only (WS2)
- Detection/embedding work space capped at 1024 px
  (server/face.py `work_image`): YuNet boxes measurably shrink/
  drift with input size and break SFace alignment on
  multi-megapixel stills (scale sweep in BIOMETRICS.md §4). A
  far/angled document portrait can still go undetected → face
  match *unclear*, fail closed. — IMPLEMENTED (WS2)
- Provider adapter: own SFace pipeline is provider #1 through
  server/bioprovider.py (the WS2 benchmark runs through it);
  external slots fail closed (`provider_not_configured`). A real
  external head-to-head needs vendor accounts/API keys held by the
  operator — the D5 evaluation remains OPEN, not faked.
  (test_bioprovider) — IMPLEMENTED as labelled (WS2)
- KYB is format validation + document + reviewer confirmation, with NO
  live government registry connection — labelled that way in the API,
  console, and README. — IMPLEMENTED as labelled
- Screening runs against the list files actually loaded; the real OFAC
  SDN list loads via scripts/fetch_ofac.py; no lists → `error`, never a
  silent pass. PEP/adverse-media exist only when such a list is loaded.
  — IMPLEMENTED as labelled
- Signed webhooks with retries (exponential backoff), dead-letter
  state, operator replay and an SSRF delivery guard — reusable
  HMAC-signed verified credentials (claims only), four-eyes review,
  retention CLI, applicant erasure. — IMPLEMENTED (WS3)
- Reviewer TOTP MFA (RFC 6238, replay-protected) gating privileged
  reviewer actions; API rate limits (per-key / per-flow-token / per-IP)
  with real `429` + `Retry-After` and a request-body cap (`413`);
  stored media encrypted at rest (AES-256-GCM envelope, master key in
  env/file only); checksummed backups with a measured restore drill.
  Proven by tests/test_isolation.py, tests/test_mfa.py,
  tests/test_ratelimit.py, tests/test_webhooks_retry.py,
  tests/test_encryption.py, tests/test_backup.py, scripts/
  pentest_local.py (32/32) and benchmarks/BACKUP-RESTORE.md. —
  IMPLEMENTED (WS3)

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

- **WS1 — Fortified Vision, finished. CLOSED 2026-10-26** (numbers in
  benchmarks/RESULTS.md): registry merge done (researched KE/ZA/IN/
  PH/SG/AE/FR/NL/IE types + AU/CA photo cards + GB PASS card, incl.
  the ZA green-book validity window, enforced by the expiry check);
  field-extraction templates for every registry type; FULL
  classification templates for every registry type; payload semantics
  at labelled depths (AAMVA semantic; Aadhaar structural+consistency,
  UIDAI signature not verified; NIN-slip/PhilID structural — no issuer
  grammar is published in the research corpus). Remaining open inside
  WS1's scope: the benchmark corpus is synthetic (no licensed specimen
  corpus was available), so accuracy numbers bound the extraction
  wiring, not real-world documents; font-consistency calibration is
  still fixture-based, not corpus-calibrated.
- **WS2 — Biometrics, measured. CLOSED 2026-10-26** (numbers in
  benchmarks/BIOMETRICS.md): FAR/FRR benchmark on the full LFW
  protocol (EER 1.07%; production threshold 0.363 kept on measured
  evidence — FAR 0.10% / FRR 2.00%); presentation-attack suite at
  labelled depths (replay REAL; print/screen/mask-proxy/deepfake-
  morph SIMULATED); rPPG hardened (POS/CHROM/quality gate) and
  honestly still evidence-only; liveness window extended to ~9 s;
  detection-at-resolution defect found and fixed (1024 px work
  space). Remaining open inside WS2's scope: demographic fairness
  testing (COMPLIANCE §3) NOT done — LFW carries no demographic
  attributes and no lawfully downloadable attribute-labelled set
  was reachable, so no fairness numbers exist; physical-mask and
  DNN face-swap attack corpora UNMEASURED (cannot be produced in
  this environment); passive liveness not built (the measured
  movement challenge remains the mechanism); the D5 external
  provider head-to-head has NOT run — the adapter exists and fails
  closed, but a real evaluation needs vendor accounts/API keys;
  rPPG on the new ~9 s captures unmeasured until a real longer
  capture exists; a far/angled document portrait can still evade
  YuNet detection (face match returns *unclear*, fail closed).
- **WS3 — Security, verified. CLOSED 2026-10-26 with evidence.**
  Reviewer TOTP MFA built (RFC 6238; enrol/confirm/reset; privileged
  actions gated; replayed codes refused; audited admin reset is the
  only recovery and fails closed); rate limits built (429 +
  Retry-After; per-key, per-flow-token, per-IP) plus a 413 body cap;
  webhook retries with exponential backoff, dead-letter state,
  operator replay, and an SSRF guard that blocks non-public targets
  before any network call; stored media encrypted at rest (AES-256-GCM
  envelope; master key from env/file, never in DB/repo; migration
  verified count + spot-decrypt; reads fail closed without the key);
  backup script + restore drill EXECUTED (backup 272,010 bytes;
  restored copy boots, records readable, document decrypts
  byte-identical — benchmarks/BACKUP-RESTORE.md); tenant-isolation
  battery (9 tests) and scripted self-pen-test (32/32 probes, 0
  findings — docs/PENTEST.md) green. REMAINING inside WS3's scope,
  stated plainly: **no external penetration test yet** (the self-test
  was its precondition and is green); **no CI vulnerability
  scanning** (no CI pipeline exists); the **SQLite file itself is
  not encrypted** (media files are; the DB relies on host controls);
  the rate limiter is **per-process memory** (multi-process needs a
  shared store — WS5); DNS-rebinding TOCTOU on webhook delivery is
  a recorded low-severity open item; captures are type-checked but
  **not malware-scanned**; the app sets no CSP/HSTS headers itself
  (TLS terminates at Cloudflare).
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

## 6. Addendum — identity-from-document (2026-10-26, owner's order)

Post-WS3 build, owner-directed ("i'm only supposed to choose the kind
of document i want… OCR fills everything in"). IMPLEMENTED and covered
by `tests/test_identity_from_document.py` (19 tests):

- Applicants carry `identity_source` (`declared` default / `document`).
  The declared path is unchanged, including its validation. The
  document path creates applicants and sessions with NO pre-declared
  name/DOB (country still required).
- The hosted flow has NO name/DOB/number inputs anywhere (asserted by
  test against the shipped page). After the scan, the server reads
  the document (`POST /v1/flow/document/process`: framing, multi-pass
  OCR, MRZ, template extraction; trust order valid-MRZ > extraction >
  upload) and the flow shows the read-back for confirm-or-rescan.
  The documents row's `doc_*` fields are the server's read.
- Consistency semantics per path are implemented as documented in
  docs/API.md ("Identity source"), including document self-consistency
  (`doc_*_reads_disagree` reasons) and adoption of the read identity
  onto the applicant at decision time (empty fields only; a
  contradicted declaration is never overwritten).
- Proven end-to-end on synthetic fixtures with invented values: an
  NG passport session on the document path APPROVES with the
  applicant identity populated from OCR alone; the synthetic wide
  NIN slip reads back completely (no DOB required — the type prints
  none), self-agrees, and is adopted.
- Honest limits of this build, measured in the same tests: a document
  type that prints no DOB (standard NIN slip) gives the expiry/age
  check no DOB on the document path, so that check reports
  `dob_missing` (unclear) and the auto-decision engine treats the
  session as incomplete — age cannot be verified from that document
  alone, and no DOB is invented to fill the gap. Likewise the
  data-consistency matrix can only compare sources that exist; a
  single-source paper document compares the read-back read against
  the submit extraction (two pipeline runs) and nothing else.
