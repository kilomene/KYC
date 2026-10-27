# Backup / Restore Drill — measured results (Phase 4 WS3)

Run: 2026-10-27 22:04 UTC by `scripts/restore_drill.py` against a scratch
instance (media encryption ON). Nothing touched the production data dir.

## Measured

- Backup size: **284298 bytes** (DB 241664 bytes, 2 media files, 41012 media bytes)
- Backup wall time: **0.089s** · Restore wall time: **0.003s**
- Session decision before backup: `approved`

## Record counts (source DB = backup manifest = restored DB)

| Table | Records |
|---|---:|
| api_keys | 2 |
| applicants | 1 |
| audit_log | 8 |
| biometric_captures | 1 |
| business_documents | 0 |
| business_people | 0 |
| businesses | 0 |
| cases | 0 |
| checks | 17 |
| consents | 1 |
| credentials | 1 |
| decisions | 1 |
| deletions | 0 |
| documents | 1 |
| flow_configs | 0 |
| ip_intel_cache | 0 |
| monitoring_alerts | 0 |
| screening_hits | 0 |
| sessions | 1 |
| tenant_users | 0 |
| tenants | 1 |
| webhook_deliveries | 0 |
| webhook_endpoints | 0 |

## Smoke checks on the restored copy

- [PASS] stored document is ciphertext at rest — first bytes b'KYCENC01'
- [PASS] backup manifest table counts match source DB
- [PASS] restore checksums + counts verified
- [PASS] restored server healthz
- [PASS] known applicant readable after restore — status 200
- [PASS] session status identical after restore — approved vs approved
- [PASS] document decrypts after restore (bytes identical) — status 200, 37142 bytes vs 37142 uploaded
- [PASS] encrypted image read without master key fails closed (503) — status 503

## Honest limits

- The drill restores to the same host/filesystem; it proves the backup is complete,
  checksummed and bootable — it is not a cross-site disaster-recovery exercise.
- The master key is NOT in the backup (by design): a restore without the key serves
  metadata but encrypted media reads fail closed (proven above). Key custody is an
  operator responsibility, recorded in the manifest only as a SHA-256 fingerprint.
- platform_secret.key IS in the backup (restored credentials must stay verifiable);
  treat backup directories as secret material.
