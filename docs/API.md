# KYC — API Draft (v1)

*Draft contract for the build. Versioned, REST, JSON. Auth: tenant API key
(`Authorization: Bearer <key>`) scoped per environment. All timestamps UTC
ISO-8601. All ids are opaque UUIDs.*

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
- Retries: exponential backoff for 24h, then dead-letter; every attempt
  logged and visible; manual replay in the dashboard and API.
- Payloads carry decision data only — **never document images or raw
  biometric data**.

## Errors & rules

- Standard shape: `{ "error": { "code", "message", "request_id" } }`.
- `401` bad/revoked key, `403` wrong environment or scope, `404` unknown
  or other-tenant id (no existence oracle), `409` state conflict,
  `422` validation, `429` rate limit (headers included).
- Idempotency: `Idempotency-Key` honoured on session/applicant creation.
- Sandbox: test keys return deterministic outcomes for known test
  documents and never touch live data or real screening lists in a way
  that could be mistaken for a live result (sandbox results are stamped
  `env: test` everywhere).

## Rate limits (starting proposal)

- 600 req/min per live key (burst 100), 60/min per test key; upload
  endpoints sized for phone photos (≤ 15 MB per image, server-reduced).
