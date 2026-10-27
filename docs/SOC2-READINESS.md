# SOC 2 Readiness Path (Phase 4 WS8)

_Status 2026-10-27: READINESS, not certification. No SOC 2 report
exists and none is claimed. This document maps the Trust Services
Criteria to what the platform ALREADY does (with evidence in the
repo), what is missing, and the sequence to a Type I / Type II._

## Controls that exist today (evidence-linked)

| Area | In place | Evidence |
|---|---|---|
| Access control | Tenant API keys (hashed, revocable), reviewer roles, reviewer TOTP MFA with replay protection, operator-token gates that fail closed | server/app.py, server/mfa.py; WS3 isolation battery 9/9, self-pentest 32/32 (docs/PENTEST.md) |
| Encryption | Media AES-256-GCM at rest with a 600-permission master key; keyless reads fail closed (proven in the DR drill) | server/storage.py; benchmarks/BACKUP-RESTORE.md |
| Audit | Append-only audit log across tenant/reviewer/platform/system actors; fraud + billing actions audited | server/db.py audit(); WS4/WS6 entries |
| Change management | Build-test discipline, full test suite as the gate (360+ tests), staging environment with synthetic data only, decisions documented | docs/DECISIONS.md; deploy/systemd/kyc-staging.service |
| Availability / DR | Async decision queue with claim recovery + reaper; backup/restore drill executed with measured results; incident runbook | docs/RUNBOOK.md; benchmarks/BACKUP-RESTORE.md |
| Privacy / retention | Erasure endpoint, retention sweeper, consent records, HMAC-hashed fraud index (no raw document numbers or face embeddings stored), claims-only reusable credentials | server/retention.py, server/fraud.py, server/credentials.py |
| Monitoring | Operator metrics endpoint, screening alerts, webhook DLQ visibility | server/monitoring.py; GET /v1/platform/metrics |
| Biometric evidence | Measured face-match operating point (LFW protocol); PAD logic harness with stated limits | benchmarks/ (WS2 report); benchmarks/PAD-EVAL.md |

## Gaps before an audit can start

1. **Formal policies** — written information-security, access,
   change, incident-response and vendor policies, owner-approved
   and versioned. (The runbook is the seed of the IR policy.)
2. **People controls** — background checks and security training
   records for anyone with production access; an access-review
   cadence with evidence.
3. **Independent penetration test** — the in-repo battery is a
   SELF-test and is labelled as such; SOC 2 needs a third-party
   report.
4. **PAD laboratory evaluation** — iBeta/ISO 30107-3 by an
   accredited lab with physical artefacts; the harness in
   scripts/pad_eval.py is the readiness step only.
5. **Vendor inventory** — Cloudflare (edge/tunnel), hosting,
   any future registry partners (WS4), each with their own SOC 2
   / ISO status recorded.
6. **Master-key custody** — the sealed-backup mechanism
   (tracked work) must land; today there is no second copy,
   which is itself a finding to remediate before Type II.
7. **Observation window** — Type II requires controls operating
   over months with evidence; the audit log + metrics history
   are the evidence base, so they must be retained accordingly.

## Sequence

1. Land the key-custody fix and the formal policy set (owner
   approves). 2. Commission the independent pen test + PAD lab
   scoping. 3. Engage a CPA firm for a SOC 2 Type I (point-in-
   time) once 1–2 are underway. 4. Run the observation window
   with the platform's own evidence collection, then Type II.

**Claims discipline:** until a report exists, public copy may
say "built to SOC 2 control patterns; readiness assessed
internally" — never "SOC 2 certified" or "compliant".
