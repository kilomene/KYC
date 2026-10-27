# Cloudflare hosting assessment (decision D4, WS5)

_Question: what can move to Cloudflare, what must stay on the
origin, based on MEASURED workloads — 2026-10-27._

## Measured­d origin workloads (this VM, 2 cores)

| Workload | Measured cost |
|---|---|
| Single OCR pass (tesseract, OMP_THREAD_LIMIT=1) | ~1.1s CPU |
| Full document read (fortified, parallel) | ~50s wall serial components on a real slip; ~10-20s typical after the speed programme |
| Decision pipeline (submit, real session) | 60-120s envelope; tunnel-safe via the async claim + poll design |
| Face embedding (SFace) / track of ~29 frames | seconds per session |
| Backup of a working data set | 0.089s, ~284KB (drill, benchmarks/BACKUP-RESTORE.md) |

## What CANNOT move to Workers (today, honestly)

- **Tesseract OCR, OpenCV (YuNet/SFace), the Python pipeline,
  SQLite.** Workers run JS/WASM in a 128MB, CPU-capped isolate
  with no native binaries and no filesystem. The fortified
  reader is native-code Python end to end; a WASM port of
  tesseract+OpenCV exists in research form but is a rewrite
  with unmeasured accuracy — and this platform's claim to
  quality IS the measured reader. Moving compute to Workers
  now would trade a proven pipeline for an unproven one.
- **The database** (SQLite, single-writer, encrypted media on
  disk) maps to D1 + R2 only with a data-layer rewrite; the
  fraud index, audit log and case system are relational and
  transactional.

## What CAN and SHOULD live at the edge

- **The tunnel Worker (already live)** — the public front
  door: TLS, the domain, IP/country stamping, body-size
  guards. This pattern (Worker + outbound-only origin) is
  also what makes the origin portable: any future host only
  needs outbound WSS.
- **Static flow assets** (voice clips, pages) — cacheable at
  the edge; the origin already serves them `no-store` for
  correctness during development; a versioned-asset cache
  rule is the safe future step.
- **Rate limiting / WAF** at the edge for the public flow
  endpoints — configuration, not code.

## Staged verdict

1. KEEP the compute + data on the origin (this VM class of
   host), fronted by the Worker — today's architecture, now
   with queue reaping, staging, metrics and a runbook (WS5).
2. NEXT (no rewrite): edge caching of versioned static assets
   + WAF/rate-limit rules in the Worker.
3. ONLY IF scale demands: move the origin to a container host
   (the same Python stack, more cores — OCR parallelises
   linearly with cores) and/or evaluate a D1/R2 data-layer
   port as its own measured project. A Workers-native rewrite
   of the reader is NOT recommended on current evidence.
