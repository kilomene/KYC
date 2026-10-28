# KYC — API (v1)

*REST, JSON. Auth: tenant API key (`Authorization: Bearer <key>`) scoped
per environment. All timestamps UTC ISO-8601. All ids are opaque UUIDs.*

**Canonical machine-readable contract:** [`openapi.json`](openapi.json)
or [`openapi.yaml`](openapi.yaml) — OpenAPI 3.1, 63 paths and 69
operations, generated from the route inventory in
`scripts/generate_openapi.py` and also published at
<https://kyc.novamail.store/openapi.json>. **Complete integration
guide:** [`DEVELOPER.md`](DEVELOPER.md) — website, mobile, backend,
SDK, agent, webhook, KYB, review, error and testing patterns.

This file remains the human endpoint and platform-rules reference.
Where a summary here and the OpenAPI operation disagree, treat the
OpenAPI operation as the wire contract and report the discrepancy.
General API-only document/selfie uploads, a document-metadata
endpoint and `Idempotency-Key` deduplication are **not offered**;
the hosted flow is the capture path.*

Platform bootstrap: `POST /v1/tenants` creates a tenant and its test/live
keys, and is **platform-operator only** — it requires the server-side
`KYC_PLATFORM_ADMIN_TOKEN` environment variable presented in the
`X-Platform-Admin` header. With no token configured it returns `403`
(tenant creation disabled). It is not part of the tenant API surface.

Other operator-only operations in the OpenAPI contract:
`GET /v1/platform/metrics`, `POST /v1/platform/prices`,
`POST /v1/platform/quotas`, `POST /v1/platform/invoices`, and
`DELETE /v1/platform/tenants/{id}` (body must repeat the tenant id
as `{"confirm":"<tenant_id>"}`). Tenant developers must not treat
these as self-service endpoints.

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
| `GET /v1/sessions/{id}/checks` | Every check: type, status, findings, provider, timestamps |
| `GET /v1/documents/{id}/image` | Protected, audited document image (`?side=front\|back`) for tenant review |
| `GET /v1/biometrics/{id}/image` | Protected, audited biometric image for tenant review |
| `POST /v1/cases/{id}/decide` | Reviewer action via API (approve / reject / request_more) — reason mandatory |
| `GET /v1/cases` / `GET /v1/cases/{id}` | Review queue and full audited case view |
| `POST /v1/webhooks` / `GET /v1/webhooks` | Manage webhook endpoints |
| `DELETE /v1/webhooks/{id}` | Delete a webhook endpoint and its delivery records |
| `POST /v1/webhooks/deliveries/{delivery_id}/replay` | Re-queue a failed/dead-lettered delivery (re-signed on send) |
| `GET /v1/keys` / `POST /v1/keys/{id}/revoke` | API-key metadata and revocation |
| `GET /v1/sessions` | Tenant session list |
| `GET /v1/flow/session` | Token-scoped hosted-flow state + authoritative document registry |

Not offered: `POST /v1/sessions/{id}/documents`,
`POST /v1/sessions/{id}/selfie`, `GET /v1/documents/{id}` metadata,
or a tenant `return_url` / iframe capture API. Capture happens in
the hosted flow.

## Phase 2/3 endpoints (implemented 2026-10-26)

Reviewer identity: console/API case actions accept an optional
`X-Reviewer-Key: <user token>` header (issued by `POST /v1/users`).
Without it, actions are recorded as the tenant API key identity
(role admin). An invalid presented token is refused with `401` —
it never silently falls back.

| Method & path | Purpose |
|---|---|
| `GET /v1/config?level=N` | Active flow config for the level: required_checks, face_pass_threshold, face_margin, risk_auto_approve_ceiling, poa_window_days, screening_threshold, sla_hours, four_eyes + its version (0 = built-in defaults) |
| `PUT /v1/config` | Body `{level, config}` — `config` is the patch object. Validates and stores a NEW config version (old versions are kept; decisions record the `config_version` they ran under). Unknown keys / out-of-range values → `422` |
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
| `POST /v1/businesses/{id}/people` | Attach an applicant as `{applicant_id, role: director\|ubo, ownership_pct}` (the endpoint does not accept `officer`) |
| `POST /v1/businesses/{id}/document` | Multipart company document upload (registry evidence) |
| `POST /v1/businesses/{id}/registry-check` | Run the configured authoritative-registry adapter and store its outcome. Adapters fail closed as `not_configured` where no source/credential is connected |
| `POST /v1/businesses/{id}/registry` | Reviewer registry decision `{status: confirmed\|rejected, reason}` after format validation, uploaded evidence and any adapter lookup. The human decision itself is not a live government-registry connection |
| `POST /v1/businesses/{id}/evaluate` | Assemble the business decision: `verified` only when the registry leg is confirmed AND every attached person is approved at Level 2+ AND no person has a pending/confirmed screening hit; otherwise `pending`/`rejected` with named reasons |
| `POST /v1/monitoring/rescreen` | Re-screen all approved applicants of the tenant against the CURRENT lists. New matches → `monitoring_alerts` rows + `screening.hit_new` webhook + a reopened case. Returns `{screened, new_hits, alerts}` |
| `GET /v1/monitoring/alerts` | Monitoring alerts for the tenant |
| `POST /v1/credentials/verify` | Body `{credential}` — any tenant key. Returns `{valid, reason?, claims?}`. Claims only — never document data (selective disclosure) |
| `POST /v1/credentials/revoke` | Body `{credential_id}` — issuing tenant only |
| `GET /v1/sessions/{id}/credential` | The credential issued for an approved session (issuing tenant) |
| `POST /v1/sessions` with `{credential}` | Create a session seeded by a verified credential instead of a fresh applicant: shared checks are recorded with `provider: "verified_credential"` and pass only if the credential verifies, is unrevoked and unexpired, and its level ≥ the requested level (`422` otherwise). **Biometrics (face match, liveness) are never inherited** — if the level's config requires them, they run fresh in the flow |

Hosted-flow endpoints (flow token auth — `Authorization: Bearer
<flow_token>` or `X-Flow-Token`):

| Method & path | Purpose |
|---|---|
| `GET /v1/flow/session` | Current flow state, applicant summary, capture state, `allowed_docs` and the authoritative `document_registry` |
| `POST /v1/flow/consent` | Record consent and start the flow; harvests disclosed IP/location signals and applies the VPN/proxy hard gate (`403 vpn_proxy_detected`) |
| `POST /v1/flow/document` | Store the document front (and a together-captured back). The hosted UI is a live camera scanner. The Nigerian NIN slip is the named upload exception and the only kind that may send an 11-digit `claimed_number` |
| `POST /v1/flow/document/back` | Attach the BACK side scan to an existing flow document (`document_id` + `back` part). 422 if the document type has no back side (per-country registry, `server/docregistry.py`). Document/selfie/liveness uploads accept a `capture_meta` JSON field (e.g. `{"method":"live_camera","side":"front"}`), stored per side and shown in the review console |
| `POST /v1/flow/presence` | One-frame face-presence coaching probe. The frame is analysed in memory and never stored |
| `POST /v1/flow/selfie` | Store the live selfie plus optional same-second `burst_0`…`burst_4` frames for continuous face tracking |
| `POST /v1/flow/liveness/challenge` | Issue the server-generated movement challenge for this session (random 2-direction sequence); returns the challenge + a plain-language instruction |
| `POST /v1/flow/liveness` | Multipart upload of the liveness video (`video` part, webm/mp4) — analysed server-side (face presence, challenged movement, static-replay rejection). Labelled in the UI as **active liveness (movement challenge)** |
| `POST /v1/flow/document/process` | Read-back step: the server reads the session's uploaded document (framing + dual-engine OCR + MRZ + template field extraction) and returns `{document_id, document_label, framing, read: {first_name, last_name, dob, number, expiry}, missing[], complete}`. A long read returns `202 {"status":"reading"}` and the caller polls the same endpoint. The hosted flow shows the applicant what was read and lets them confirm or rescan — there is no name/DOB form |
| `POST /v1/flow/document/claim` | Correct the typed NIN for an uploaded `nin_slip` without re-uploading it; the claim is compared with the number read from the slip |
| `POST /v1/flow/poa` | Multipart proof-of-address upload (`document` part) for Level 3 |
| `POST /v1/flow/submit` | Submit for the automatic decision. Returns the final session view or `202 {"status":"processing","session_id"}` while processing runs |
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

## Session and decision shape

`GET /v1/sessions/{id}` returns the session view. The decision is
nested under `decision`; the session outcome itself is the top-level
`status`.

```json
{
  "id": "…",
  "tenant_id": "…",
  "env": "test",
  "applicant_id": "…",
  "identity_source": "document",
  "level": 2,
  "status": "approved",
  "expires_at": "2026-10-29T00:00:00Z",
  "created_at": "2026-10-28T00:00:00Z",
  "client_ip_masked": "203.0.113.x",
  "ip_country": "NG",
  "vpn_status": "clear",
  "checks_summary": {
    "document_classification": "pass",
    "face_match": "pass",
    "liveness": "pass",
    "screening_sanctions": "pass"
  },
  "decision": {
    "id": "…",
    "session_id": "…",
    "outcome": "approved",
    "decided_by": "engine",
    "reason": null,
    "reason_codes": [],
    "rules_version": "2026-10-26.1",
    "risk_score": 0,
    "risk_band": "low",
    "risk_contributions": [],
    "config_version": 0,
    "created_at": "2026-10-28T00:01:00Z"
  }
}
```

## Webhooks

Implemented events: `session.completed`, `case.opened`,
`case.decided`, `applicant.deleted`, and `screening.hit_new`
(ongoing monitoring). An endpoint whose `events` list is empty
receives every implemented event. Deliveries also carry a
`KYC-Event: <event>` header and a JSON envelope
`{"event": "...", "data": {...}}`.

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
- Idempotency: `Idempotency-Key` is **not currently honoured**;
  creation endpoints do not deduplicate on it. Reconcile a timed-out
  creation against your own mapping before creating another resource.
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
