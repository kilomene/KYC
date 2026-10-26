# KYC — Decisions

*The build does not guess these. Answered decisions are facts, with dates.*

## SETTLED — 2026-10-26, by the owner: "Approve it — go with the recommendations and start Phase 1"

### D1. Brand home — SETTLED: Nova Inc product
KYC is a **Nova Inc** product. It inherits the Nova Inc brand lock
unchanged (company name; shared company mail sends under the display name
"Nova Inc"; ecosystem listing as a Nova Inc product). Payments and
Exchange are natural first tenants.

### D2. First customer — SETTLED: internal first (explained 2026-10-26)
"Internal first" means: the **first businesses to use KYC are our own
Nova Inc platforms** (Nova Payments, Agent Exchange) verifying their own
users. Outside companies cannot sign up as tenants yet in Phase 1.
"External in Phase 2" means: once it is proven on our own platforms,
outside businesses can sign up, get API keys, and pay to verify their
users. Same product, same build — the only difference is *who is allowed
to be a tenant, and when*. (Owner asked what this meant on 2026-10-26;
explanation given, he can flip it to external-from-launch with one word.)

### D3. Launch coverage — SETTLED, EXPANDED by the owner 2026-10-26
Owner corrected the original 3-country proposal: coverage is **worldwide
in scope, not three countries**. Named by the owner: **Nigeria, United
Kingdom, United States, Canada, Australia, Germany, Ghana**, plus more
African countries, more Asian countries, and countries across the world.
Filled in by us (owner can strike/add any): Africa — Ghana, Kenya, South
Africa; Asia — India, Philippines, Singapore, United Arab Emirates;
Europe — France, Netherlands, Ireland; plus the named set above.
How this works honestly: **passports are accepted from every country in
the launch list (and the MRZ format is a worldwide standard)**, while
driver's licence / national ID support starts with the named countries
and expands country by country with tests. Only tested documents get
listed as supported.

### D4. Stack — SETTLED, clarified by the owner 2026-10-26
**Built local-first. Not on Supabase and not on Cloudflare yet.**
Phase 1 runs on our own machine (local data + local storage behind the
API contract in docs/API.md). The normal production home **will be
Cloudflare** (see D6 for which account) — hosting moves there when the
owner is ready to deploy; it is not hosted on this computer as a final
state. The data layer is kept portable so that move is a deployment
step, not a rewrite.

### D5. Face match / liveness (Phase 2) — SETTLED
Plug an evaluated provider first behind our check interface; evaluate own
models in parallel against the same acceptance tests; swap only on
evidence. No provider named until the evaluation runs.

### D6. Domain & Cloudflare account — SETTLED, clarified 2026-10-26
**`kyc.novamail.store`** (subdomain only, per the owner's root-domain
rule), created when Phase 1 is ready to deploy — not before.
The domain lives on **the owner's existing Cloudflare account — the one
he already gave access to and used to log in for novamail.store** — not
a separate new account. If a different Cloudflare account is ever to be
used for KYC, the owner will provide that account's API token himself at
that time; until then, the existing account is the one.

### D7. Pricing — SETTLED (shape; prices deferred on purpose)
Per-verification by level, free sandbox, no charge for expired-untouched
or our-error sessions. Actual prices are set once Phase 1 check costs are
measured — pricing before measuring would be guessing.

## STILL OPEN

### D8. Repo visibility
Repo is public now per the owner's instruction and may go private later.
The blueprint is safe public. **With Phase 1 code now landing, the owner
should say if he wants it flipped private** — until he does, it stays
public per his original instruction; no secrets, keys, or provider
credentials ever land in the repo either way.
