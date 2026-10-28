# Nova KYC — JavaScript SDK

Zero-dependency server-side client for the Nova KYC API.

- **Runtime:** Node 18+ (global `fetch` and Node standard library)
- **Use:** backend services only
- **Never:** ship the API key to a browser or mobile app
- **Full guide:** [`docs/DEVELOPER.md`](../docs/DEVELOPER.md)
- **Machine-readable contract:** [`docs/openapi.json`](../docs/openapi.json)
  or <https://kyc.novamail.store/openapi.json>

## Quickstart

```js
import { KycClient, verifyWebhookSignature } from './kyc.mjs';

const kyc = new KycClient({
  apiKey: process.env.KYC_API_KEY,
  baseUrl: process.env.KYC_BASE_URL || 'https://kyc.novamail.store',
});

// 1. Create an applicant whose identity will be read from the document.
const applicant = await kyc.createApplicant({
  country: 'NG',
  identitySource: 'document',
  externalRef: 'user_12345',
});

// 2. Create a session.
const session = await kyc.createSession({
  applicantId: applicant.id,
  level: 2,
  expiresHours: 24,
});

// 3. Send only this one-session URL to the applicant.
const verificationUrl = kyc.absoluteFlowUrl(session);

// 4. Read the authoritative outcome from your backend.
const result = await kyc.getSession(session.id);
console.log(result.status, result.decision);
```

For the declared cross-check path:

```js
const applicant = await kyc.createApplicant({
  country: 'NG',
  identitySource: 'declared',
  firstName: 'Adaeze',
  lastName: 'Example',
  dob: '1992-04-17',
  externalRef: 'user_12345',
});
```

## Webhooks

Register an endpoint:

```js
const endpoint = await kyc.registerWebhook({
  url: 'https://your-app.example/webhooks/nova-kyc',
  events: ['session.completed', 'case.opened', 'case.decided'],
});

// Store endpoint.secret now. It is shown once.
```

Verify every delivery against the **raw request body**:

```js
const ok = verifyWebhookSignature(
  process.env.KYC_WEBHOOK_SECRET,
  rawBody,
  req.headers['kyc-signature'],
  { maxAgeSec: 300 },
);
if (!ok) return reply(401);
```

The optional `maxAgeSec` also rejects stale signed timestamps.
Without it, the function checks the HMAC only.

## Method map

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

Reviewer operations accept a final options object:

```js
await kyc.decideCase(caseId, {
  action: 'approve',
  reason: 'Evidence reviewed and accepted',
}, {
  reviewerKey: process.env.KYC_REVIEWER_TOKEN,
  totp: '123456',
});
```

Errors throw `KycError` with `status`, `code`, `message`, and
`retryAfter` (seconds, when the server sends `Retry-After`).

## Website and mobile handoff

The SDK creates sessions; it does not embed the verification flow.
For a website, navigate to `absoluteFlowUrl(session)` or open it in
a new tab. For a mobile app, open it in a system browser, iOS
in-app browser surface or Android Custom Tab, and refresh status
from your backend when the app resumes.

There is no supported iframe SDK, native capture SDK, or session
`return_url`. See the website and mobile chapters in
[`docs/DEVELOPER.md`](../docs/DEVELOPER.md).

Your tenant dashboard is at
<https://kyc.novamail.store/dashboard>. The developer portal is
<https://kyc.novamail.store/docs>.
