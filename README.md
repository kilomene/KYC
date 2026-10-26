# KYC

**Know Your Customer, built our way.**

KYC is an identity verification platform: it lets a business confirm that a
person is who they claim to be — before that business gives them an account,
money, or access. Other companies have built this before (Sumsub, Persona,
Onfido, Veriff, Jumio). This is our own, original build: our code, our
design, our rules — informed by what the category does, copying none of it.

> **Status: Phase 1 local MVP built and tested (2026-10-26).**
> A real, runnable local build (details below): tenant API keys, a hosted
> applicant flow, checks that actually run (image quality, OCR, MRZ check
> digits, expiry/age, name/DOB consistency), a fail-closed decision
> engine, human review console, signed webhooks, audit log, erasure and
> retention. It runs **locally only** — not deployed, not on Supabase or
> Cloudflare yet; the production home will be Cloudflare when the owner
> is ready (DECISIONS D4/D6), behind this same API contract.
> Nothing here claims a certification, partnership, or check we have not
> actually built and tested.

## Run the Phase 1 local MVP

```bash
cd KYC
python3 -m server --port 8765          # data lives in ./data/ (gitignored)
# Landing:  http://127.0.0.1:8765/
# Console:  http://127.0.0.1:8765/console   (paste a tenant API key)
python3 -m unittest discover tests     # 38 tests
python3 scripts/e2e_local.py           # live end-to-end run
python3 -m server.retention --days 90  # delete images of old decided sessions
```

Create a tenant (local bootstrap — unauthenticated **only** in this local
build; a deployment gates this behind platform admin):

```bash
curl -s -X POST localhost:8765/v1/tenants -H 'Content-Type: application/json' \
  -d '{"name":"Nova Payments","country":"NG"}'   # returns test+live keys ONCE
```

Then `POST /v1/applicants` and `POST /v1/sessions` with
`Authorization: Bearer <key>`; the session response carries the applicant's
`/flow/<token>` link. Sessions are **resumable**: reopening an unexpired
link continues where the applicant left off — uploaded steps stay done.

Requires: Python 3.12, Pillow, and the `tesseract` CLI for OCR
(`sudo apt-get install -y tesseract-ocr`). If tesseract is missing the OCR
check reports `error` — it never pretends to pass.

### What Phase 1 does NOT do yet (honest list)

- **Face match and liveness are Phase 2.** They are recorded as required
  checks with status `not_run`, so by the fail-closed rule a Level 2/3
  session can **never auto-approve** in Phase 1 — it goes to a human
  reviewer, who compares the document image and the selfie side by side
  in the console. Nothing claims biometrics passed.
- **Level 3 extras (proof of address, sanctions/PEP screening) are
  Phase 3** — likewise `not_run`, likewise blocking auto-approval.
- **Document authenticity** beyond OCR/MRZ/consistency (template, tamper,
  recapture detection) is Phase 2. KYB is Phase 3.
- **Sandbox honesty note:** the blueprint's draft API text mentioned
  "deterministic outcomes for test documents". This build does **not**
  fake outcomes: test keys run the identical real checks; "test" means
  strict data separation from live (a test key can never read live data),
  nothing more.
- No billing, no email sending, no multi-user tenant teams, webhook
  delivery is one signed attempt, logged (no backoff/replay yet).

## The ambition

The owner's standing bar (docs/AMBITION.md): **everything we build is
built to be more advanced than Sumsub, Persona, and Onfido** — on low-end
phone completion and resumable sessions, Africa/Asia document quality,
explainable decisions, reviewer speed, layered fraud defence, reusable
verified identity, developer experience, pricing honesty, and privacy.
That superiority is a target to earn: we claim it publicly only for a
specific capability that is built, tested, and measured.

## What it does (the product in one page)

A business (the **tenant**) sends a person (the **applicant**) to KYC.
The applicant completes a short flow on their phone or computer:

1. Enter basic details (legal name, date of birth, country).
2. Photograph a government ID (passport, driver's licence, national ID).
3. Take a selfie — checked against the ID photo, with a liveness check so a
   photo of a photo does not pass.
4. Depending on the level: proof of address, and screening against
   sanctions / PEP / watchlists.

KYC runs its checks, produces a **decision** (approved, rejected, or sent to
a human reviewer), and sends the result back to the business by dashboard,
API, and webhook. The business never has to build document capture, OCR,
face matching, case review, or audit trails itself.

## Verification levels

| Level | Name | Checks |
|---|---|---|
| 1 | Basic | Name + DOB + email/phone, document number format & expiry |
| 2 | Standard | Government ID capture, OCR/MRZ extraction, document authenticity checks, selfie face-match, liveness |
| 3 | Enhanced | Everything in Standard + proof of address + sanctions / PEP / adverse-media screening + duplicate & fraud signals |
| KYB | Business | Company registration check, directors / ultimate beneficial owners identified and each verified at Level 2+ |

## The blueprint

Read in this order:

1. **[docs/BLUEPRINT.md](docs/BLUEPRINT.md)** — the full product blueprint:
   users, journeys, every check in detail, the decision engine, the review
   console, pricing shape, and what "done" means for each part.
2. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — proposed system
   architecture, stack, data flow, and provider strategy.
3. **[docs/DATA-MODEL.md](docs/DATA-MODEL.md)** — database schema draft:
   tenants, applicants, sessions, documents, checks, cases, webhooks, audit.
4. **[docs/API.md](docs/API.md)** — draft REST API and webhook contract.
5. **[docs/COMPLIANCE-AND-PRIVACY.md](docs/COMPLIANCE-AND-PRIVACY.md)** —
   the legal/privacy ground rules this product must be built inside.
6. **[docs/SECURITY.md](docs/SECURITY.md)** — threat model and controls.
7. **[docs/ROADMAP.md](docs/ROADMAP.md)** — phased build plan, MVP first.
8. **[docs/DECISIONS.md](docs/DECISIONS.md)** — the owner's decisions
   D1–D8, settled 2026-10-26 (Nova Inc product, internal first, expanded
   worldwide coverage, local-first build, Cloudflare as production home).
9. **[docs/AMBITION.md](docs/AMBITION.md)** — the standing bar: more
   advanced than Sumsub, Persona, and Onfido — claimed only where built,
   tested, and measured.

## Non-negotiable build rules

- **Real or not shipped.** Every check named in a release actually runs in
  that release. No placeholder checks, no demo decisions, no fake results.
- **Fail closed.** If a check cannot run, times out, or returns unclear,
  the outcome is *review* or *rejected* — never an automatic approval.
- **A human can always review.** Automation proposes; a trained reviewer
  in the console can overturn, with a reason, and the overturn is audited.
- **Collect the minimum.** Only the data a check needs, kept only as long
  as the retention rule says, deletable on a valid request.
- **Everything is audited.** Every view of an applicant's documents, every
  decision, every change — who, what, when — in an append-only log.
- **No borrowed trust.** We do not claim SOC 2, iBeta, ISO, or any other
  certification until we actually hold it.

## Who it is for (first)

**Settled (DECISIONS.md): KYC is a Nova Inc product, internal first.**
The first tenants are Nova Inc's own platforms (Nova Payments, Agent
Exchange) verifying their users; outside businesses — fintechs,
marketplaces, crypto and payments platforms, platforms onboarding agents
or sellers — come in Phase 2 once it is proven on our own traffic.

## Launch coverage (settled, owner-expanded 2026-10-26)

Worldwide in scope. Launch list: **Nigeria, United Kingdom, United
States, Canada, Australia, Germany, Ghana, Kenya, South Africa, India,
Philippines, Singapore, United Arab Emirates, France, Netherlands,
Ireland** (ISO codes in `SUPPORTED_DOCUMENTS` in `server/app.py`).
**Passports are accepted for every country in that list** (the MRZ is a
worldwide standard); **driver's licence / national ID** start with
Nigeria, United Kingdom, United States, Canada, Australia, Germany, and
Ghana, expanding country by country with tests.

## Licence / visibility

Public repo for now, by the owner's instruction; it may go private later.
No licence is granted by the presence of this blueprint.
