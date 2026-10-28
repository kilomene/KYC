# Integration guide — Nova KYC

Everything a developer needs to put identity verification into a
product. For the endpoint-by-endpoint reference see `docs/API.md`;
for the JavaScript SDK see `sdk/`.

## 1. Keys and environments

You get two API keys per tenant: a **test** key and a **live**
key. The key decides the environment — there is no separate
sandbox host. Test-mode verifications are free, run the full
pipeline, and are the only mode while you integrate. Treat keys
as secrets: server-side only, never in a browser or mobile app.

All API calls use:

```
Authorization: Bearer <api_key>
```

## 2. The verification flow (the 4-step pattern)

1. **Create an applicant** — `POST /v1/applicants`
   `{ "country": "NG", "identity_source": "document" }`.
   Identity comes FROM the document the person scans; there is
   no name/DOB form anywhere in the product, by design.
2. **Create a session** — `POST /v1/sessions`
   `{ "applicant_id": "...", "level": 1 }` → the response carries
   `flow_url` (a path: `/flow/<token>`) and `expires_at`.
   Levels: 1 = document + selfie + liveness; 2 adds proof of
   address; 3 adds enhanced checks (screening/monitoring).
3. **Send the person to the flow** —
   `https://kyc.novamail.store` + `flow_url`. The hosted flow is
   phone-only by design (desktop visitors get a QR handoff to
   their phone). It is fully automatic: live document scanning,
   selfie, and an active liveness challenge, with voice guidance.
4. **Learn the outcome** — poll `GET /v1/sessions/{id}` or take
   the webhook (below). Terminal statuses: `approved`,
   `rejected`, `needs_review`, `needs_more_information`. The
   session view carries the decision and its reason codes;
   approved sessions can issue a reusable, signed credential
   (claims only — the documents never leave the platform).

## 3. Webhooks

Register: `POST /v1/webhooks` `{ "url": "https://…", "events":
["session.completed", "case.decided"] }`. The response includes
the endpoint **secret** — store it; it is shown once.

Every delivery is signed:

```
KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
```

The HMAC is over `"<t>.<raw request body>"` with your endpoint
secret. **Verify against the raw body** — a re-serialised JSON
object will not verify. The SDK's `verifyWebhookSignature`
does this for you. Deliveries retry with backoff and dead-letter
after the schedule; inspect them with `GET /v1/webhooks/deliveries`
and remove an endpoint with `DELETE /v1/webhooks/{id}` (its
deliveries go with it). Endpoint URLs must be public HTTPS —
private/loopback targets are refused by the SSRF guard.

## 4. Businesses (KYB)

`POST /v1/businesses` creates a business record;
`POST /v1/businesses/{id}/registry-check` runs the authoritative
registry lookup for its country where a live registry source is
connected, and stores the outcome on the record. Where no
registry is connected the check answers `not_configured` —
never a guess.

## 5. Usage, invoices, dashboard

Every decided session is metered exactly once. `GET /v1/usage`
(?from=&to=) returns per-level counts and amounts for the
period; `GET /v1/invoices` lists generated invoices. Test-mode
events are always priced at zero (sandbox). The human view is
the dashboard: **https://kyc.novamail.store/dashboard** — paste
your key, see usage, invoices, endpoints (with removal), and
recent sessions.

## 6. Errors

Errors are JSON: `{ "error": { "code": "...", "message": "..." } }`.
Expect 401 (bad/revoked key), 403 (platform-admin routes),
404 (not yours / not found — cross-tenant objects are invisible),
422 (validation), 429 (`quota_exceeded` when an operator-set
monthly live cap is reached). 5xx is retryable with backoff;
the hosted flow's long operations answer 202 with a polling
contract instead of holding a request open.

## 7. Privacy & erasure

`DELETE /v1/applicants/{id}` performs subject erasure: stored
media is deleted and PII fields are nulled, with the erasure
itself recorded. Webhook payloads and credentials carry claims
and outcomes, never document images or biometric data.
