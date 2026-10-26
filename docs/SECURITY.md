# KYC — Security

*A platform holding ID documents and faces is a high-value target.
Security here is not a phase; it is the precondition for every phase.*

*STATUS (WS0 audit, 2026-10-26): this document is the threat model and
the control TARGETS. It is not a statement that every control below is
implemented today. Section 2 is headed "baseline controls", but the
audit found several of them partial or not yet built (reviewer MFA,
encryption at rest, malware scanning, backup/restore testing, CI
vulnerability scanning, independent penetration test). The verified
implementation status of each control lives in docs/CLAIMS-AUDIT.md;
closing the gaps is Phase 4 WS3.*

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
- Encryption at rest for the database and object storage; PII columns
  flagged in the schema (DATA-MODEL 🔒) get column-level protection
  where the design calls for it.
- Secrets only in the platform secret store — never in the repo, never in
  logs, never in chat. Keys and tokens are hashed at rest.
- Uploaded files treated as hostile: type sniffing, size limits, malware
  scanning, image re-encoding before any downstream processing.
- Every PII read (document view, image URL mint, export) writes an audit
  event. Exports are rate-limited, reason-tagged, and tenant-admin
  visible.
- Backups encrypted, access-logged, with tested restore; backup retention
  follows the same deletion rules (deletions propagate).
- Dependency and container scanning in CI; critical findings block
  release.
- Annual (minimum) independent penetration test before scale claims; a
  responsible-disclosure contact published from launch.

## 3. Fraud-security specifics

- Session links: high-entropy tokens, hashed at rest, single-applicant,
  expiring, revocable; opening a link never exposes prior data.
- Device/injection signals collected proportionately and declared in the
  consent text — no covert fingerprinting beyond the verification purpose.
- Reviewer actions require recent authentication for sensitive cases
  (screening-hit disposition, override approvals).

## 4. What we will not do

- No applicant images in logs, analytics, error reports, or support
  tickets.
- No "temporary" public storage links for debugging.
- No security through obscurity as a substitute for the controls above.
- No launch with a known critical open. Fail closed applies to shipping,
  too.
