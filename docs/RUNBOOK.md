# Incident Runbook — KYC production (kyc.novamail.store)

_Last updated 2026-10-27 (WS5). Production = `kyc.service` on this
VM (127.0.0.1:8790) behind the Cloudflare tunnel Worker; staging =
`kyc-staging.service` (127.0.0.1:8792, data-staging/, synthetic
data only)._

## Health checks (in order)

1. `curl -s http://127.0.0.1:8790/healthz` → `{"ok": true}`.
   If this fails, the origin is down — see "Service down".
2. `curl -s https://kyc.novamail.store/healthz` → same body via
   the tunnel. If (1) passes and (2) fails, the tunnel is down —
   see "Tunnel down".
3. Queue state (operator token required):
   `GET /v1/platform/metrics` with `X-Platform-Admin` — reports
   sessions/decisions (24h), `queue.processing_now`, live
   workers, webhook dead letters, fraud-index size.

## Service down

- `sudo systemctl restart kyc.service`; re-check (1).
- Still down: `sudo journalctl -u kyc.service -n 100` — the usual
  causes after a VM replacement are missing system pieces;
  `bash deploy/recover.sh` restores them (tesseract, pip
  packages, systemd units) and the `kyc-health` watchdog hook
  runs it automatically on its 5-minute poll.
- Sessions stuck in `processing`: the WS5 submit reaper
  re-drives claims quiet for 3+ minutes on its own (audit action
  `decision.reaped`). Nothing manual is needed; verify via the
  metrics endpoint that `processing_now` drains.

## Tunnel down

- `sudo systemctl restart kyc-tunnel-client.service`; watch
  `logs/tunnel-client.log` for the WSS reconnect.
- Worker-side failures (Cloudflare 500/1101 on the Durable
  Object) have historically cleared on their own; do not
  redeploy the Worker for a transient 1101.

## Data / disaster recovery

- Backup: `python3 scripts/backup.py` (see benchmarks/
  BACKUP-RESTORE.md for the last measured drill: full
  backup+restore of a scratch instance with encrypted media,
  decision preserved, keyless reads failing closed at 503).
- Restore into a FRESH data dir only; verify `/healthz`, one
  known applicant read, and one document decrypt before
  pointing the service at it.
- **Master key**: `data/kyc-master.key` (600). Loss of this
  file = all stored media unreadable, permanently. The sealed
  backup mechanism is tracked work — until it lands, treat any
  VM/disk migration as a key migration first.

## Webhook dead letters

- Metrics shows `webhook_dead_letters`. Deliveries retry with
  backoff automatically (the serve-time sweeper); a dead letter
  means the tenant endpoint stayed unreachable — inspect via
  the console's webhook view, fix the endpoint, then replay
  from the console.

## Fraud-signal surge

- A spike in `duplicate_document` / `duplicate_face_suspected`
  routes cases to review (never auto-rejects). Check the
  review queue first; confirm whether one IP/applicant cluster
  explains it (metrics + fraud_signals findings on the cases)
  before touching any threshold. Thresholds live in
  server/fraud.py and are deliberately conservative.
