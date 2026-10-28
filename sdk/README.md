# Nova KYC — JavaScript SDK

Zero-dependency client for the Nova KYC API. Node 18+ / modern
browsers (global `fetch`). Server-side use is the primary target —
API keys must never ship to a browser.

```js
import { KycClient, verifyWebhookSignature } from './kyc.mjs';

const kyc = new KycClient({ apiKey: process.env.KYC_API_KEY });

// 1. Create the applicant + a verification session
const applicant = await kyc.createApplicant({ country: 'NG' });
const session = await kyc.createSession({ applicantId: applicant.id, level: 1 });

// 2. Send the user to the hosted flow (phone-first; desktop shows
//    a QR handoff). session.flow_url is a path on the platform.
redirectUserTo('https://kyc.novamail.store' + session.flow_url);

// 3. Learn the outcome: poll, or (better) receive the webhook.
const done = await kyc.getSession(session.id);   // .status / .decision
```

Webhooks — register an endpoint, then verify every delivery with
the endpoint secret before trusting it:

```js
await kyc.registerWebhook({
  url: 'https://your-app.example/kyc/webhook',
  events: ['session.completed', 'case.decided'],
});

// in your webhook handler (raw body required):
if (!verifyWebhookSignature(process.env.KYC_WEBHOOK_SECRET, rawBody,
                            req.headers['kyc-signature'])) {
  return reply(401);
}
```

Full walkthrough: [docs/INTEGRATION.md](../docs/INTEGRATION.md).
Your usage, invoices and endpoints are also visible in the
tenant dashboard at `https://kyc.novamail.store/dashboard`.
