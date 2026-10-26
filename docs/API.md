# KYC — API (v1)

*REST, JSON. Auth: tenant API key (`Authorization: Bearer <key>`) scoped
per environment. All timestamps UTC ISO-8601. All ids are opaque UUIDs.
The Phase 1 endpoints below are implemented as drafted; the Phase 2/3
section after the decision object documents what was added in the
2026-10-26 local build (implemented and covered by the test suite).
Unimplemented items are marked as such where they appear: API-only
document/selfie upload endpoints (the hosted flow is the only capture
path), the `GET /v1/documents/{id}` metadata endpoint, and idempotency
keys. Rate limiting, webhook retries/dead-letter/replay and reviewer
MFA were implemented in Phase 4 WS3 (2026-10-26) — see below.*

Platform bootstrap: `POST /v1/tenants` creates a tenant and its test/live
keys, and is **platform-operator only** — it requires the server-side
`KYC_PLATFORM_ADMIN_TOKEN` environment variable presented in the
`X-Platform-Admin` header. With no token configured it returns `403`
(tenant creation disabled). It is not part of the tenant API surface.

## Core flow

```
1. POST /v1/applicants            → create / upsert an applicant
2. POST /v1/sessions              → create a verification session
                                    response includes the hosted-flow URL
3. Applicant completes the flow    → captures happen inside the flow
   (an API-only upload integration is drafted below but NOT implemented)
4. Webhook: session.completed      → decision ready
   GET  /v1/sessions/{id}          → status + decision + reason codes
   GET  /v1/sessions/{id}/checks   → per-check results
```

## Endpoints (draft)

| Method & path | Purpose |
|---|---|
| `POST /v1/applicants` | Create applicant: declared name / DOB / country (+ optional external_ref), or `identity_source: "document"` with country only — see "Identity source" below |
| `GET /v1/applicants/{id}` | Applicant summary (no document images by default) |
| `DELETE /v1/applicants/{id}` | Erasure (audited, synchronous, confirmed by webhook `applicant.deleted`) |
| `POST /v1/sessions` | Create session: applicant_id, level, optional allowed document types/countries, expiry override. With `{identity_source: "document", country, level}` and no applicant_id, a document-sourced applicant shell is created inline (see "Identity source"). The response carries `applicant_id` and `identity_source` |
| `GET /v1/sessions/{id}` | Status, decision, reason codes, timestamps |
| `POST /v1/sessions/{id}/cancel` | Cancel a live session; its link dies immediately |
| `POST /v1/sessions/{id}/documents` | **NOT IMPLEMENTED (draft)** — API-only upload when not using the hosted flow |
| `POST /v1/sessions/{id}/selfie` | **NOT IMPLEMENTED (draft)** — API-only biometric capture upload |
| `GET /v1/sessions/{id}/checks` | Every check: type, status, findings, provider, timestamps |
| `GET /v1/documents/{id}` | **NOT IMPLEMENTED (draft)** — document metadata + extracted fields. (Implemented today: `GET /v1/documents/{id}/image`, tenant-authenticated and audited, used by the console case view) |
| `POST /v1/cases/{id}/decide` | Reviewer action via API (approve / reject / request_more) — reason mandatory |
| `GET /v1/cases` | Review queue for the tenant |
| `POST /v1/webhooks` / `GET /v1/webhooks` | Manage webhook endpoints |
| `POST /v1/webhooks/{id}/replay/{delivery_id}` | **NOT IMPLEMENTED (draft)** — replay a delivery |

## Phase 2/3 endpoints (implemented 2026-10-26)

Reviewer identity: console/API case actions accept an optional
`X-Reviewer-Key: <user token>` header (issued by `POST /v1/users`).
Without it, actions are recorded as the tenant API key identity
(role admin). An invalid presented token is refused with `401` —
it never silently falls back.

| Method & path | Purpose |
|---|---|
| `GET /v1/config?level=N` | Active flow config for the level: required_checks, face_pass_threshold, face_margin, risk_auto_approve_ceiling, poa_window_days, screening_threshold, sla_hours, four_eyes + its version (0 = built-in defaults) |
| `PUT /v1/config` | Body `{level, patch}` — validates and stores a NEW config version (old versions are kept; decisions record the `config_version` they ran under). Unknown keys / out-of-range values → `422` |
| `POST /v1/users` | Create a named tenant user `{name, role: admin\|reviewer}` → returns a per-user token ONCE (only its hash is stored) |
| `GET /v1/users` | List users (no tokens) |
| `POST /v1/users/{id}/revoke` | Revoke a user token |
| `POST /v1/users/{id}/mfa/enroll` / `/confirm` / `/reset` | Reviewer TOTP MFA — see "Reviewer MFA" below |
| `GET /v1/webhooks/deliveries` | Webhook delivery attempts incl. dead-letter state (`?status=` filter) |
| `POST /v1/webhooks/deliveries/{id}/replay` | Re-queue a failed/dead-lettered delivery (re-signed on send) |
| `POST /v1/cases/{id}/confirm` | Four-eyes confirmation of a parked decision `{reason}` — the confirmer must be a DIFFERENT reviewer identity than the first decider (`403` otherwise); required when a decision overrides an engine rejection or follows a false-positive hit disposition |
| `POST /v1/cases/{id}/hits/{hit_id}/dispose` | Screening-hit disposition `{disposition: confirmed\|false_positive, reason}` — `confirmed` rejects the session (`sanctions_hit_confirmed`); `false_positive` lets the case proceed but flags it four-eyes. Approving a case with a still-pending hit → `409` |
| `GET /v1/cases` | Review queue — now sorted by `sla_due_at` (cases carry an SLA, default +24h, from config) |
| `GET /v1/cases/{id}` | Case detail — now includes `screening_hits`, the issued `credential` (if approved), and a deterministic `assist` block: `{label: "Assist — a human decides.", mismatches[], risk_summary, suggested_disposition, suggestion_reasons[]}` |
| `POST /v1/businesses` | Create a KYB business `{legal_name, registration_number, country}` — the registration number is format-validated per country (NG/US/GB/CA/AU/DE/GH patterns); invalid format → `422` with the expected pattern |
| `GET /v1/businesses` / `GET /v1/businesses/{id}` | Businesses with people + per-person `verified_l2plus` status |
| `POST /v1/businesses/{id}/people` | Attach an applicant as `{applicant_id, role: director\|ubo\|officer, ownership_pct}` |
| `POST /v1/businesses/{id}/document` | Multipart company document upload (registry evidence) |
| `POST /v1/businesses/{id}/registry` | Reviewer registry decision `{status: confirmed\|rejected, reason}` — **format validation + document + human confirmation only; there is no live government registry connection in this build** |
| `POST /v1/businesses/{id}/evaluate` | Assemble the business decision: `verified` only when the registry leg is confirmed AND every attached person is approved at Level 2+ AND no person has a pending/confirmed screening hit; otherwise `pending`/`rejected` with named reasons |
| `POST /v1/monitoring/rescreen` | Re-screen all approved applicants of the tenant against the CURRENT lists. New matches → `monitoring_alerts` rows + `screening.hit_new` webhook + a reopened case. Returns `{screened, new_hits, alerts}` |
| `GET /v1/monitoring/alerts` | Monitoring alerts for the tenant |
| `POST /v1/credentials/verify` | Body `{credential}` — any tenant key. Returns `{valid, reason?, claims?}`. Claims only — never document data (selective disclosure) |
| `POST /v1/credentials/revoke` | Body `{credential_id}` — issuing tenant only |
| `GET /v1/sessions/{id}/credential` | The credential issued for an approved session (issuing tenant) |
| `POST /v1/sessions` with `{credential}` | Create a session seeded by a verified credential instead of a fresh applicant: shared checks are recorded with `provider: "verified_credential"` and pass only if the credential verifies, is unrevoked and unexpired, and its level ≥ the requested level (`422` otherwise). **Biometrics (face match, liveness) are never inherited** — if the level's config requires them, they run fresh in the flow |

Hosted-flow additions (flow token auth):

| Method & path | Purpose |
|---|---|
| `POST /v1/flow/liveness/challenge` | Issue the server-generated movement challenge for this session (random 2-direction sequence); returns the challenge + a plain-language instruction |
| `POST /v1/flow/liveness` | Multipart upload of the liveness video (`video` part, webm/mp4) — analysed server-side (face presence, challenged movement, static-replay rejection). Labelled in the UI as **active liveness (movement challenge)** |
| `POST /v1/flow/document/back` | Attach the BACK side scan to an existing flow document (`document_id` + `back` part). 422 if the document type has no back side (per-country registry, `server/docregistry.py`). Document/selfie/liveness uploads accept a `capture_meta` JSON field (e.g. `{"method":"live_camera","side":"front"}`), stored per side and shown in the review console. The hosted flow itself is a live camera scanner — it has no file-upload path |
| `POST /v1/flow/document/process` | Read-back step: the server reads the session's uploaded document (framing + multi-pass OCR + MRZ + template field extraction) and returns `{document_id, document_label, framing, read: {first_name, last_name, dob, number, expiry}, missing[], complete}`. The hosted flow shows the applicant what was read and lets them confirm or rescan — there is no form; rescan is the only correction path |
| `POST /v1/flow/poa` | Multipart proof-of-address upload (`document` part) for Level 3 |
| `GET /v1/flow/credential` | The applicant's own issued credential for this session (claims + signature) |
| `POST /v1/flow/credential/revoke` | The applicant revokes their own credential |

## Identity source: declared vs read-from-document

Every applicant carries `identity_source` — `"declared"` (default) or
`"document"`.

**Declared (the original contract).** `POST /v1/applicants` requires
`first_name`, `last_name`, `dob` and `country` (`422` otherwise). The
document is cross-checked against the declaration (the `consistency`
check and the `data_consistency` matrix's applicant source).

**Document (owner's order, 2026-10-26).** With
`{"identity_source": "document", "country": "NG"}` the tenant declares
NO name/DOB — the applicant only picks a document in the flow, and the
platform reads the identity from it. Rules:

- `country` is still required (the jurisdiction whose document the
  applicant will present); `first_name` / `last_name` / `dob` are
  optional. An `identity_source` other than `declared`/`document` →
  `422`.
- Sessions: pass the applicant's id as usual, or create the session
  inline with `{identity_source: "document", country, level}` — a
  document-sourced applicant shell is created for you (`422` without
  `country`). Session responses carry `identity_source`.
- Reading: the flow's read-back (`POST /v1/flow/document/process`) and
  submit both run the same reader — framing, multi-pass OCR, MRZ,
  template field extraction — merged by trust order: check-digit-valid
  MRZ > template extraction > any uploaded `doc_*` fields. The merged
  read is stored on the document (`doc_first_name` etc. are the
  SERVER's read, never the client's typing; the hosted flow collects
  no typed fields at all — there are no name/DOB/number inputs in it).
- Read-back contract: `missing` lists required identity fields that
  could not be read — `name` and `number` always; `dob` only where the
  document type carries an MRZ (an MRZ always encodes a DOB). Document
  types that print no DOB (e.g. the standard NG NIN slip) are never
  faulted for a missing DOB. `complete` is true only when framing
  passed and nothing required is missing.
- Consistency semantics: where tenant-declared details ARE present
  they are cross-checked exactly as on the declared path. Where
  nothing was declared, `consistency` evaluates agreement across the
  document's own reads (template extraction vs check-digit-valid MRZ
  vs the OCR text read; disagreements fail with `doc_*_reads_disagree`
  reason codes) and the `data_consistency` matrix compares the
  extraction against the printed/MRZ/payload sources with the
  applicant source empty — an applicant mismatch is impossible on
  this path by construction.
- Adoption: at decision time the read identity is written onto the
  applicant record as the verified identity (`identity_document_id`
  records the source document; audit action `identity.adopt`). Only
  empty fields are filled — a declared field is never overwritten,
  and when a declaration contradicted the document
  (`name_mismatch`/`dob_mismatch` in the decision) the declared
  record stands untouched.
- Screening, PoA name matching and the expiry/age check consume the
  session identity (declared fields, or the document read where
  nothing was declared), so a Level 3 document-sourced session is
  screened on the name read from its document.

Screening list format (`data/lists/*.csv`, one header row):
`full_name,dob,country,list_source,entry_id` — DOB as `YYYY-MM-DD`.
The repo ships a small SAMPLE fixture list under `lists/`; real lists
(e.g. OFAC SDN via `scripts/fetch_ofac.py`) are dropped into
`data/lists/` (gitignored). A decision's `risk_score`, `risk_band`,
`risk_contributions[]` and `config_version` are returned with the
session decision object.

## Decision object (shape)

```json
{
  "session_id": "…",
  "status": "approved",
  "level": 2,
  "reason_codes": [],
  "decided_by": "engine",
  "rules_version": "2026-10-26.1",
  "checks_summary": {
    "document_authenticity": "pass",
    "face_match": "pass",
    "liveness": "pass",
    "screening_sanctions": "pass"
  },
  "decided_at": "2026-10-26T00:00:00Z"
}
```

## Webhooks

Events: `session.created`, `session.completed`, `session.expired`,
`session.needs_more_information`, `case.opened`, `case.decided`,
`applicant.deleted`, `screening.hit_new` (ongoing monitoring).

- Signed: `KYC-Signature: t=<ts>,v1=<hmac-sha256>` over the raw body with
  the endpoint secret; tenants must verify and reject stale timestamps.
- Retries (WS3): failed deliveries retry with exponential backoff
  (30 s base, doubling) up to 5 attempts, then land in a **dead-letter**
  state. Every attempt is re-signed with a fresh timestamp. Deliveries
  are listed at `GET /v1/webhooks/deliveries` (`?status=` filter:
  pending/delivered/failed/dead_letter) and a dead-lettered or failed
  delivery can be re-queued with `POST /v1/webhooks/deliveries/{id}/replay`
  (tenant-scoped; `409` if the endpoint was deleted).
- SSRF guard (WS3): delivery is refused before any network call when
  the endpoint URL is not http(s) or its host resolves to a
  loopback/private/link-local/reserved address; the refusal is recorded
  on the delivery row.
- Payloads carry decision data only — **never document images or raw
  biometric data**.

## Errors & rules

- Standard shape: `{ "error": { "code", "message" } }` (no request_id
  field is emitted today).
- `401` bad/revoked key, `403` wrong environment or scope, `404` unknown
  or other-tenant id (no existence oracle), `409` state conflict,
  `413` request body over the size cap, `422` validation.
  `429` rate limiting **is implemented** (WS3): body
  `{error:{code:"rate_limited"}}` plus a `Retry-After` header.
- Idempotency: `Idempotency-Key` is **not honoured yet** (Phase 4 WS6);
  creation endpoints do not deduplicate on it today.
- Sandbox: test keys run the **identical real checks** as live keys —
  there are no faked deterministic outcomes. "Test" means strict data
  separation only: a test key can never read live data, and every
  record is stamped `env: test`. Screening in the test environment
  reads the same list files (results stay inside the test env).

## Rate limits (implemented — Phase 4 WS3)

In-memory sliding-window limiter (per process), all values env-tunable:

- Per API credential (key or reviewer token): **1,200 requests / minute**
  (`KYC_RL_API_PER_MIN`).
- Per hosted-flow token (consent, document front/back, selfie, liveness,
  proof-of-address submissions): **240 / minute** (`KYC_RL_FLOW_PER_MIN`).
- Per client IP backstop across `/v1/*`: **6,000 / minute**
  (`KYC_RL_IP_PER_MIN`). Window: `KYC_RL_WINDOW_SEC` (60).
- On limit: `429` + `Retry-After` (seconds until the window frees a
  slot). Uploads are also body-capped: any request body over
  `KYC_MAX_BODY_BYTES` (default 25 MB) is refused with `413` before it
  is read.

## Reviewer MFA (implemented — Phase 4 WS3)

Reviewer accounts can enrol a TOTP second factor (RFC 6238, any
authenticator app):

- `POST /v1/users/{id}/mfa/enroll` — reviewer authenticates with their
  own token; returns the base32 secret + `otpauth://` URI **once**.
- `POST /v1/users/{id}/mfa/confirm` — `{code}` activates MFA.
- Once active, privileged reviewer actions (case decide/confirm,
  screening-hit disposition, KYB registry decision) require the header
  `X-Reviewer-TOTP: <current 6-digit code>`; a missing, wrong, expired
  or **replayed** code → `401 mfa_required_or_invalid`.
- `POST /v1/users/{id}/mfa/reset` — tenant API key only (audited); the
  only recovery path. It fails closed: until reset + re-enrolment, the
  reviewer's privileged actions stay blocked.
- Policy: reviewers without MFA enrolled keep working **unless** the
  operator sets `KYC_REQUIRE_REVIEWER_MFA=1`, in which case unenrolled
  reviewers get `403 mfa_enrollment_required` on privileged actions.
  The tenant API-key identity itself is not TOTP-gated (documented
  operator policy; protect the key accordingly).
