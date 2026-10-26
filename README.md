# KYC

**Know Your Customer, built our way.**

KYC is an identity verification platform: it lets a business confirm that a
person is who they claim to be — before that business gives them an account,
money, or access. Other companies have built this before (Sumsub, Persona,
Onfido, Veriff, Jumio). This is our own, original build: our code, our
design, our rules — informed by what the category does, copying none of it.

> **Status: Blueprint phase (2026-10-26).**
> This repo currently contains the full product blueprint, not code.
> Nothing in here is a working verification product yet, and nothing here
> claims a certification, partnership, or check we have not actually built
> and tested. The build starts at Phase 1 of the roadmap, on the owner's word.

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
8. **[docs/DECISIONS.md](docs/DECISIONS.md)** — open decisions only the
   owner can make, each with a recommendation. The build does not guess
   these.

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

Fintechs, marketplaces, crypto and payments platforms, and platforms that
onboard agents or sellers — businesses that must verify people before
money or accounts move. Internal Nova Inc platforms are a natural first
user **if** the owner decides KYC sits under Nova Inc (see DECISIONS.md);
the design works either way, for one tenant or many.

## Licence / visibility

Public repo for now, by the owner's instruction; it may go private later.
No licence is granted by the presence of this blueprint.
