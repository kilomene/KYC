# KYC

**Know Your Customer, built our way.**

KYC is an identity verification platform: it lets a business confirm that a
person is who they claim to be — before that business gives them an account,
money, or access. Other companies have built this before (Sumsub, Persona,
Onfido, Veriff, Jumio). This is our own, original build: our code, our
design, our rules — informed by what the category does, copying none of it.

> **Status: Phases 1–3 built and tested locally (2026-10-26).**
> A real, runnable local build: tenant API keys, a hosted applicant
> flow, checks that actually run (image quality, OCR, MRZ check digits,
> expiry/age, name/DOB consistency, **face match** (YuNet + SFace),
> **active liveness (movement challenge)**, **document authenticity
> signals** (ELA / metadata / moiré-FFT / format), **proof of address**,
> **sanctions screening** with human disposition, **ongoing
> monitoring**), an explainable **risk engine**, a fail-closed decision
> engine with Level 2 auto-approval for clean low-risk sessions,
> **versioned per-tenant flow config**, **KYB** (business verification),
> **four-eyes review with reviewer roles and case SLAs**, a reviewer
> **assist** pre-read, **reusable signed verified credentials**, human
> review console, signed webhooks, audit log, erasure and retention.
> 86 automated tests + a live Level 3 end-to-end run, all green.
> It runs **locally only** — not deployed, not on Supabase or
> Cloudflare yet; the production home will be Cloudflare when the owner
> is ready (DECISIONS D4/D6), behind this same API contract.
> Nothing here claims a certification, partnership, or check we have not
> actually built and tested.

## Run it locally

```bash
cd KYC
python3 scripts/fetch_models.py        # one-time: YuNet + SFace ONNX models into models/ (gitignored)
python3 -m server --port 8765          # data lives in ./data/ (gitignored)
# Landing:  http://127.0.0.1:8765/
# Console:  http://127.0.0.1:8765/console   (paste a tenant API key)
python3 -m unittest discover tests     # 86 tests
python3 scripts/e2e_local.py           # live Level 3 end-to-end run
python3 -m server.retention --days 90  # delete images of old decided sessions
python3 scripts/fetch_ofac.py          # optional: real OFAC SDN list into data/lists/
python3 -m server.monitoring --tenant <id> --env test   # ongoing-monitoring rescreen CLI
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

Requires: Python 3.12, Pillow, numpy, OpenCV (`cv2`) and the `tesseract`
CLI for OCR (`sudo apt-get install -y tesseract-ocr`). If tesseract is
missing the OCR check reports `error` — it never pretends to pass. If
the face models are missing (run `scripts/fetch_models.py`), face match
and liveness report `error`/`model_missing` — never a fake pass.
Face models: YuNet `face_detection_yunet_2023mar.onnx` (MIT) and SFace
`face_recognition_sface_2021dec.onnx` (Apache 2.0) from the OpenCV Zoo
— the zoo ships SFace as the 2021dec file; there is no 2023dec file.

### What this build does NOT do yet (honest list)

- **No live government registry connection for KYB.** The registry leg
  is registration-number *format* validation (NG/US/GB/CA/AU/DE/GH
  patterns we define) + a company document upload + a named reviewer's
  confirmation. It is labelled exactly that way in the API and console.
- **Liveness is an active movement challenge (v1)** — server-issued
  random head movements analysed from video frames. It is **not**
  passive liveness and carries **no iBeta / ISO 30107 certification**;
  nothing here claims one.
- **Screening lists:** the repo ships a tiny, clearly-labelled SAMPLE
  fixture list (`lists/sample.csv`, fictional entries). Real coverage
  comes from dropping list CSVs into `data/lists/` —
  `scripts/fetch_ofac.py` downloads the real OFAC SDN list (verified
  working: 7,519 individual entries). PEP and adverse-media lists are
  not bundled; the engine reads whatever CSVs are present in the
  documented format. No lists at all → screening reports `error`
  (`screening_lists_missing`), never a silent pass.
- **Face/liveness accuracy is not benchmarked yet.** The SFace decision
  threshold is OpenCV's published 0.363 default (tenant-configurable);
  demographic performance testing per COMPLIANCE §3 has **not** been
  done — no accuracy claim is made. Synthetic test images cannot pass
  the real face checks, so sandbox Level 2/3 sessions land in human
  review by design (fail-closed), exactly as the E2E shows.
- **Authenticity signals are heuristics**, calibrated on synthetic
  images (ELA block spread, moiré FFT energy share). Combined evidence
  decides; one weak signal alone never fails a document. They are a
  routing/tamper-triage layer, not a forensic guarantee.
- **Sandbox honesty note:** this build does **not** fake outcomes: test
  keys run the identical real checks; "test" means strict data
  separation from live (a test key can never read live data), nothing
  more.
- No billing, no email sending; webhook delivery is one signed attempt,
  logged (no backoff/replay yet). Tenant "teams" exist as named
  reviewer tokens with roles (admin/reviewer) for console actions —
  not full user accounts with passwords.

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
