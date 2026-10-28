/**
 * Nova KYC — JavaScript SDK (zero dependencies).
 *
 * Works in Node 18+ and modern browsers (uses the global fetch).
 * Server-side use is the primary target: your API keys must never
 * ship to a browser. The applicant-facing flow is a hosted page —
 * you create a session server-side and send the user to its link.
 *
 *   import { KycClient, verifyWebhookSignature } from './kyc.mjs';
 *   const kyc = new KycClient({ apiKey: process.env.KYC_API_KEY });
 *   const applicant = await kyc.createApplicant({ country: 'NG' });
 *   const session = await kyc.createSession({ applicantId: applicant.id, level: 1 });
 *   // redirect the user to session.flow_url to complete verification
 */
import { createHmac, timingSafeEqual } from 'node:crypto';

export class KycError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'KycError';
    this.status = status;
    this.code = code;
  }
}

export class KycClient {
  constructor({ apiKey, baseUrl = 'https://kyc.novamail.store' } = {}) {
    if (!apiKey) throw new Error('KycClient: apiKey is required');
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async _call(method, path, body) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = data.error || {};
      throw new KycError(res.status, e.code || 'http_error', e.message || `HTTP ${res.status}`);
    }
    return data;
  }

  // --- applicants & sessions -------------------------------------
  createApplicant({ country, identitySource = 'document', externalRef } = {}) {
    return this._call('POST', '/v1/applicants', {
      country, identity_source: identitySource, external_ref: externalRef,
    });
  }
  getApplicant(id) { return this._call('GET', `/v1/applicants/${id}`); }
  eraseApplicant(id) { return this._call('DELETE', `/v1/applicants/${id}`); }

  createSession({ applicantId, level = 1 } = {}) {
    return this._call('POST', '/v1/sessions', { applicant_id: applicantId, level });
  }
  getSession(id) { return this._call('GET', `/v1/sessions/${id}`); }
  listSessions() { return this._call('GET', '/v1/sessions'); }

  // --- businesses (KYB) -------------------------------------------
  createBusiness(fields) { return this._call('POST', '/v1/businesses', fields); }
  getBusiness(id) { return this._call('GET', `/v1/businesses/${id}`); }
  registryCheck(id) { return this._call('POST', `/v1/businesses/${id}/registry-check`, {}); }

  // --- webhooks -----------------------------------------------------
  registerWebhook({ url, events } = {}) {
    return this._call('POST', '/v1/webhooks', { url, events });
  }
  listWebhooks() { return this._call('GET', '/v1/webhooks'); }
  deleteWebhook(id) { return this._call('DELETE', `/v1/webhooks/${id}`); }
  listDeliveries() { return this._call('GET', '/v1/webhooks/deliveries'); }

  // --- usage & billing ----------------------------------------------
  getUsage({ from, to } = {}) {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    const qs = q.toString();
    return this._call('GET', '/v1/usage' + (qs ? `?${qs}` : ''));
  }
  listInvoices() { return this._call('GET', '/v1/invoices'); }

  // --- flow configuration -------------------------------------------
  getConfig(level) { return this._call('GET', `/v1/config?level=${level}`); }
  updateConfig(level, patch) { return this._call('PUT', '/v1/config', { level, config: patch }); }
}

/**
 * Verify a webhook delivery. The platform signs every delivery:
 *   KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
 * over the string "<t>.<raw request body>" with your endpoint's
 * secret. Pass the RAW body (string or Buffer) — never a re-serialised
 * JSON object. Returns true/false; also reject stale timestamps in
 * your handler if replay matters to you.
 */
export function verifyWebhookSignature(secret, rawBody, signatureHeader) {
  if (!secret || !signatureHeader) return false;
  const parts = {};
  for (const kv of String(signatureHeader).split(',')) {
    const [k, v] = kv.split('=', 2);
    if (k && v) parts[k.trim()] = v.trim();
  }
  if (!parts.t || !parts.v1) return false;
  const body = Buffer.isBuffer(rawBody) ? rawBody : Buffer.from(String(rawBody));
  const expected = createHmac('sha256', secret)
    .update(Buffer.concat([Buffer.from(parts.t + '.'), body]))
    .digest('hex');
  const a = Buffer.from(expected);
  const b = Buffer.from(parts.v1);
  return a.length === b.length && timingSafeEqual(a, b);
}

export default KycClient;
