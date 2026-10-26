# KYC — Security

*A platform holding ID documents and faces is a high-value target.
Security here is not a phase; it is the precondition for every phase.*

*STATUS (updated WS3, 2026-10-26): this document is the threat model
and the control targets; the verified implementation status of each
control lives in docs/CLAIMS-AUDIT.md. WS3 moved these from target to
IMPLEMENTED, each proven by tests or a measured exercise: reviewer
TOTP MFA, encryption at rest for stored media (AES-256-GCM envelope),
API rate limits + request-size cap, webhook retries with
dead-letter + replay and an SSRF delivery guard, checksummed
backup + a real restore drill (benchmarks/BACKUP-RESTORE.md), a
tenant-isolation test battery, and a scripted self-pen-test
(docs/PENTEST.md — 32/32 probes). STILL OPEN, stated plainly: media
malware scanning, database-file encryption (media files are encrypted;
the SQLite file itself relies on host storage), CI
dependency/vulnerability scanning, and an independent external
penetration test.*

## 1. Threat model (top threats)

| Threat | Example | Primary controls |
|---|---|---|
| External breach of image store | Attacker dumps ID photos | Private buckets only, encryption at rest, signed URLs in minutes, no public listing, RLS-scoped minting |
| Tenant account takeover | Stolen reviewer login → mass PII viewing | MFA for dashboard, session controls, per-view audit, anomaly alerts |
| Cross-tenant exposure | Bug lets tenant A read tenant B | RLS in the database, tenant-scoped tests in CI, no-existence-oracle API errors |
| Insider misuse | Staff browsing applicants | Break-glass only, reason required, tenant-visible audit, least-privilege roles |
| Fraudster evasion | Deepfake selfie, tampered document, virtual camera | Liveness + injection signals, authenticity checks, velocity/fraud signals, review routing |
| Webhook/API abuse | Forged callbacks, key leakage | HMAC signatures + timestamp window, hashed keys shown once, instant revocation, rate limits |
| Provider compromise/outage | Check provider leaks or dies | Minimum data sent per check, provider isolation, fail-closed degradation, DPA + sub-processor review |

## 2. Baseline controls (from the first commit)

- TLS everywhere; HSTS; secure cookies; CSP on the hosted flow and
  dashboard.
- Encryption at rest: **stored media files** (documents, selfies,
  liveness, PoA, KYB documents) are AES-256-GCM encrypted with per-file
  keys wrapped by a master key held in env/file, never in the DB or
  repo (WS3, `server/storage.py`; migration CLI + tests). The SQLite
  database file itself is **not** encrypted in this build — it relies
  on host storage controls; PII columns flagged in the schema
  (DATA-MODEL 🔒) remain a target for column-level protection.
- Secrets only in the platform secret store — never in the repo, never in
  logs, never in chat. Keys and tokens are hashed at rest.
- Uploaded files treated as hostile: type sniffing, size limits
  (request-body cap → `413`, WS3), image re-encoding before downstream
  processing. **Malware scanning is NOT implemented** (open).
- Every PII read (document view, image URL mint, export) writes an audit
  event. Exports are rate-limited, reason-tagged, and tenant-admin
  visible.
- Backups: checksummed backup script (`scripts/backup.py`) with a
  manifest (table counts + per-file SHA-256) and a **restore drill
  executed and measured** (WS3, benchmarks/BACKUP-RESTORE.md) — the
  restored copy boots, serves records, and decrypts media. Backups
  contain the platform secret and encrypted media, so a backup
  directory is itself secret material; the media master key is never
  inside a backup (fingerprint only). Backup retention follows the
  same deletion rules (deletions propagate).
- API abuse controls (WS3): per-credential, per-flow-token and per-IP
  rate limits returning real `429` + `Retry-After`; webhook delivery
  retries with exponential backoff, dead-letter state and replay, and
  an SSRF guard that refuses non-public webhook targets before any
  network call.
- Dependency and container scanning in CI; critical findings block
  release. (**Not set up yet** — no CI pipeline exists; open.)
- Annual (minimum) independent penetration test before scale claims; a
  responsible-disclosure contact published from launch. (A scripted
  **self**-pen-test ran in WS3 — docs/PENTEST.md; the independent test
  is still open.)

## 3. Fraud-security specifics

- Session links: high-entropy tokens, hashed at rest, single-applicant,
  expiring, revocable; opening a link never exposes prior data.
- Device/injection signals collected proportionately and declared in the
  consent text — no covert fingerprinting beyond the verification purpose.
- Reviewer actions require recent authentication for sensitive cases
  (screening-hit disposition, override approvals).
- Reviewer MFA (WS3): TOTP (RFC 6238) second factor for named reviewer
  accounts gates privileged actions (decide, four-eyes confirm, hit
  disposition, KYB registry). Codes are single-use (replay refused).
  Recovery is an audited tenant-admin reset that fails closed. Tenant
  isolation is enforced by a dedicated cross-tenant attack test
  battery (tests/test_isolation.py).

## 4. What we will not do

- No applicant images in logs, analytics, error reports, or support
  tickets.
- No "temporary" public storage links for debugging.
- No security through obscurity as a substitute for the controls above.
- No launch with a known critical open. Fail closed applies to shipping,
  too.
