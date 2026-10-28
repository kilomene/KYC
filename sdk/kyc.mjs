/**
 * Nova KYC — JavaScript SDK (zero dependencies).
 *
 * Server-side Node 18+ is the supported target. Your API key is a
 * secret: never ship it to a browser, a mobile app, a public repo,
 * or an AI-agent prompt. The applicant-facing verification itself
 * is a hosted page — your server creates a session and sends the
 * person to the returned flow URL.
 *
 *   import { KycClient, verifyWebhookSignature } from './kyc.mjs';
 *
 *   const kyc = new KycClient({ apiKey: process.env.KYC_API_KEY });
 *   const applicant = await kyc.createApplicant({ country: 'NG' });
 *   const session = await kyc.createSession({
 *     applicantId: applicant.id,
 *     level: 2,
 *   });
 *   redirectTheUserTo(kyc.absoluteFlowUrl(session));
 *
 * Method names use JavaScript camelCase. Request and response field
 * names remain the API's snake_case names so SDK objects can be
 * compared directly with the OpenAPI specification.
 */
import { createHmac, timingSafeEqual } from 'node:crypto';

export class KycError extends Error {
  constructor(status, code, message, retryAfter = null) {
    super(message);
    this.name = 'KycError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

function cleanObject(fields) {
  const out = {};
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) out[key] = value;
  }
  return out;
}

export class KycClient {
  constructor({ apiKey, baseUrl = 'https://kyc.novamail.store' } = {}) {
    if (!apiKey) throw new Error('KycClient: apiKey is required');
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async _call(method, path, body, { headers = {} } = {}) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return this._readResponse(res);
  }

  async _form(method, path, formData) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: { Authorization: `Bearer ${this.apiKey}` },
      body: formData,
    });
    return this._readResponse(res);
  }

  async _binary(method, path) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const e = data.error || {};
      throw new KycError(res.status, e.code || 'http_error', e.message || `HTTP ${res.status}`);
    }
    return res;
  }

  async _readResponse(res) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = data.error || {};
      const retry = res.headers.get('Retry-After');
      throw new KycError(
        res.status,
        e.code || 'http_error',
        e.message || `HTTP ${res.status}`,
        retry === null ? null : Number(retry),
      );
    }
    return data;
  }

  _reviewHeaders({ reviewerKey, totp } = {}) {
    return cleanObject({
      'X-Reviewer-Key': reviewerKey,
      'X-Reviewer-TOTP': totp,
    });
  }

  /** Return an absolute hosted-flow URL for a create-session result. */
  absoluteFlowUrl(session) {
    if (!session) return null;
    if (session.flow_url && /^https?:\/\//.test(session.flow_url)) return session.flow_url;
    if (session.flow_url) return this.baseUrl + session.flow_url;
    if (session.flow_token) return `${this.baseUrl}/flow/${session.flow_token}`;
    return null;
  }

  // --- applicants and sessions ------------------------------------
  /**
   * Create an applicant. By default identitySource is "document":
   * only the country is required and identity is read from the
   * document. For the declared path, pass identitySource:"declared"
   * plus firstName, lastName and dob.
   */
  createApplicant({
    country,
    identitySource = 'document',
    firstName,
    lastName,
    dob,
    externalRef,
    email,
    phone,
    addressLine,
    city,
  } = {}) {
    return this._call('POST', '/v1/applicants', cleanObject({
      country,
      identity_source: identitySource,
      first_name: firstName,
      last_name: lastName,
      dob,
      external_ref: externalRef,
      email,
      phone,
      address_line: addressLine,
      city,
    }));
  }

  getApplicant(id) { return this._call('GET', `/v1/applicants/${id}`); }
  eraseApplicant(id) { return this._call('DELETE', `/v1/applicants/${id}`); }

  /**
   * Create a session from exactly one source:
   * - applicantId, or
   * - identitySource:"document" + country, or
   * - a reusable credential object.
   */
  createSession({
    applicantId,
    level = 1,
    expiresHours,
    credential,
    identitySource,
    country,
    externalRef,
  } = {}) {
    return this._call('POST', '/v1/sessions', cleanObject({
      applicant_id: applicantId,
      level,
      expires_hours: expiresHours,
      credential,
      identity_source: identitySource,
      country,
      external_ref: externalRef,
    }));
  }

  getSession(id) { return this._call('GET', `/v1/sessions/${id}`); }
  listSessions() { return this._call('GET', '/v1/sessions'); }
  getSessionChecks(id) { return this._call('GET', `/v1/sessions/${id}/checks`); }
  cancelSession(id) { return this._call('POST', `/v1/sessions/${id}/cancel`); }
  getSessionCredential(id) { return this._call('GET', `/v1/sessions/${id}/credential`); }

  // --- API keys -----------------------------------------------------
  listKeys() { return this._call('GET', '/v1/keys'); }
  revokeKey(id) { return this._call('POST', `/v1/keys/${id}/revoke`); }

  // --- tenant users and reviewer MFA --------------------------------
  createUser({ name, role } = {}) { return this._call('POST', '/v1/users', { name, role }); }
  listUsers() { return this._call('GET', '/v1/users'); }
  revokeUser(id) { return this._call('POST', `/v1/users/${id}/revoke`); }
  enrollUserMfa(id) { return this._call('POST', `/v1/users/${id}/mfa/enroll`); }
  confirmUserMfa(id, code) { return this._call('POST', `/v1/users/${id}/mfa/confirm`, { code }); }
  resetUserMfa(id) { return this._call('POST', `/v1/users/${id}/mfa/reset`); }

  // --- review cases ---------------------------------------------------
  listCases() { return this._call('GET', '/v1/cases'); }
  getCase(id) { return this._call('GET', `/v1/cases/${id}`); }
  decideCase(id, { action, reason } = {}, reviewer = {}) {
    return this._call('POST', `/v1/cases/${id}/decide`, { action, reason },
                      { headers: this._reviewHeaders(reviewer) });
  }
  confirmCase(id, { reason } = {}, reviewer = {}) {
    return this._call('POST', `/v1/cases/${id}/confirm`, { reason },
                      { headers: this._reviewHeaders(reviewer) });
  }
  disposeCaseHit(caseId, hitId, { disposition, reason } = {}, reviewer = {}) {
    return this._call('POST', `/v1/cases/${caseId}/hits/${hitId}/dispose`,
                      { disposition, reason },
                      { headers: this._reviewHeaders(reviewer) });
  }

  /** Authorized, audited media downloads. The returned Response is a stream source; use .arrayBuffer() or .blob(). */
  getDocumentImageResponse(id, side = 'front') {
    return this._binary('GET', `/v1/documents/${id}/image?side=${encodeURIComponent(side)}`);
  }
  getBiometricImageResponse(id) {
    return this._binary('GET', `/v1/biometrics/${id}/image`);
  }

  // --- businesses (KYB) ---------------------------------------------
  createBusiness(fields) { return this._call('POST', '/v1/businesses', fields); }
  listBusinesses() { return this._call('GET', '/v1/businesses'); }
  getBusiness(id) { return this._call('GET', `/v1/businesses/${id}`); }
  addBusinessPerson(id, { applicantId, role, ownershipPct } = {}) {
    return this._call('POST', `/v1/businesses/${id}/people`, cleanObject({
      applicant_id: applicantId,
      role,
      ownership_pct: ownershipPct,
    }));
  }
  uploadBusinessDocument(id, file, { kind = 'registration', filename } = {}) {
    const form = new FormData();
    if (filename) form.append('document', file, filename);
    else form.append('document', file);
    form.append('kind', kind);
    return this._form('POST', `/v1/businesses/${id}/document`, form);
  }
  registryCheck(id) { return this._call('POST', `/v1/businesses/${id}/registry-check`, {}); }
  decideBusinessRegistry(id, { status, reason } = {}, reviewer = {}) {
    return this._call('POST', `/v1/businesses/${id}/registry`, { status, reason },
                      { headers: this._reviewHeaders(reviewer) });
  }
  evaluateBusiness(id) { return this._call('POST', `/v1/businesses/${id}/evaluate`, {}); }

  // --- webhooks -------------------------------------------------------
  registerWebhook({ url, events } = {}) {
    return this._call('POST', '/v1/webhooks', { url, events });
  }
  listWebhooks() { return this._call('GET', '/v1/webhooks'); }
  deleteWebhook(id) { return this._call('DELETE', `/v1/webhooks/${id}`); }
  listDeliveries(status) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return this._call('GET', `/v1/webhooks/deliveries${qs}`);
  }
  replayDelivery(id) { return this._call('POST', `/v1/webhooks/deliveries/${id}/replay`); }

  // --- credentials and monitoring ------------------------------------
  verifyCredential(credential) {
    return this._call('POST', '/v1/credentials/verify', { credential });
  }
  revokeCredential(credentialId) {
    return this._call('POST', '/v1/credentials/revoke', { credential_id: credentialId });
  }
  rescreen() { return this._call('POST', '/v1/monitoring/rescreen', {}); }
  listMonitoringAlerts() { return this._call('GET', '/v1/monitoring/alerts'); }

  // --- usage and billing ----------------------------------------------
  getUsage({ from, to } = {}) {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    const qs = q.toString();
    return this._call('GET', '/v1/usage' + (qs ? `?${qs}` : ''));
  }
  listInvoices() { return this._call('GET', '/v1/invoices'); }

  // --- flow configuration ---------------------------------------------
  getConfig(level) { return this._call('GET', `/v1/config?level=${level}`); }
  updateConfig(level, patch) {
    // The wire shape is {level, config:{...}}.
    return this._call('PUT', '/v1/config', { level, config: patch });
  }
}

/**
 * Verify a webhook delivery.
 *
 * The platform signs every attempt with:
 *   KYC-Signature: t=<unix_ts>,v1=<hex hmac-sha256>
 * over the string "<t>.<raw request body>" using the endpoint
 * secret. Pass the RAW body (string or Buffer) — never a parsed and
 * re-serialised JSON object.
 *
 * By default this checks the HMAC only. Pass {maxAgeSec: 300} to
 * also reject a correctly signed but stale delivery timestamp.
 */
export function verifyWebhookSignature(secret, rawBody, signatureHeader, { maxAgeSec, nowSec } = {}) {
  if (!secret || !signatureHeader) return false;
  const parts = {};
  for (const kv of String(signatureHeader).split(',')) {
    const splitAt = kv.indexOf('=');
    if (splitAt < 1) continue;
    parts[kv.slice(0, splitAt).trim()] = kv.slice(splitAt + 1).trim();
  }
  if (!parts.t || !parts.v1) return false;
  if (maxAgeSec !== undefined) {
    const ts = Number(parts.t);
    const now = nowSec === undefined ? Math.floor(Date.now() / 1000) : nowSec;
    if (!Number.isFinite(ts) || Math.abs(now - ts) > maxAgeSec) return false;
  }
  const body = Buffer.isBuffer(rawBody) ? rawBody : Buffer.from(String(rawBody));
  const expected = createHmac('sha256', secret)
    .update(Buffer.concat([Buffer.from(parts.t + '.'), body]))
    .digest('hex');
  const a = Buffer.from(expected);
  const b = Buffer.from(parts.v1);
  return a.length === b.length && timingSafeEqual(a, b);
}

export default KycClient;
