# KYC — API (v1)

*REST, JSON. Auth: tenant API key (`Authorization: Bearer <key>`) scoped
per environment. All timestamps UTC ISO-8601. All ids are opaque UUIDs.
The Phase 1 endpoints below are implemented as drafted; the Phase 2/3
section after the decision object documents what was added in the
2026-10-26 local build (implemented and covered by the test suite).
Two draft items remain unimplemented and are marked as such: webhook
replay and API-only document/selfie upload endpoints (the hosted flow
is the upload path in the local build).*

## Core flow

```
1. POST /v1/applicants            → create / upsert an applicant
2. POST /v1/sessions              → create a verification session
                                    response includes the hosted-flow URL
3. Applicant completes the flow    → uploads happen inside the flow
   (or: upload via API in an API-only integration, endpoints below)
4. Webhook: session.completed      → decision ready
   GET  /v1/sessions/{id}          → status + decision + reason codes
   GET  /v1/sessions/{id}/checks   → per-check results
```

## Endpoints (draft)

| Method & path | Purpose |
|---|---|
| `POST /v1/applicants` | Create applicant from name / DOB / country (+ optional external_ref) |
| `GET /v1/applicants/{id}` | Applicant summary (no document images by default) |
| `DELETE /v1/applicants/{id}` | Request erasure (audited, async, confirmed by webhook `applicant.deleted`) |
| `POST /v1/sessions` | Create session: applicant_id, level, optional allowed document types/countries, expiry override |
| `GET /v1/sessions/{id}` | Status, decision, reason codes, timestamps |
| `POST /v1/sessions/{id}/cancel` | Cancel a live session; its link dies immediately |
| `POST /v1/sessions/{id}/documents` | API-only upload (multipart) when not using the hosted flow |
| `POST /v1/sessions/{id}/selfie` | API-only biometric capture upload (liveness rules still apply) |
| `GET /v1/sessions/{id}/checks` | Every check: type, status, findings, provider, timestamps |
| `GET /v1/documents/{id}` | Document metadata + extracted fields (images only via short-lived signed URL, separately authorised + audited) |
| `POST /v1/cases/{id}/decide` | Reviewer action via API (approve / reject / request_more) — reason mandatory |
| `GET /v1/cases` | Review queue for the tenant |
| `POST /v1/webhooks` / `GET /v1/webhooks` | Manage webhook endpoints |
| `POST /v1/webhooks/{id}/replay/{delivery_id}` | Replay a delivery |

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
| `POST /v1/flow/poa` | Multipart proof-of-address upload (`document` part) for Level 3 |
| `GET /v1/flow/credential` | The applicant's own issued credential for this session (claims + signature) |
| `POST /v1/flow/credential/revoke` | The applicant revokes their own credential |

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
- Retries: **not yet built** — the local build makes one signed
  delivery attempt per event and logs it. (Backoff/dead-letter/replay
  remain the design target.)
- Payloads carry decision data only — **never document images or raw
  biometric data**.

## Errors & rules

- Standard shape: `{ "error": { "code", "message", "request_id" } }`.
- `401` bad/revoked key, `403` wrong environment or scope, `404` unknown
  or other-tenant id (no existence oracle), `409` state conflict,
  `422` validation, `429` rate limit (headers included).
- Idempotency: `Idempotency-Key` honoured on session/applicant creation.
- Sandbox: test keys run the **identical real checks** as live keys —
  there are no faked deterministic outcomes. "Test" means strict data
  separation only: a test key can never read live data, and every
  record is stamped `env: test`. Screening in the test environment
  reads the same list files (results stay inside the test env).

## Rate limits (starting proposal)

- 600 req/min per live key (burst 100), 60/min per test key; upload
  endpoints sized for phone photos (≤ 15 MB per image, server-reduced).
