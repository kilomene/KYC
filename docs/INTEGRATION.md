# Integration quickstart — Nova KYC

This is the short path. The complete website, mobile, backend,
webhook, SDK, KYB, review and troubleshooting guide is
[`DEVELOPER.md`](DEVELOPER.md). The machine-readable contract is
[`openapi.json`](openapi.json) / [`openapi.yaml`](openapi.yaml),
also published at <https://kyc.novamail.store/openapi.json>.

## 1. Keys and environments

You get two API keys per tenant: a **test** key and a **live**
key. The key decides the environment — there is no separate
sandbox host and no environment header. Test-mode verifications
run the full pipeline and are priced at zero; test and live data
are strictly separated.

Tenant creation is operator-provisioned. `POST /v1/tenants` is a
platform-operator endpoint, not public self-service signup.

Treat keys as server-side secrets. Never put one in a browser,
mobile app, public repository or agent prompt.

```http
Authorization: Bearer <api_key>
```

## 2. The verification flow

1. **Create an applicant** — `POST /v1/applicants`

   ```json
   { "country": "NG", "identity_source": "document" }
   ```

   Identity comes from the document the person scans. Use the
   declared identity form only when your product already holds a
   reliable name and date of birth to cross-check.

2. **Create a session** — `POST /v1/sessions`

   ```json
   { "applicant_id": "...", "level": 2 }
   ```

   The response carries `flow_url`, `flow_token` and `expires_at`.

   Built-in level defaults:

   - Level 1: document identity core;
   - Level 2: Level 1 plus MRZ where applicable, authenticity,
     face match/track, liveness and deepfake checks;
   - Level 3: Level 2 plus proof of address and sanctions
     screening.

   A tenant's active configuration can differ; read it with
   `GET /v1/config?level=N`.

3. **Send the person to the flow** —
   `https://kyc.novamail.store` + `flow_url`.

   The hosted flow is phone-first. Desktop visitors receive a QR
   handoff. It includes consent, live document scanning, a selfie,
   liveness from Level 2 and proof of address at Level 3, with
   voice guidance. A detected VPN/proxy stops the flow before
   capture.

4. **Learn the outcome** — use the signed webhook (recommended)
   or poll `GET /v1/sessions/{id}` from your backend.

   Terminal approval is only `approved`. `needs_review` and
   `needs_more_information` are not approvals. A submitted session
   can return `202 processing`; keep polling or wait for the
   webhook.

## 3. Website and mobile handoff

- **Website:** navigate the current tab to the flow URL or open it
  in a new tab. Refresh status from your own backend when the user
  returns.
- **Mobile:** call your own backend to create the session, then
  open the flow in the system browser, an iOS in-app browser
  surface or an Android Custom Tab. Refresh status when the app
  resumes or after your backend sends a push.
- **Not supported:** an iframe/embed SDK, a native capture SDK, or
  a tenant-supplied session `return_url`. There is no general
  API-only document/selfie upload. These boundaries are detailed
  in `DEVELOPER.md`.

## 4. Webhooks

Register:

```http
POST /v1/webhooks
{ "url": "https://…", "events": ["session.completed", "case.decided"] }
```

The response includes the endpoint **secret** — store it; it is
shown once.

Implemented events are `session.completed`, `case.opened`,
`case.decided`, `applicant.deleted` and `screening.hit_new`.

Every delivery is signed:

```http
KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
KYC-Event: session.completed
```

The HMAC is over `"<t>.<raw request body>"` with the endpoint
secret. Verify the raw body, never a re-serialised JSON object.
The SDK's `verifyWebhookSignature` does this and can also enforce
a maximum timestamp age. Deliveries retry with backoff, dead-letter
after the attempt budget, and can be inspected and replayed through
the API. Receiver URLs must resolve to public addresses; the SSRF
guard refuses private and loopback targets.

## 5. Businesses (KYB)

1. Create the business with `POST /v1/businesses`.
2. Upload registry evidence with
   `POST /v1/businesses/{id}/document`.
3. Run `POST /v1/businesses/{id}/registry-check` for the configured
   authoritative adapter. It fails closed with `not_configured`
   where no source is connected.
4. A reviewer records the registry leg with
   `POST /v1/businesses/{id}/registry` after reviewing evidence.
5. Verify and attach directors/UBOs as applicants.
6. Run `POST /v1/businesses/{id}/evaluate`.

A business verifies only when the registry leg is confirmed, every
attached person is approved at Level 2+, and no person has a
pending or confirmed screening hit.

## 6. Usage, invoices and dashboard

Every decided session is metered exactly once. `GET /v1/usage`
(`?from=&to=`) returns counts and amounts for the period;
`GET /v1/invoices` lists generated invoices. Prices and quotas are
operator configuration, not constants in this guide.

The human view is <https://kyc.novamail.store/dashboard>. The
developer portal is <https://kyc.novamail.store/docs>.

## 7. Errors and retries

Errors are JSON:

```json
{ "error": { "code": "...", "message": "..." } }
```

Expect 401 (bad/revoked credential), 403 (operator gate, VPN or
MFA policy), 404 (not yours / wrong environment), 409 (state
conflict), 413 (body too large), 422 (validation), 429
(`rate_limited` or `quota_exceeded`) and retryable 5xx.

`Idempotency-Key` is not currently honoured. Reconcile timed-out
creation calls before blindly creating another resource.

## 8. Privacy and erasure

`DELETE /v1/applicants/{id}` performs subject erasure: stored media
is deleted and PII fields are nulled, with the erasure recorded.
Webhook payloads and reusable credentials carry claims and
outcomes, never document images or biometric data.
