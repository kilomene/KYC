# KYC — Architecture (Proposed)

*Proposal, following the owner's proven stack pattern (Supabase +
Cloudflare). Final stack confirmation is an owner decision — DECISIONS.md.*

## 1. Shape

```
Applicant (phone/browser)          Tenant systems
        │                                │
        ▼                                ▼
┌────────────────┐   sessions   ┌──────────────────┐
│  Hosted Flow   │◄────────────►│   Tenant API     │
│ (Cloudflare    │              │ (Supabase Edge   │
│  Pages, static)│              │  Functions)      │
└───────┬────────┘              └────────┬─────────┘
        │ uploads (signed URLs)          │
        ▼                                ▼
┌──────────────────────────────────────────────────┐
│ Private Storage (Supabase Storage, encrypted,    │
│ no public buckets, short-lived signed access)    │
└───────┬──────────────────────────────────────────┘
        │ events
        ▼
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│  Check Workers │──►│ Decision Engine│──►│ Webhook        │
│ (queue-driven: │   │ (rules per     │   │ Dispatcher     │
│ OCR, face,     │   │ tenant+level)  │   │ (HMAC-signed,  │
│ liveness,      │   └───────┬────────┘   │ retries, log)  │
│ screening)     │           ▼            └────────────────┘
└────────────────┘   ┌────────────────┐
                     │ Review Console │  ◄── Reviewers (dashboard)
                     └────────────────┘
        All data: Supabase Postgres, Row-Level Security per tenant.
        All actions: append-only audit log.
```

## 2. Components

| Component | Job | Proposed tech |
|---|---|---|
| Hosted applicant flow | Consent, details, capture, selfie, status | Static web app on Cloudflare Pages; camera via `getUserMedia`; works without an app install |
| Tenant dashboard / review console | Queues, cases, keys, webhooks, billing, settings | Same Pages deployment, authenticated area |
| API | Sessions, applicants, uploads, decisions | Supabase Edge Functions (Deno/TypeScript), REST, versioned `/v1` |
| Database | All state, RLS isolation per tenant | Supabase Postgres |
| File storage | ID images, selfies, PoA — private only | Supabase Storage private buckets, signed URLs (minutes, not hours), per-object tenant/applicant pathing |
| Check workers | OCR/MRZ, face match, liveness, authenticity, screening | Queue + worker functions; each check is an independent job with its own timeout and retry budget |
| Decision engine | Applies tenant+level rules to check results | Deterministic code (no LLM decisions on identity — ever) |
| Webhooks | Decision + status events to tenants | HMAC-signed POSTs, exponential backoff, dead-letter + manual replay |
| Email/notifications | Session links, reviewer alerts, tenant notices | Transactional mail from the platform domain, display-name rules per owner brand decision |

## 3. Provider strategy — build vs plug

Checks are defined by **our interface**, not by a vendor's API. Each check
type has a provider slot:

- **Phase 1:** one provider per check where we must not build (watchlist
  data), our own pipeline where building is realistic (capture quality,
  OCR/MRZ, expiry/consistency rules).
- **Face match / liveness / document authenticity:** Phase 1 evaluates
  established ML providers behind our interface *and* an own-model track;
  whichever ships must pass the Phase 2 acceptance tests on real devices.
  The blueprint does not name a winner before that evaluation — naming one
  now would be a guess dressed as a plan.
- **No provider lock-in:** swapping a provider changes one adapter, never
  the API, data model, or decision rules.
- **Provider outage = degraded, visible, fail-closed** (see BLUEPRINT §6).

## 4. Tenancy & isolation

- Every row carries `tenant_id`; Postgres RLS enforces tenant isolation at
  the database, not just in app code.
- Storage paths are tenant/applicant-scoped; signed URLs are minted only
  after an RLS-checked authorisation.
- Platform-admin access to applicant PII is break-glass: explicit action,
  reason required, time-boxed, audit-logged, and visible to the tenant.

## 5. Environments & domain

- `test` (sandbox: fake documents, deterministic outcomes, no real PII
  allowed) and `live`, separated by API keys and data.
- Proposed home: a subdomain of the owner's domain (e.g.
  `kyc.novamail.store`) — **subdomain only**, per the owner's standing
  root-domain rule, and only when the owner confirms KYC's brand home.
- CI: build + test on this machine first; push once when green; never
  stack CI runs (owner's standing build discipline).

## 6. Scale assumptions (design targets, not claims)

- Stateless API/workers; queue absorbs capture bursts.
- Decision latency target in BLUEPRINT §13 drives worker timeouts:
  individual check budget ≤ 30s, full automated Level 2 ≤ 2 min p50.
- Storage growth is dominated by images; retention enforcement (see
  COMPLIANCE-AND-PRIVACY) is a scheduled job, not a hope.

## 7. Observability

- Structured logs with tenant/session ids — **never** PII or image data in
  logs.
- Metrics per check: volume, pass/fail/unclear, latency, provider errors.
- Alerts: provider outage, webhook failure spikes, review-queue SLA
  breach, anomalous approval-rate movement (attack signal).
