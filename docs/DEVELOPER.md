# Nova KYC — Developer Guide

*The complete integration guide for websites, mobile apps, backend
services, review operations and AI agents.*

Nova KYC verifies people and businesses without asking the
integrating product to collect identity documents or biometric data
itself. Your server creates a verification session, Nova KYC hosts
the capture and decision flow, and your server receives the result.

## Documentation map

| Need | Use |
|---|---|
| Build an integration step by step | This guide |
| Import the API into Postman, Insomnia, an agent tool registry or a client generator | [`openapi.json`](openapi.json) or [`openapi.yaml`](openapi.yaml) |
| Browse the specification online | <https://kyc.novamail.store/openapi.json> |
| Human endpoint reference and platform rules | [`API.md`](API.md) |
| Short quickstart | [`INTEGRATION.md`](INTEGRATION.md) |
| JavaScript / Node SDK | [`../sdk/README.md`](../sdk/README.md) |
| Tenant operations dashboard | <https://kyc.novamail.store/dashboard> |
| Review console | <https://kyc.novamail.store/console> |

The OpenAPI file is not a sketch. It describes the implemented
v1 HTTP surface, including tenant APIs, the token-scoped hosted-flow
endpoints, review and KYB operations, reusable credentials,
monitoring, billing metadata and the platform-operator endpoints.

## 1. The integration model

```text
Your user's browser or phone
        │
        │ 1. User chooses "Verify identity" in your product
        ▼
Your application UI ───────────────► Your backend
                                       │
                                       │ 2. POST /v1/applicants
                                       │ 3. POST /v1/sessions
                                       │    (secret API key)
                                       ▼
                                  Nova KYC API
                                       │
                                       │ 4. flow_url + flow_token
                                       ▼
Your backend returns only the one-session flow link to the device
                                       │
                                       ▼
                         Hosted Nova KYC flow on the phone
                    consent → document → selfie → liveness / PoA
                                       │
                         5. Automatic decision or review case
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
       Signed webhook to your backend              GET /v1/sessions/{id}
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       ▼
                         Your backend updates its own user
```

### The five rules that keep an integration safe

1. **API keys belong on your server.** Never put a tenant key in a
   website bundle, mobile app, browser storage, source repository,
   analytics event, support ticket or AI-agent prompt.
2. **The flow token belongs to one person and one session.** Treat
   `flow_url` / `flow_token` as a temporary secret. Send it only to
   the person who must verify, do not log the full URL, and do not
   reuse it for another user.
3. **Your backend is the source of truth for access.** A browser or
   app must not grant itself a benefit merely because it returned
   from the flow. Your backend grants access only after it receives
   a verified webhook or reads an approved session with its API key.
4. **Do not collect identity media yourself.** The hosted flow is
   the capture surface. There is no general API-only upload endpoint
   for documents, selfies or liveness videos.
5. **Do not invent an outcome.** `processing`, `needs_review` and
   `needs_more_information` are not approvals. Only `approved` is
   an approval.

## 2. Access, environments and base URLs

Production base URL:

```text
https://kyc.novamail.store
```

Local development default:

```text
http://127.0.0.1:8765
```

A tenant has two keys:

| Key | Environment | Use |
|---|---|---|
| `kyc_test_…` | `test` | Development and end-to-end testing |
| `kyc_live_…` | `live` | Real applicants |

The key selects the environment. There is no separate sandbox host
and no environment header. Test and live records are isolated: a
test key cannot read a live applicant, session, case, business or
webhook endpoint.

Tenant creation is currently an **operator-provisioned** operation.
`POST /v1/tenants` requires the platform operator's
`X-Platform-Admin` credential; it is not a public self-service
signup endpoint. If you are integrating a Nova product, obtain the
tenant's test and live keys through the platform operator and store
them in your server's secret manager.

Authentication for tenant APIs:

```http
Authorization: Bearer kyc_test_REPLACE_ME
Content-Type: application/json
```

## 3. Choose an identity model

### 3.1 Document-sourced identity — recommended

Create the applicant with only a country:

```json
{
  "country": "NG",
  "identity_source": "document",
  "external_ref": "user_12345"
}
```

The person chooses and scans a document in the hosted flow. Nova
KYC reads the name, date of birth and document number from the
document itself, using the strongest available sources. After a
decision, the verified read is adopted onto the applicant record.

Use `external_ref` for your own user id. Do not put secrets,
national identity numbers or unnecessary personal data in it.

### 3.2 Declared identity — cross-check mode

Use this only when your product already lawfully holds a reliable
name and date of birth and needs Nova KYC to cross-check them:

```json
{
  "country": "NG",
  "identity_source": "declared",
  "first_name": "Adaeze",
  "last_name": "Example",
  "dob": "1992-04-17",
  "external_ref": "user_12345"
}
```

A mismatch between the declaration and the document is a decision
input. A declared value is never silently overwritten by a document
read.

### 3.3 Reusable credential

An approved session can issue a signed credential containing claims
only. A later session can be seeded with that credential when the
credential:

- verifies successfully;
- has not expired or been revoked; and
- was issued at a level greater than or equal to the requested level.

Document and data checks can be inherited according to the active
configuration. **Biometrics are never inherited**: if the requested
level requires face match or liveness, those run again in the new
flow.

## 4. Verification levels

Levels are configuration-driven. Always read the tenant's active
configuration with `GET /v1/config?level=N` instead of assuming a
deployment can never change. The built-in defaults are:

| Level | Default required checks | Typical use |
|---|---|---|
| 1 | Capture quality, document framing, document classification, data consistency, OCR, expiry/age and consistency | Document identity core |
| 2 | Level 1 plus MRZ where applicable, authenticity, face match, continuous face track, liveness and deepfake checks | Full person verification |
| 3 | Level 2 plus proof of address and sanctions screening | Enhanced verification |

The hosted experience always includes consent and a live selfie.
Liveness is presented from Level 2, and proof of address from
Level 3. Location consistency and the VPN/proxy gate are platform
controls around the flow; a detected VPN or proxy stops the flow
before document capture.

## 5. Your first verification

### 5.1 cURL

Create an applicant:

```bash
curl -s https://kyc.novamail.store/v1/applicants \
  -H "Authorization: Bearer $KYC_TEST_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "NG",
    "identity_source": "document",
    "external_ref": "user_12345"
  }'
```

Create a session:

```bash
curl -s https://kyc.novamail.store/v1/sessions \
  -H "Authorization: Bearer $KYC_TEST_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "applicant_id": "APPLICANT_ID",
    "level": 2,
    "expires_hours": 24
  }'
```

The response includes:

```json
{
  "id": "SESSION_ID",
  "level": 2,
  "env": "test",
  "status": "created",
  "applicant_id": "APPLICANT_ID",
  "identity_source": "document",
  "flow_url": "/flow/FLOW_TOKEN",
  "flow_token": "FLOW_TOKEN",
  "expires_at": "2026-10-29T08:30:00Z",
  "credential_id": null,
  "inherited_checks": []
}
```

Send the person to:

```text
https://kyc.novamail.store/flow/FLOW_TOKEN
```

Read the result:

```bash
curl -s https://kyc.novamail.store/v1/sessions/SESSION_ID \
  -H "Authorization: Bearer $KYC_TEST_KEY"
```

Or create a document-sourced applicant and session source in one
session call:

```bash
curl -s https://kyc.novamail.store/v1/sessions \
  -H "Authorization: Bearer $KYC_TEST_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "identity_source": "document",
    "country": "NG",
    "external_ref": "user_12345",
    "level": 2
  }'
```

### 5.2 Node.js with the SDK

```js
import { KycClient } from './sdk/kyc.mjs';

const kyc = new KycClient({
  apiKey: process.env.KYC_API_KEY,
  baseUrl: process.env.KYC_BASE_URL || 'https://kyc.novamail.store',
});

export async function startVerification(user) {
  const applicant = await kyc.createApplicant({
    country: user.country,
    identitySource: 'document',
    externalRef: String(user.id),
  });

  const session = await kyc.createSession({
    applicantId: applicant.id,
    level: 2,
    expiresHours: 24,
  });

  await db.saveVerificationSession({
    userId: user.id,
    applicantId: applicant.id,
    sessionId: session.id,
    status: session.status,
  });

  return { verificationUrl: kyc.absoluteFlowUrl(session) };
}
```

### 5.3 Python without an SDK package

The API is plain JSON over HTTPS. This standard-library example is
enough for a backend integration:

```python
import json
import os
import urllib.request

BASE = os.environ.get("KYC_BASE_URL", "https://kyc.novamail.store")
KEY = os.environ["KYC_API_KEY"]

def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

applicant = call("POST", "/v1/applicants", {
    "country": "NG",
    "identity_source": "document",
    "external_ref": "user_12345",
})
session = call("POST", "/v1/sessions", {
    "applicant_id": applicant["id"],
    "level": 2,
})
verification_url = BASE + session["flow_url"]
```

For another language, import the OpenAPI document into your client
generator instead of hand-writing endpoint strings.

## 6. Website integration

### Recommended pattern: full-page handoff

1. The signed-in user selects **Verify identity** in your product.
2. Your page calls **your own backend**, not Nova KYC directly.
3. Your backend creates the applicant/session and stores the
   mapping `your user → applicant_id + session_id`.
4. Your backend returns the flow URL to your page.
5. Navigate the current tab to the flow URL, or open it in a new
   tab if your product needs to preserve form state.
6. When the user returns, your page asks **your backend** for the
   current status. It never decides from a query parameter.
7. Your backend learns the outcome from the webhook and/or
   `GET /v1/sessions/{id}`.

Example browser code after your backend has returned a URL:

```js
const response = await fetch('/api/verification/start', { method: 'POST' });
const { verificationUrl } = await response.json();
window.location.assign(verificationUrl);
```

### New-tab pattern and focus polling

If the flow opens in another tab, the original page may refresh its
own backend status when it regains focus:

```js
window.addEventListener('focus', async () => {
  const status = await fetch('/api/verification/status').then(r => r.json());
  renderVerificationStatus(status);
});
```

This is only a user-experience refresh. The webhook remains the
authoritative completion signal.

### Desktop behaviour

The capture flow is phone-first. A desktop visitor is shown a QR
handoff so the document and camera steps can continue on a phone.
Set this expectation in your product copy before the handoff:

> Verification continues on your phone so you can scan your
> document and complete the live camera checks.

### What not to do on a website

- **Do not embed your API key in JavaScript.**
- **Do not treat the hosted flow as an iframe widget.** There is no
  supported iframe SDK, embed token, postMessage completion protocol
  or return-message contract. Use a page navigation or new tab.
- **Do not add a `return_url` parameter and expect it to work.**
  Session creation does not currently accept a tenant return URL.
  Your backend learns completion by webhook/polling and your own
  product controls what happens when the user navigates back.
- **Do not mirror the flow token into analytics, ads or error
  reporting.** Strip `/flow/<token>` down to `/flow/…` before logging.

## 7. Mobile-app integration

A mobile app needs a backend just as much as a website does. The
app should call your backend's "start verification" endpoint; your
backend calls Nova KYC with its secret key.

### Recommended native handoff

Use the platform's secure in-app browser surface:

- **iOS:** open the flow URL with the system browser or
  `SFSafariViewController` where camera behaviour has been tested on
  your supported OS versions.
- **Android:** open it in a Chrome Custom Tab or the system browser.

These surfaces give the web flow a modern browser engine, camera
and media APIs, and a clear user-controlled return to your app.

When the user returns to the app:

1. Refresh status from **your backend** in `onResume` /
   `sceneDidBecomeActive`.
2. If your backend has not yet received the webhook, show
   **Verification in progress** and retry with backoff.
3. If push notifications are part of your product, your backend may
   send one after it receives and verifies `session.completed`.
4. Never mark the user verified merely because the browser closed.

### Returning to the app

Nova KYC does not currently accept a session `return_url`, universal
link or Android app link to invoke after completion. Do not invent
one in the session request. The supported completion loop is:

```text
Hosted flow finishes
      → signed webhook reaches your backend
      → your backend updates the user
      → app refreshes status when resumed, or receives your push
```

You may link from your own email, SMS or in-app inbox back into a
**status screen in your app**, but that link belongs to your product;
it is not a Nova KYC flow parameter.

### WebView warning

A raw embedded WebView is not the recommended integration. Browser
engines and permission delegation differ sharply:

- Android WebView hosts must correctly delegate camera/microphone
  permission requests, JavaScript, DOM storage, media capture and
  file handling.
- iOS `WKWebView` camera and `getUserMedia` behaviour depends on OS
  version, app configuration and usage-description setup.
- A WebView makes it harder for the user to inspect the real Nova
  KYC domain.

If you choose a WebView despite this guidance, test the entire flow
on every supported OS/browser-engine version, including document
camera, selfie, liveness video, VPN blocking, expired sessions and
the Nigerian NIN-slip exception. Never inject a tenant API key into
the WebView; the page should receive only the one-session flow URL.

### Custom native capture

There is currently **no public native-capture SDK** and no general
API-only media upload contract. A native app must not send camera
frames directly to tenant endpoints and expect a verification. Use
the hosted flow. The token-scoped `/v1/flow/*` operations in the
OpenAPI document exist for the hosted flow and advanced wrappers
that faithfully preserve its consent, sequencing and capture rules;
they are not a shortcut around the hosted product.

## 8. AI-agent integration

An AI agent can operate the tenant API as a tool-using backend
client, provided a human-controlled system gives it credentials
through a secret manager or tool runtime.

Give the agent these machine-readable resources:

- OpenAPI JSON: <https://kyc.novamail.store/openapi.json>
- OpenAPI YAML: <https://kyc.novamail.store/openapi.yaml>
- This guide and `docs/API.md`
- The JavaScript SDK when the agent is building a Node service

A safe agent tool contract is:

```text
create_applicant(country, external_ref)
create_session(applicant_id or document-source input, level)
get_session(session_id)
get_session_checks(session_id)
cancel_session(session_id)
verify_credential(credential)
```

Rules for agents:

- Retrieve the API key from the tool's secret binding at call time;
  never ask the user to paste it into a prompt and never print it.
- Use the **test key** while building.
- Store the returned applicant and session ids in the calling
  product's database.
- Deliver the flow link only to the intended applicant.
- Read outcomes from `get_session` or a verified webhook. Do not
  infer approval from a page screenshot or from the user returning.
- Do not call reviewer decision endpoints unless the calling product
  has explicitly delegated that authority and supplies a named
  reviewer identity and MFA code where required.
- Platform-operator endpoints are not agent tools for a tenant
  integration. Tenant creation, prices, quotas and platform metrics
  require the operator credential.

## 9. Session lifecycle and result handling

Session statuses:

| Status | Meaning | Terminal? | Your action |
|---|---|---:|---|
| `created` | Session exists; flow not started | No | Send the user to the flow |
| `in_progress` | Consent/capture is under way | No | Wait |
| `processing` | The decision engine is running | No | Poll with backoff or wait for webhook |
| `approved` | Verification approved | Yes | Read the decision and grant the gated action |
| `rejected` | Verification rejected | Yes | Show a safe, non-sensitive explanation and your support path |
| `needs_review` | A human case exists | Operationally pending | Do not approve; wait for `case.decided` / a later `session.completed` |
| `needs_more_information` | The applicant must supply or redo something | Operationally pending | Follow the case/session reason codes and your product policy |
| `expired` | The flow link expired before completion | Yes for that session | Create a new session if the user still wants to verify |
| `cancelled` | The tenant cancelled the session | Yes | Do not reuse the link |

The session view carries:

- `checks_summary`: the latest status by check type;
- `decision`: the decision object, or `null` before decision;
- `decision.reason_codes`: machine-readable reasons;
- `decision.risk_score`, `risk_band` and `risk_contributions`;
- `client_ip_masked`, `ip_country` and `vpn_status`;
- `identity_source`.

Use `GET /v1/sessions/{id}/checks` when your support or risk team
needs provider, findings and reason codes for every check rather
than only the summary.

### Polling rules

- Poll your own backend from browsers/apps; poll Nova KYC from your
  backend.
- Start at 3–5 seconds, back off to 15–30 seconds, and stop at a
  terminal status.
- `POST /v1/flow/submit` may return `202 {"status":"processing"}`.
  That is a successful acceptance, not an error and not approval.
- `POST /v1/flow/document/process` may return
  `202 {"status":"reading"}`. The hosted flow polls the same
  operation until the read completes. A network interruption during
  a read is not a document verdict.

## 10. Webhooks

Webhooks are the recommended completion mechanism.

Register an endpoint:

```bash
curl -s https://kyc.novamail.store/v1/webhooks \
  -H "Authorization: Bearer $KYC_TEST_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://api.example.com/webhooks/nova-kyc",
    "events": ["session.completed", "case.opened", "case.decided"]
  }'
```

Store the returned `secret` immediately. It is shown once.

### Implemented events

| Event | When it fires | Data |
|---|---|---|
| `session.completed` | A session reaches a decision, including after a reviewer decision | Session view |
| `case.opened` | A review case is created | `case_id`, `session_id`, `reason_codes` |
| `case.decided` | A reviewer decides a case | `case_id`, `session_id`, `outcome`, `reason` |
| `applicant.deleted` | Applicant erasure completes | `applicant_id`, `files_deleted` |
| `screening.hit_new` | Ongoing monitoring finds a new hit | Screening/alert payload |

An endpoint with an empty `events` list receives every implemented
event. Event names that are not implemented do not create a
subscription to a future event by themselves; update the endpoint
when a new event is announced.

### Delivery envelope and headers

The HTTP body is:

```json
{
  "event": "session.completed",
  "data": {
    "id": "SESSION_ID",
    "status": "approved",
    "decision": {"outcome": "approved", "reason_codes": []}
  }
}
```

Headers include:

```http
Content-Type: application/json
KYC-Event: session.completed
KYC-Signature: t=1700000000,v1=HEX_HMAC_SHA256
```

Return any 2xx status promptly. Do slow work after acknowledging
the delivery.

### Verify the signature

The signature is the hex HMAC-SHA256 of:

```text
<timestamp>.<exact raw request body>
```

using the endpoint secret as the key.

Node SDK:

```js
import { verifyWebhookSignature } from './sdk/kyc.mjs';

export async function novaKycWebhook(req, res) {
  const rawBody = await readRawBody(req); // Buffer, not parsed JSON

  const ok = verifyWebhookSignature(
    process.env.KYC_WEBHOOK_SECRET,
    rawBody,
    req.headers['kyc-signature'],
    { maxAgeSec: 300 },
  );
  if (!ok) return res.status(401).end();

  const payload = JSON.parse(rawBody.toString('utf8'));
  await handleNovaKycEvent(payload.event, payload.data);
  return res.status(204).end();
}
```

Python:

```python
import hashlib
import hmac
import time

def verify(secret: str, raw_body: bytes, header: str, max_age=300) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        ts = parts["t"]
        supplied = parts["v1"]
        if abs(int(time.time()) - int(ts)) > max_age:
            return False
    except Exception:
        return False
    expected = hmac.new(
        secret.encode(),
        ts.encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied)
```

Common signature failures:

- verifying a parsed/re-serialised JSON object instead of raw bytes;
- using the tenant API key instead of the webhook endpoint secret;
- reading a different endpoint's secret in a multi-endpoint setup;
- ignoring the timestamp and accepting an old captured delivery.

### Retries, dead letters and replay

- Failed attempts retry with exponential backoff: 30 seconds,
  doubling, up to five attempts by default.
- Every attempt is re-signed with a fresh timestamp.
- Exhausted deliveries become `dead_letter`.
- Inspect them with `GET /v1/webhooks/deliveries?status=dead_letter`.
- Replay one with
  `POST /v1/webhooks/deliveries/{deliveryId}/replay`.
- The receiver must be a public HTTP(S) URL. Loopback, private,
  link-local, reserved and multicast targets are blocked by an SSRF
  guard. Use a public tunnel endpoint for local development rather
  than asking production to call `localhost`.
- Webhook payloads never contain document images or raw biometric
  data.

## 11. Countries and documents

The launch set is NG, GB, US, CA, AU, DE, GH, KE, ZA, IN, PH, SG,
AE, FR, NL and IE. Passports are supported across the launch set;
licences, national IDs and country-specific documents vary.

Do not hard-code a permanent document list into your product. The
flow session returns:

- `allowed_docs`: country → document-kind list;
- `document_registry`: per-document label, side count, expiry
  behaviour, MRZ location and other researched facts.

Nigeria includes passport, driver's licence, voter's card, NIN card
and NIN slip. The NIN slip:

- prints no expiry and no date of birth;
- is never failed for missing either field;
- is the **only** hosted-flow upload exception; and
- requires the applicant's typed 11-digit NIN to tally with the
  number read from the slip.

For all other documents, the product rule remains live camera
scanning only. Unsupported country/document combinations return
`422` rather than silently accepting the wrong template.

## 12. JavaScript SDK reference

Install by copying or vendoring `sdk/kyc.mjs`, or import it from
your server codebase. It has no runtime dependencies beyond Node's
standard library and global `fetch`.

### Client

```js
const kyc = new KycClient({
  apiKey: process.env.KYC_API_KEY,
  baseUrl: 'https://kyc.novamail.store',
});
```

### Method map

| Area | Methods |
|---|---|
| Applicants | `createApplicant`, `getApplicant`, `eraseApplicant` |
| Sessions | `createSession`, `getSession`, `listSessions`, `getSessionChecks`, `cancelSession`, `getSessionCredential`, `absoluteFlowUrl` |
| Keys | `listKeys`, `revokeKey` |
| Users / MFA | `createUser`, `listUsers`, `revokeUser`, `enrollUserMfa`, `confirmUserMfa`, `resetUserMfa` |
| Cases | `listCases`, `getCase`, `decideCase`, `confirmCase`, `disposeCaseHit` |
| Protected media | `getDocumentImageResponse`, `getBiometricImageResponse` |
| KYB | `createBusiness`, `listBusinesses`, `getBusiness`, `addBusinessPerson`, `uploadBusinessDocument`, `registryCheck`, `decideBusinessRegistry`, `evaluateBusiness` |
| Webhooks | `registerWebhook`, `listWebhooks`, `deleteWebhook`, `listDeliveries`, `replayDelivery` |
| Credentials | `verifyCredential`, `revokeCredential` |
| Monitoring | `rescreen`, `listMonitoringAlerts` |
| Billing | `getUsage`, `listInvoices` |
| Configuration | `getConfig`, `updateConfig` |

SDK failures throw `KycError` with:

- `status`: HTTP status;
- `code`: API error code;
- `message`: server message;
- `retryAfter`: seconds from the `Retry-After` header, when present.

Reviewer methods accept an optional final options object:

```js
await kyc.decideCase(caseId, {
  action: 'approve',
  reason: 'Evidence reviewed and accepted',
}, {
  reviewerKey: process.env.KYC_REVIEWER_TOKEN,
  totp: '123456',
});
```

## 13. Review operations

A session that cannot be safely auto-decided opens a case. Review
is a tenant operation, not something an applicant-facing app should
call directly.

### Reviewer identities

- Create named users with `POST /v1/users`; the token is shown once.
- Send it as `X-Reviewer-Key` on case actions.
- Without a named token, actions are recorded as the tenant API-key
  identity with admin role.
- A presented but invalid reviewer token returns `401`; it never
  silently falls back.
- Revoke a user with `POST /v1/users/{id}/revoke`.

### MFA

Reviewers can enrol TOTP MFA:

1. `POST /v1/users/{id}/mfa/enroll`
2. `POST /v1/users/{id}/mfa/confirm` with `{code}`
3. Send `X-Reviewer-TOTP: 123456` on privileged actions when that
   reviewer's MFA is enabled.

`POST /v1/users/{id}/mfa/reset` is tenant-admin recovery. It clears
MFA and forces re-enrolment; there is no bypass code.

### Decisions and four-eyes

- `POST /v1/cases/{id}/decide` requires `action` and `reason`.
- Actions are `approve`, `reject` and `request_more`.
- Some decisions return `202` and park for confirmation by a
  **different** reviewer identity.
- Confirm with `POST /v1/cases/{id}/confirm`.
- A case with a pending screening hit cannot simply be approved:
  dispose the hit first.
- Dispose with `POST /v1/cases/{id}/hits/{hitId}/dispose` and a
  `confirmed` or `false_positive` disposition plus a reason.

### Protected media

Reviewers can read stored media only through:

- `GET /v1/documents/{documentId}/image?side=front|back`
- `GET /v1/biometrics/{biometricId}/image`

Every view is audited. There are no public media URLs. Do not copy
media into tickets, analytics or third-party support tools unless
your own legal and privacy process explicitly permits it.

## 14. Businesses (KYB)

Build a business verification in this order:

1. `POST /v1/businesses` with legal name, registration number and
   country. The number is format-validated.
2. `POST /v1/businesses/{id}/document` with registry evidence.
3. `POST /v1/businesses/{id}/registry-check` to run the configured
   authoritative-registry adapter. It fails closed with
   `not_configured` where no source is connected.
4. A reviewer records the registry leg with
   `POST /v1/businesses/{id}/registry` after examining the evidence.
   This human decision must not be described to your users as
   itself being a live government-registry connection.
5. Create and verify each director/UBO as a normal applicant.
6. Attach each person with
   `POST /v1/businesses/{id}/people`. The endpoint accepts
   `director` or `ubo` and an optional ownership percentage.
7. Run `POST /v1/businesses/{id}/evaluate`.

A business is `verified` only when:

- the registry leg is confirmed;
- at least one person is attached;
- every attached person is approved at Level 2 or above; and
- no attached person has a pending or confirmed screening hit.

Otherwise evaluation returns `pending` or `rejected` with named
reasons.

## 15. Configuration

Read and version flow configuration per level:

```http
GET /v1/config?level=2
PUT /v1/config
```

The PUT body is exactly:

```json
{
  "level": 2,
  "config": {
    "four_eyes": true,
    "sla_hours": 12
  }
}
```

Configurable values include required checks, face threshold and
margin, risk auto-approval ceiling, proof-of-address window,
screening threshold, case SLA and four-eyes. Unknown keys and
out-of-range values return `422`.

Treat configuration changes as production risk changes. Record who
changed them in your own system; Nova KYC records the config
version used by each decision.

## 16. Credentials and ongoing monitoring

### Credentials

- Read an issued credential with
  `GET /v1/sessions/{sessionId}/credential` or, in the flow,
  `GET /v1/flow/credential`.
- Verify with `POST /v1/credentials/verify`.
- Revoke with `POST /v1/credentials/revoke`.
- A credential contains claims and a signature only. Verification
  of a credential must not be represented as access to the original
  documents.

### Monitoring

- Run `POST /v1/monitoring/rescreen` to re-screen approved
  applicants against the current lists.
- Read results with `GET /v1/monitoring/alerts`.
- New matches emit `screening.hit_new` and create/reopen review
  work. Monitoring does not silently reverse an approval without
  the platform's case process.

## 17. Usage and quotas

- Every decided session is metered exactly once.
- Read usage with `GET /v1/usage?from=…&to=…`; the default period
  is the current UTC month.
- Read invoices with `GET /v1/invoices`.
- Test-environment usage is priced at zero.
- Live prices and monthly quotas are operator configuration; do
  not hard-code a commercial price from an old document or sales
  conversation into your integration.
- A live session creation that would exceed a configured monthly
  quota returns `429` with code `quota_exceeded`.

The tenant dashboard at `/dashboard` is the human view of keys,
usage, invoices, webhook endpoints and recent sessions.

## 18. Errors, retries, limits and idempotency

### Error shape

```json
{
  "error": {
    "code": "validation_error",
    "message": "country required"
  }
}
```

Many validation and not-found responses use the HTTP status as the
string code. Production code should therefore branch first on the
HTTP status, then inspect `error.code` for the semantic cases it
knows. Do not parse the human message as an API contract.

### HTTP status guide

| Status | Meaning | Retry? |
|---:|---|---|
| 200 / 201 | Success | — |
| 202 | Accepted: document reading or session processing is still running, or a case is parked for confirmation | Poll the documented resource |
| 400 | Malformed request in an operation that uses it | Fix the request |
| 401 | Missing/invalid/revoked tenant key, flow token or reviewer token | Do not retry until credentials are corrected |
| 403 | Operator-only route, VPN/proxy gate, MFA enrolment requirement or another explicit prohibition | Do not retry unchanged |
| 404 | Not found, wrong tenant, or wrong environment | Check ids and key environment |
| 409 | State conflict, duplicate attachment, MFA state conflict or replay against a deleted endpoint | Read current state first |
| 413 | Body over the configured request limit | Reduce or split only where the product supports it; do not bypass capture rules |
| 416 | Invalid media byte range | Correct the range |
| 422 | Validation failed | Correct the named field/state |
| 429 | Rate limited (`rate_limited`) or quota reached (`quota_exceeded`) | Wait for `Retry-After` or the next quota period |
| 500 | Internal error | Retry with exponential backoff; report the time and operation if persistent |
| 503 | Required capability or storage key unavailable | Treat as platform incident, not applicant failure |

Important semantic codes include:

- `body_too_large`
- `rate_limited`
- `quota_exceeded`
- `vpn_proxy_detected`
- `mfa_invalid`
- `mfa_required_or_invalid`
- `mfa_enrollment_required`
- `tenant_bootstrap_restricted`
- `billing_admin_restricted`
- `platform_metrics_restricted`
- `platform_admin_required`
- `storage_unavailable`
- `storage_error`

### Rate limits

Default in-memory sliding-window limits are:

| Scope | Default |
|---|---:|
| Per API credential or reviewer token | 1,200 requests/minute |
| Per hosted-flow token | 240 requests/minute |
| Per client IP across `/v1/*` | 6,000 requests/minute |

Operators can tune these values. On `429`, honour `Retry-After`.
Default maximum request body is 25 MB; larger requests return
`413` before processing.

### Idempotency — read this before retrying creation

`Idempotency-Key` is **not currently honoured**. Creation endpoints
do not deduplicate based on that header.

Safe retry practice:

- For a timed-out `POST /v1/sessions`, first list/read sessions for
  the applicant in your own mapping and reconcile before creating
  another.
- Keep your own operation id in your database and in
  `external_ref` where the resource supports it.
- Never blindly retry a case decision, hit disposition, credential
  revocation or erasure. Read the current state first.

## 19. Security and privacy checklist

Before launch, confirm all of the following:

- [ ] Tenant keys live only in a server-side secret manager.
- [ ] Test and live keys are separate configuration values.
- [ ] Flow tokens are never written to logs, analytics or URLs you
      share with third parties.
- [ ] Webhook verification uses the endpoint secret and raw body.
- [ ] Webhook handlers are idempotent in **your** database: a
      redelivery must not grant a benefit twice.
- [ ] Your database stores applicant/session ids and outcomes, not
      copies of document or biometric media.
- [ ] Support tooling displays reason codes without exposing more
      personal data than the support task needs.
- [ ] Reviewer accounts are named people, MFA is enrolled, and
      revoked users are removed promptly.
- [ ] Erasure requests call `DELETE /v1/applicants/{id}` and your
      product also deletes its own derived records according to its
      retention policy.
- [ ] Your privacy notice explains that identity data is processed
      by Nova KYC, why it is processed, and how a person can ask the
      business that sent them for deletion.
- [ ] VPN/proxy behaviour is acceptable for your population: Nova
      KYC hard-blocks detected VPN/proxy use in the flow.
- [ ] Your app does not claim a person is verified until your
      backend has an `approved` session.

## 20. Testing an integration

### Test mode is not a fake-outcome sandbox

Test keys run the same checks and decision pipeline as live keys.
“Test” means data separation and zero-priced metering, not a
deterministic approval button. A bad document, mismatched identity
or failed biometric check can fail in test mode for the same reason
it would fail live.

### Recommended test sequence

1. **Connectivity:** call `GET /v1/keys` with the test key. A `401`
   means the key is wrong, revoked or being sent incorrectly.
2. **Happy path:** create a document-sourced applicant and a Level 1
   session; complete the hosted flow with a supported document.
3. **Biometric path:** repeat at Level 2.
4. **Enhanced path:** repeat at Level 3 with proof of address.
5. **Webhook:** register a public test receiver, verify signatures,
   force a failure and confirm retry/dead-letter visibility.
6. **Negative paths:** expired session, cancelled session, wrong
   environment key, unsupported document, VPN enabled, reviewer
   request-more, and a case requiring four-eyes confirmation.
7. **Credential path:** approve a session, fetch and verify its
   credential, seed a second session, then revoke and verify again.
8. **Erasure:** erase a test applicant and confirm your product's
   own state follows the `applicant.deleted` event.

### Local development

Run the platform locally and use its development port:

```bash
python3 -m server --port 8765
```

The repository's automated suite and local end-to-end tooling are
the source for synthetic fixtures. Do not use a real person's
documents in tickets, screenshots, public issues or shared test
reports.

## 21. Troubleshooting

| Symptom | Likely cause | Correct response |
|---|---|---|
| Every call returns `401` | Missing `Bearer`, revoked key, or the server received a reviewer/flow token as a tenant key | Check the credential type and environment |
| An id returns `404` with one key but works with another | Test/live environment mismatch or cross-tenant id | Use the key that created the resource |
| Session creation returns `422 applicant_id or credential required` | The request had none of the three session-source forms | Send an applicant id, a document-source country, or a credential |
| Session creation returns `429 quota_exceeded` | Monthly live cap reached | Use test mode for development or ask the operator about the live quota |
| Flow stops with VPN/proxy detected | The applicant's connection matched the VPN/proxy gate | Ask the applicant to disable VPN/proxy and start again; do not try to bypass it |
| Flow link returns invalid/expired | Token was cancelled, expired, mistyped or already belongs to a terminal session | Create a fresh session |
| Document upload returns `422` for the kind/country | The pair is not in the session registry | Read `document_registry` / `allowed_docs` from `GET /v1/flow/session` |
| Typed number accepted only for NIN slip | Another document kind sent `claimed_number` | Remove it; the exception is NIN-slip only |
| Document process keeps returning `202` | The fortified read is still running | Continue polling; investigate only if it persists beyond the platform's normal read window |
| Submit returns `202` | Decision processing is running | Read the session or wait for `session.completed`; do not resubmit in a loop |
| Webhook signature always fails | Body was parsed/re-serialised, wrong secret, or a proxy changed the body | Verify the exact raw bytes with the endpoint secret |
| Webhook endpoint is registered but never called | Event filter does not include the event, endpoint is in the other environment, or delivery is blocked/dead-lettered | Check deliveries and endpoint env/events |
| Webhook receiver on localhost is blocked | SSRF guard correctly refuses private targets in production | Expose a public development receiver |
| Reviewer action returns `401 mfa_required_or_invalid` | MFA-enabled reviewer did not send a current TOTP code | Send `X-Reviewer-TOTP` with the current code |
| Business registry check says `not_configured` | No authoritative adapter/credential is configured for that country | Use the evidence + reviewer registry process; do not describe the business as registry-verified from format alone |
| Business evaluation stays `pending` | Registry unconfirmed, a person is not Level 2+, or a hit is pending | Read the returned named reasons |

## 22. Versioning and compatibility

- The HTTP API is versioned in the path as `/v1`.
- The OpenAPI document carries its own specification version and
  should be pinned in generated-client repositories.
- New optional response fields can appear; clients must ignore
  unknown fields.
- Do not depend on human-readable error messages.
- Session status and check names are contracts; reason-code sets
  can grow as new document and fraud evidence is added. Treat an
  unknown reason code as a non-approval unless the session outcome
  itself is `approved`.
- Flow pages and flow endpoints are released together. If you build
  an advanced wrapper, pin and test it against the OpenAPI version
  you deployed with.

## 23. What is not currently offered

State these boundaries plainly in your own product planning:

- No public self-service tenant signup API.
- No tenant-supplied `return_url` for the hosted flow.
- No supported iframe/embed SDK or postMessage protocol.
- No public native iOS/Android capture SDK.
- No general API-only document, selfie or liveness upload.
- No `Idempotency-Key` deduplication.
- No document images or raw biometric data in webhooks or
  reusable credentials.
- No promise that every country's business registry has a live
  adapter; registry adapters fail closed as `not_configured`.

These are product boundaries, not documentation gaps to work
around. Build on the hosted-flow contract above.
