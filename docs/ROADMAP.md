# KYC — Roadmap

*Each phase ships only when its acceptance criteria pass on real devices
and real test data. A phase is not "done" because its code exists.*

*CURRENT STATUS (WS0 audit, 2026-10-26): Phases 1–3 and the live-scanner
rebuild are LIVE at https://kyc.novamail.store (origin service reached
through a Cloudflare tunnel). The phase sections below are the build
record written as each phase shipped — phrases like "built locally" and
"not deployed" describe the moment of shipping, not today. Phase 4 is
approved and governed by docs/PHASE4-PLAN.md (WS0–WS8), which supersedes
the short Phase 4 sketch at the bottom of this file.*

## Phase 0 — Blueprint ✅ DONE

- [x] Repo created (public, owner's instruction): kilomene/KYC
- [x] Full blueprint, architecture, data model, API draft, compliance,
      security, roadmap, open decisions — in this repo
- [x] Owner decisions in DECISIONS.md answered (2026-10-26, incl. the
      expanded worldwide coverage correction the same day)
- **Exit:** ✅ owner approved the blueprint and Phase 1 ("Approve it —
  go with the recommendations and start Phase 1", 2026-10-26).

## Phase 1 — MVP: hosted flow + manual review ✅ BUILT LOCALLY (2026-10-26)

The smallest *real* product: a tenant can verify a real person end-to-end,
with humans making the final call while automation assists.
Built local-first (Python stdlib + Pillow + tesseract, SQLite, local
private storage) behind the docs/API.md contract. Not deployed anywhere.

- [x] Tenant creation, API keys (test/live, hashes only, shown once,
      revocable), webhook endpoints with HMAC-signed deliveries, logged.
- [x] Hosted applicant flow: consent, details, document capture, selfie
      capture, status — **resumable sessions** (reopening the link keeps
      uploaded steps). Document coverage per DECISIONS D3 as expanded:
      passports for all 16 launch countries; licence/national ID for
      NG/GB/US/CA/AU/DE/GH (`SUPPORTED_DOCUMENTS` map in server/app.py).
- [x] Capture-quality, OCR + MRZ (check digits), expiry/age and
      cross-field consistency checks — all real, all tested. Plus
      proportionate risk signals at submit (IP country vs document
      country, user-agent/device class, tenant velocity) stored as a
      structured `fraud_signals` check — signals route to review when
      elevated, never auto-reject.
- [x] Review console v1: queue, side-by-side document + selfie case view
      (audited image endpoint), approve / reject / request-more,
      **reason mandatory**, full append-only audit log.
- [x] Decision states + fail-closed engine + signed webhooks; test/live
      env separation (sandbox = data separation with the *same real
      checks* — no faked deterministic outcomes).
- [x] Retention helper (CLI) and applicant erasure — both run and tested,
      deletion verified in the filesystem, not just the UI.
- [x] Tests: `python3 -m unittest discover tests` (38 tests, green) and
      `scripts/e2e_local.py` live end-to-end run (green).
- **Acceptance — met:** two tenants fully isolated (tested); an unrun /
  error / unclear required check can never produce an approval (tested);
  deletion actually deletes (tested). **Not yet done:** end-to-end run on
  a physical low-end Android phone over a slow connection (needs the
  owner's phone test after a deploy exists).
- **Deliberately NOT in Phase 1:** face match / liveness (Phase 2 —
  recorded `not_run`, which blocks Level 2/3 auto-approval and sends the
  case to the human side-by-side comparison), document authenticity
  beyond OCR/MRZ/consistency (Phase 2), PoA + screening (Phase 3), KYB
  (Phase 3), billing, webhook backoff/replay.

## Phase 2 — Automation: face match, liveness, authenticity ✅ BUILT LOCALLY (2026-10-26)

- [x] Face match behind the check interface: YuNet detection + SFace
      embeddings, cosine decision vs OpenCV's published 0.363 threshold
      (configurable per tenant, with a near-threshold `unclear` band);
      missing models → `error`/`model_missing`, never a fake pass.
      Models fetched by `scripts/fetch_models.py` (YuNet 2023mar;
      SFace — the zoo ships `2021dec`, there is no `2023dec` file).
- [x] Liveness v1 — **active liveness (movement challenge)**:
      server-issued random movement sequence, applicant records/uploads
      a short video, server analyses YuNet frame features (face
      presence ≥80%, challenged displacement, static-replay rejection).
      Frame-feature analysis is a pure, unit-tested function.
- [x] Document authenticity: one check combining block-wise ELA,
      editor/screenshot metadata, moiré FFT energy-share and
      template/format consistency; combined evidence decides, one weak
      signal alone never fails. Thresholds calibrated on measured
      synthetic images (recorded in `server/authenticity.py`).
- [x] Explainable risk engine (`server/risk.py`): named point
      contributions per check/fraud signal, 0–100 score + band, stored
      with every decision; bands feed routing only.
- [x] Auto-decision upgrade: Level 2 with all required checks passing
      AND risk at/below the tenant ceiling auto-approves
      (`decided_by=engine`); hard fails still auto-reject; the
      fail-closed invariant is unchanged (tested).
- [x] Versioned no-code flow config foundations: per-tenant per-level
      required checks, face thresholds, risk ceiling, PoA window,
      screening threshold, SLA hours, four-eyes toggle —
      `GET/PUT /v1/config`; decisions record `config_version`
      (config-change-affects-decision is tested).
- [x] Injection/virtual-camera signals (editor metadata on "captures",
      missing camera EXIF on JPEG selfies) feed `fraud_signals` and
      risk — they route, never silently reject.
- [ ] Demographic performance testing per COMPLIANCE §3 — **not done**;
      no accuracy claim is made yet.
- [ ] Fraud/velocity v2 (duplicate document/face/device per tenant):
      v1 velocity + IP/UA signals exist from Phase 1; duplicate-face /
      duplicate-document detection is **not** built.
- **Acceptance — partially met:** fail-closed degradation is tested
  (missing model/tesseract paths return `error`, decisions never
  auto-approve on them). **Not yet:** published FAR/FRR benchmarks and
  reviewer overturn-rate measurement (need real traffic / a labelled
  evaluation set).

## Phase 3 — Enhanced + KYB ✅ BUILT LOCALLY (2026-10-26)

- [x] Proof of address (Level 3): OCR + date-within-window (default
      90 days, tenant-configurable) + name/address token matching;
      no date found → `unclear`, stale date → fail (all tested).
- [x] Screening engine (`server/screening.py`): CSV lists
      (`data/lists/*.csv` + repo `lists/`), normalised-token +
      difflib similarity + DOB proximity; hits are `pending` rows that
      block auto-approval; reviewer disposition endpoint (confirmed →
      rejected with `sanctions_hit_confirmed`; a name match alone
      never auto-rejects). Ships with a clearly-labelled SAMPLE
      fixture list; `scripts/fetch_ofac.py` downloads the real OFAC
      SDN list (verified: 7,519 entries). PEP/adverse-media lists are
      drop-in CSVs, not bundled.
- [x] Ongoing monitoring: `POST /v1/monitoring/rescreen` + CLI
      (`python3 -m server.monitoring`) re-screens approved applicants
      against current lists; new hits create alert rows, a
      `screening.hit_new` webhook and a reopened case (tested,
      including no-duplicate-alerts on re-run).
- [x] KYB: businesses API, people (directors/UBOs with ownership %)
      each a normal applicant who must reach Level 2+ approved;
      registry leg = registration-number **format** validation
      (NG/US/GB/CA/AU/DE/GH) + company document upload + reviewer
      confirmation — **no live government registry connection** in
      this build, labelled as such. Business is `verified` only when
      registry is confirmed AND all people are approved (tested).
- [x] Four-eyes + roles + SLA: named reviewer tokens via
      `POST /v1/users` (roles admin/reviewer); overriding an engine
      rejection, or approving after a false-positive disposition,
      requires a second distinct reviewer (`awaiting_second` →
      `POST /v1/cases/{id}/confirm`; same-reviewer confirm is refused
      — tested). Cases carry `sla_due_at` (default +24h, config) and
      the queue sorts by SLA. All audited.
- [x] Reviewer assist: deterministic `assist` block on the case view
      (mismatches, risk summary, suggested disposition with evidence),
      labelled "Assist — a human decides" (logic unit-tested).
- [x] Reusable verified credential: HMAC-SHA256-signed claims issued
      on approval; verify (any tenant, claims only), revoke (issuing
      tenant / the applicant), and credential-based sessions that
      inherit shared checks with `provider='verified_credential'` —
      biometrics/liveness are never inherited; tampered, revoked,
      expired and under-level credentials are all refused (tested).

## Phase 4 — Scale & polish → SUPERSEDED by docs/PHASE4-PLAN.md

- The approved Phase 4 plan (WS0 claims audit → WS8 independent
  assurance) lives in docs/PHASE4-PLAN.md and governs execution. The
  original sketch — more document types with tests, an embeddable SDK,
  billing automation (blocked on D7 prices), independent security audit
  and pen test, certification only when earned — is folded into it.

## Standing rule for every phase

Build and test locally first, watch it work, push once when green.
Real features only — if a check is listed, it runs.
