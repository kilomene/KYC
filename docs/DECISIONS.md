# KYC — Open Decisions for the Owner

*The build does not guess these. Each has a recommendation; the owner's
word settles it. Answered decisions move into the blueprint as facts, with
the date.*

## D1. Brand home — is KYC a Nova Inc product?

- **Options:** (a) A Nova Inc product (inherits the Nova Inc brand lock:
  company name, "Nova Inc" sender name on mail, ecosystem listing), or
  (b) a standalone brand of its own.
- **Recommendation:** (a) Nova Inc — trust is the product in KYC, and Nova
  Inc is the owner's trust brand; Payments and Exchange are natural first
  tenants.
- **Affects:** naming in product, mail sender, domain, ecosystem page.

## D2. First customer — who do we build Phase 1 for?

- **Options:** (a) Internal first (Nova Payments / Agent Exchange verify
  their users through it), (b) external tenants from day one,
  (c) internal first, external in Phase 2 once proven.
- **Recommendation:** (c) — real internal traffic proves it; external
  sales start from evidence, not promises.

## D3. Launch document / country coverage

- **Proposal for Phase 1:** Nigeria (international passport, driver's
  licence, national ID / NIN card) + United States (passport, state
  driver's licence / ID) + United Kingdom (passport, driving licence).
- **Why:** owner's base (Nigeria + Houston, US) and the documents he can
  test with real people legally and safely.
- **Owner to confirm or change the set.** Every added country is real work
  (templates, tests) — we list only what we have tested.

## D4. Stack confirmation

- **Proposal:** Supabase (Postgres, Auth, Storage, Edge Functions) +
  Cloudflare Pages — the owner's proven pattern on Exchange/Payments.
- **Alternative:** a dedicated backend (e.g. Node/Go service) if check
  workers outgrow Edge Functions in Phase 2.
- **Recommendation:** confirm Supabase + Cloudflare for Phase 1; keep the
  provider-interface design so Phase 2 can add workers anywhere.

## D5. Face match / liveness — build or plug (Phase 2)

- **Options:** evaluate established ML providers behind our interface vs
  building our own models (owner already runs model-training work).
- **Recommendation:** plug first for Phase 2 launch speed, evaluate own
  models in parallel against the same acceptance tests; swap only when
  ours win on evidence. No provider is named in the product until the
  evaluation is done.

## D6. Domain

- **Proposal:** `kyc.novamail.store` (subdomain only, per the owner's
  root-domain rule), created when Phase 1 is ready to deploy — not before.

## D7. Pricing

- **Proposal:** per-verification by level (BLUEPRINT §10), free sandbox,
  no charge for expired-untouched or our-error sessions.
- **Owner to set:** actual prices and currency once Phase 1 costs
  (provider fees per check) are measured. Pricing before measuring check
  costs would be guessing.

## D8. Repo visibility

- Repo is public now per the owner's instruction and may go private later.
- **Trigger to decide:** before any real code, keys structure, or provider
  detail lands — blueprint is safe public; implementation may not be.
