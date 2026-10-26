# KYC

**Know Your Customer, built our way.**

KYC is an identity verification platform: it lets a business confirm that a
person is who they claim to be — before that business gives them an account,
money, or access. Other companies have built this before (Sumsub, Persona,
Onfido, Veriff, Jumio). This is our own, original build: our code, our
design, our rules — informed by what the category does, copying none of it.

> **Status: LIVE (2026-10-26) at https://kyc.novamail.store — Phases
> 1–3 plus the scanner rebuild (automatic decisions, detection-gated
> capture, voice guidance, phone-only flow, IP/VPN gate, fortified
> vision, face tracking, classification, evidence packs). Phase 4 is
> approved and in progress (docs/PHASE4-PLAN.md); WS0 claims audit:
> docs/CLAIMS-AUDIT.md.**
> A real, runnable build: tenant API keys, a hosted applicant
> flow, checks that actually run (image quality, OCR, MRZ check digits,
> expiry/age, name/DOB consistency, **face match** (YuNet + SFace),
> **active liveness (movement challenge)**, **document authenticity
> signals** (ELA / metadata / moiré-FFT / format), **proof of address**,
> **sanctions screening** with human disposition, **ongoing
> monitoring**), an explainable **risk engine**, a fail-closed decision
> engine with automatic approval/rejection in the standard path,
> **versioned per-tenant flow config**, **KYB** (business verification),
> **four-eyes review with reviewer roles and case SLAs**, a reviewer
> **assist** pre-read, **reusable signed verified credentials**, human
> review console, signed webhooks, audit log, erasure and retention.
> 273 automated tests + a live Level 3 end-to-end run, all green.
> The application currently runs on the Nova origin service and is
> reached publicly through a Cloudflare tunnel; it is not on Supabase.
> Final Cloudflare-native hosting is Phase 4 WS5 (DECISIONS D4/D6),
> behind this same API contract.
> Nothing here claims a certification, partnership, or check we have not
> actually built and tested.

## Run it locally

```bash
cd KYC
python3 scripts/fetch_models.py        # one-time: YuNet + SFace ONNX models into models/ (gitignored)
python3 -m server --port 8765          # data lives in ./data/ (gitignored)
# Landing:  http://127.0.0.1:8765/
# Console:  http://127.0.0.1:8765/console   (paste a tenant API key)
python3 -m unittest discover tests     # 273 tests
python3 scripts/e2e_local.py           # live Level 3 end-to-end run
python3 -m server.retention --days 90  # delete images of old decided sessions
python3 scripts/fetch_ofac.py          # optional: real OFAC SDN list into data/lists/
python3 -m server.monitoring --tenant <id> --env test   # ongoing-monitoring rescreen CLI
```

Create a tenant (platform-operator only: tenant creation requires the
`KYC_PLATFORM_ADMIN_TOKEN` environment variable on the server and the
matching `X-Platform-Admin` header; with no token configured, tenant
creation is disabled entirely — WS0 audit fix, 2026-10-26):

```bash
curl -s -X POST localhost:8765/v1/tenants -H 'Content-Type: application/json' \
  -H 'X-Platform-Admin: <operator token>' \
  -d '{"name":"Nova Payments","country":"NG"}'   # returns test+live keys ONCE
```

Then `POST /v1/applicants` and `POST /v1/sessions` with
`Authorization: Bearer <key>`; the session response carries the applicant's
`/flow/<token>` link. Sessions are **resumable**: reopening an unexpired
link continues where the applicant left off — completed steps stay done.

Requires: Python 3.12, Pillow, numpy, OpenCV (`cv2`) and the `tesseract`
CLI for OCR (`sudo apt-get install -y tesseract-ocr`). If tesseract is
missing the OCR check reports `error` — it never pretends to pass. If
the face models are missing (run `scripts/fetch_models.py`), face match
and liveness report `error`/`model_missing` — never a fake pass.
Face models: YuNet `face_detection_yunet_2023mar.onnx` (MIT) and SFace
`face_recognition_sface_2021dec.onnx` (Apache 2.0) from the OpenCV Zoo
— the zoo ships SFace as the 2021dec file; there is no 2023dec file.

### The hosted flow is a live camera scanner (2026-10-26)

The applicant flow (`public/flow.html`) is **camera-only**. There is
**no gallery picker and no file-upload path anywhere in the flow** —
not for the document, not for the selfie, not for the liveness video,
not for proof of address. If the browser has no camera or permission
is denied, the flow shows a plain "a camera is required for live
verification" state; it never falls back to file upload.

- **Documents** are scanned in a live viewfinder with an animated
  corner frame (card or passport-page aspect). Lightweight analysis of
  downscaled frames (~8×/second, built for low-end phones) gives one
  plain-language hint at a time — too dark, glare, blurry, hold
  steady, fit the document in the frame. When the frame has been
  sharp, lit and still for ~700 ms the scanner **captures by itself —
  there is no shutter button**. A two-sided document automatically
  prompts "Now scan the BACK of your ID" and repeats; retakes are
  offered after a capture. Captures carry metadata
  (`{method: "live_camera", side}`) recorded server-side per side.
- **Selfie + liveness** are likewise automatic: face in the oval →
  the selfie captures by itself; the server-issued movement challenge
  is then recorded from the same live stream automatically (no
  start/stop buttons, no video-file upload).
- **The scanner must SEE the document before it may capture**
  (2026-10-26). A lightweight detector on the analysis frames
  (grayscale → Sobel edges → a document quadrilateral locked onto the
  guide frame: all four border edges present along most of their
  length, aspect matching the selected document type from the registry
  within 10%, real interior texture) gates auto-capture: detection
  true + quality judges (light/glare/sharpness/stillness) sustained
  for the stability window, nothing else. A still, textured room sits
  in the "No ID detected — place your ID inside the frame" state
  forever; capture with no document is *impossible*, not discouraged.
  The detected quad is drawn live on the overlay. The same gate covers
  the back side and proof of address. Camera is requested at up to
  1920×1080 (graceful fallback). A refresh-banding watch runs during
  the document step: sustained periodic luminance banding (a display's
  refresh beating against the rolling shutter) puts the scanner in
  "This looks like a screen — scan the physical document" and refuses
  the lock the same way.
- **Server-side `document_framing` check** (OpenCV contour detection)
  verifies each captured side actually contains a card-like
  quadrilateral roughly filling the frame. It is a **required,
  decision-bearing** check for document sessions: framing *fail*
  (`document_not_detected`) auto-rejects; framing *unclear* (document
  too small in frame) auto-rejects with `document_quality_rescan`.
- **Paper documents are first-class (rectification, 2026-10-26).**
  The first live owner test failed exactly here: his physical
  Nigerian NIN slip — a wide, bowed, laminated *paper* printout,
  ~2.18:1 in frame — was told "No ID detected", because the registry
  carried the slip at a card-style point aspect (1.41 ±10%), the
  client detector searched for rigid straight edges, and server
  framing found no quad in the frame (largest contour 1.4% of the
  image). The model is now honest per physical class, end to end:
  *Registry geometry* — plastic cards keep a point aspect; paper and
  booklet types carry an aspect **range** (NIN slip 1.2–2.8, guide
  frame drawn at 2.0; ZA green ID book is a booklet range).
  *Client detector* — paper types take a dedicated path: luminance
  segmentation of the bright sheet, quadratic (bowed) border fits,
  border support judged against the fitted outline at paper
  thresholds (side ≥ 0.30, mean ≥ 0.45), aspect tested against the
  registry range, and the measured aspect corrected for the analysis
  canvas's vertical squash on tall video buffers. The card path and
  its strict numbers are unchanged; the screen-refresh refusal keeps
  precedence over both paths; proof-of-address pages (portrait paper)
  take the paper path too. *Server framing* — multi-strategy quad
  detection (two Canny tunings + luminance segmentation) with
  interior-texture, border-support and ring-contrast gates so bright
  windows/walls cannot hallucinate a document (the owner's original
  room photos still fail); segmentation quads must meet the pass
  size bars to count at all. *Warped reading* — when a quad is found,
  the capture is perspective-warped flat and OCR, classification and
  field extraction read the warp (authenticity keeps the original);
  a quad too small to be the document (an inner photo box) never
  earns a warp. *Measured on the owner's own frames* (artefacts in
  `data/owner-frame-proof/`, script `scripts/owner_frame_proof.py`):
  the clearer frame now passes server framing (quad found, aspect
  2.204, wide-fill rule, warp applied), locks the client detector
  (`doc_hold`; the old card path still says `doc_none` on it),
  classifies 100/100 as NG NIN slip on the warp, and extracts surname
  and given names; the darker frame locks the client detector but
  still fails server framing (`document_not_detected`) — a capture
  taken in that light would be asked to rescan. **Honest limit:**
  the slip's printed NIN digits sit under the green NIMC watermark in
  grey print; on the owner's frame tesseract could not segment them
  in any of 20+ configurations tried (multi-pass, zone crops to 4×,
  thresholding, digit whitelist, green-channel separation), so the
  number field does not extract from that capture — names do, and
  the extraction machinery itself is proven on a layout-faithful
  synthetic slip (classification pass 85.6, all printed fields
  extracted, number format-valid).
- **Honest limits:** the client-side guidance (brightness / glare /
  blur / stillness / a skin-tone centre heuristic for the selfie) is
  *guidance heuristics*, not verification — the real checks run
  server-side (framing, vision OCR/MRZ, face track + match, liveness,
  deepfake, authenticity). OS-level camera-feed injection (virtual
  cameras, rooted devices, emulators) is mitigated in layers (see the
  deepfake section) but is **not** claimed to be eliminated.

### Automatic decisions — no manual review in the standard path (2026-10-26)

Verification is **automatic**. A genuine session approves by itself;
an invalid one rejects by itself; nothing in the standard
document + selfie path waits for a human. The decision engine
(`server/engine.py`) is decisive, in this order: hard-fail reasons
(expired document, underage, VPN/proxy detected) → any *required*
check failed → framing unclear (auto-reject, `document_quality_rescan`)
→ a required check *errored* (the platform failed, not the applicant —
the one route to a human besides the three below) → any other required
check not passed (unclear / not run / missing: the verification is
incomplete, the applicant re-does it) → tenant-config risk routing.
`needs_review` survives **only** for: a tenant flow-config that
explicitly requires review (risk ceiling / elevated signals), L3
screening possible-hits awaiting disposition, KYB, and platform
errors. The review console remains for audit, overrides (four-eyes),
and those dispositions.

### Verification layers — surface, text, internal (2026-10-26)

Every document decision records `verification_layers` — the decision
must show *how deep* the verification went:

- **SURFACE** — framing + capture quality + template classification.
- **TEXT** — vision OCR of the printed fields.
- **INTERNAL** — the document's encoded/hidden evidence: MRZ check
  digits, MRZ↔VIZ agreement, decoded QR/PDF417 payload agreement,
  authenticity signals.

Where a document type **carries** internal data (registry `mrz: true`,
or a machine-readable code was actually decoded from the image), the
internal layer is **required** for an automatic approval: unreadable
internal data auto-rejects (`internal_data_unreadable`), disagreeing
internal data auto-rejects (`internal_mismatch`). A document type with
no internal data records `internal: not_available` — honestly — rather
than pretending the layer ran. The layers are shown in the console
case view. **NFC chip reading is the remaining internal layer and is
Phase 4**: Web NFC is Android-Chrome only, and iOS Safari cannot read
passport chips from a web flow at all.

### Document classification (2026-10-26)

A captured image must classify **as the document type the session
claims**, by layout — not merely be a rectangle (`server/templates.py`,
check `document_classification`). Per-type layout templates carry the
expected aspect, portrait zone, printed labels, document-number zone
and MRZ zone. Full templates: NG passport, NG drivers licence, NG
voter card, NG NIN card, NG NIN slip, US passport, US passport card,
US drivers license, US state ID — plus a generic TD3 template for
other countries' passports and coarse templates (aspect +
portrait-left + MRZ-absent) for the remaining registry types. The
measurement locates the portrait with the YuNet face detector on the
document image, maps OCR word boxes (tesseract TSV) against the
number zone and expected labels, and checks MRZ position/validity.
Score threshold 70/100: full/generic types must **pass** for
auto-approval — a mismatch fails with
`document_classification_mismatch` and auto-rejects. Coarse types:
failure is strong risk + no auto-approval, and a type with no template
records `classification_template_missing` honestly. Calibration on
the suite fixtures: the drawn passport scores ~88 claimed as a
passport and ~58 claimed as a US driver's licence; a room photo
scores ~35 as a passport.

### Data-consistency matrix + document evidence (2026-10-26)

Verification is four-way agreement, recorded explicitly. The
`data_consistency` check builds a **pairwise agreement matrix**
across every data source present — printed fields as extracted by
OCR, the MRZ, the decoded QR/PDF417 payload, and the applicant
profile — over name, date of birth, document number and expiry. Each
pair verdict is `agree | disagree | not_available`, stored on the
case. **Any disagree is a named finding** (e.g.
`mrz_vs_barcode_number_disagree`, +25 risk via `data_inconsistency`)
and fails the check: no disagreement may exist among available pairs
for an automatic approval. Alongside it, every document decision
records a `document_evidence` block — layout classification, text
extraction, machine-readable data, portrait analysis, image quality,
security features, each with its status — the document-side mirror of
the biometric evidence block, so a decision shows the combined
independent evidence it rests on.

### Vision OCR (2026-10-26)

`server/vision.py`: **multi-pass reading + MRZ/VIZ cross-validation +
code decoding**.

- *Multi-pass reading*: tesseract runs a plain pass (greyscale + 2×
  upscale, `--psm 3`) and an adaptive-threshold pass, each with word
  confidences; a dedicated **MRZ-band pass** (focused strips, psm 6)
  recovers the MRZ lines that full-page segmentation skips (measured).
  The best read wins — a check-digit-valid MRZ outranks raw confidence.
- *MRZ↔VIZ cross-validation*: where an MRZ parses valid, label-anchored
  visual-zone DOB/expiry dates, the surname and the document number
  are compared against it. A material disagreement fails with
  `mrz_viz_mismatch` (+35 risk) — a forged document must fool **both**
  zones consistently. Fields the visual zone doesn't label are
  recorded as not compared, never guessed.
- *Code decoding*: QR codes via OpenCV (`QRCodeDetector`); PDF417 and
  other barcodes via **zxing-cpp** when installed (optional dependency —
  its absence degrades to "unavailable", recorded). US/CA licence-back
  PDF417 payloads are parsed for AAMVA elements (number, names, DOB,
  expiry) and cross-checked against the printed fields: disagreement
  fails with `code_decode_mismatch`. Decoded content is evidence,
  never truth — it must agree, or it counts against the document.

### Field templates + payload semantics (Phase 4 WS1, 2026-10-26)

- *Field-extraction templates* (`server/fieldtemplates.py`): every
  document type in the registry has a template — per-field relative
  zones (surname, given names, DOB, expiry, document number), label
  anchors including the local-language labels on DE/FR/NL documents,
  and a per-type number format validator. Extraction is zone-first
  with label anchoring, falls back to label-anchored text extraction,
  and records each field's source and format verdict on the case
  (`field_extraction` check). A document number that is read but fails
  its own type's format — including real check digits: **Verhoeff**
  for Aadhaar, the published checksum letter for Singapore NRIC —
  fails with `field_number_format_invalid`. Digit-format numbers get
  OCR-confusable normalisation (O/0, I/1, S/5…) that is only accepted
  when the normalised value passes its check digit/format.
- *Payload semantics* (`server/payloads.py`): AAMVA payloads are
  parsed in full (all elements present, with element format
  validation — MMDDYYYY dates, sex code set, height format,
  jurisdiction) and cross-checked. The NG NIN-slip QR and the PhilID
  QR are **structurally** validated (NIN = 11 digits; PCN = 16,
  PSN = 12) with cross-checks where the payload carries the fields —
  their issuers publish no payload grammar in our research corpus, and
  the findings say so. The Aadhaar secure QR is decompressed
  (zlib → XML demographic record) and cross-checked by name, DOB and
  UID last-4 — **UIDAI signature verification is NOT performed** (no
  UIDAI certificate is held), and the findings state that.
- *Classification*: every registry type now carries a FULL layout
  template in `server/templates.py` (non-NG/US passports use the
  generic TD3 template); the coarse fallback remains for any future
  type added without one, and findings always state the level.
- *Labelled accuracy benchmark* (`scripts/benchmark_vision.py`,
  results in `benchmarks/RESULTS.md`): a synthetic corpus drawn to
  the templates with known ground truth, degraded at named levels
  (blur, downscale, brightness, rotation), run through the real
  pipeline. The corpus is synthetic and template-conformant, so the
  numbers bound the extraction wiring, not real-world accuracy —
  that limit is printed in RESULTS.md and travels with the numbers.

### Biometric measurement + attack resistance (Phase 4 WS2, 2026-10-26)

Full write-up with sources and honest limits: `benchmarks/BIOMETRICS.md`
(raw data: `benchmarks/biometrics.json`, `benchmarks/attacks.json`).

- *FAR/FRR, measured on real faces*: the full LFW View-2 protocol
  (all 6,000 official pairs, deep-funneled release) through the
  production pipeline — **EER 1.07%; at the production threshold
  0.363: FAR 0.10%, FRR 2.00%, accuracy 98.95%; standard protocol
  accuracy 99.13% ± 0.38%; detection failures 0 on this corpus**
  (pre-cropped faces — not a real-world detection claim). Threshold
  analysis from the measured curve **keeps 0.363** (it delivers the
  target FAR; the data-derived auto-approve point is 0.351) and
  records a high-assurance option (0.413 → FAR 0/3,000, FRR 3.33%)
  for tenant configuration. Simulated condition slices (dark /
  downscale / blur, labelled simulations) tax FRR up to ~2× and open
  no FAR hole. **Demographic slicing is UNMEASURED** — LFW carries no
  demographic attributes and no lawfully downloadable
  attribute-labelled set was reachable; no fairness claim is made.
- *Presentation attacks, measured*: replay (REAL artefacts — the
  owner's genuine videos vs fresh challenges: liveness passed 0/6),
  print / screen / mask / deepfake families (SIMULATED, methods and
  labels in BIOMETRICS.md; physical masks and DNN face-swap corpora
  are **UNMEASURED** — they cannot be produced in this environment).
  No attack artefact achieved auto-approval (blocked-or-rejected
  100% per family); strict auto-rejection is carried by challenge
  freshness, the movement liveness, and face-track identity
  continuity — **not** by the deepfake pulse leg, which fired on
  some jittered photo presentations and is therefore evidence-only.
- *rPPG hardening*: the pulse leg now runs POS + CHROM + green under
  a signal-quality gate; re-measured on the owner's real captures it
  produces a plausible POS peak (1.34 Hz, clean take) but still
  below the evidentiary bar on 4.5 s clips — **evidence-only
  stands**. The flow's liveness window is now ~9 s at a raised
  bitrate so new captures can be measured properly.
- *Detection-at-resolution fix*: YuNet boxes shrink/drift with
  input size and break SFace alignment on multi-megapixel stills
  (measured scale sweep in BIOMETRICS.md). Detection/embedding now
  run in a ≤1024 px work space (`server/face.py`), which restored
  correct matching on the owner's full-resolution captures. A
  document portrait in a far/angled full-card photo can still go
  undetected — that returns *unclear* (fail closed), never a guess.
- *Provider adapter* (`server/bioprovider.py`): the own SFace
  pipeline is provider #1 through a real adapter interface (the
  benchmark runs through it). External provider slots fail closed
  (`provider_not_configured`) — a head-to-head still needs vendor
  accounts/keys; the evaluation is open, not faked.

### Security hardening, verified (Phase 4 WS3, 2026-10-26)

- *Tenant isolation, tested as attacks* (`tests/test_isolation.py`):
  tenant A keys, reviewer tokens and flow tokens are driven against
  tenant B's applicants, sessions, documents, images, cases,
  credentials, businesses, webhook endpoints and deliveries — every
  attempt refused, cross-tenant ids return the same `404` shape as a
  random UUID (no existence oracle), and test/live environments stay
  separated under the same tenant.
- *Reviewer MFA*: TOTP (RFC 6238, stdlib implementation) enrolment for
  named reviewers; privileged actions (decide, four-eyes confirm, hit
  disposition, KYB registry) require a current code in
  `X-Reviewer-TOTP`; replayed codes are refused. Recovery is an
  audited tenant-admin reset — there is no bypass, it fails closed.
- *Rate limits + body cap*: per-credential (1,200/min), per-flow-token
  (240/min) and per-IP (6,000/min) sliding windows, env-tunable;
  breaches return a real `429` with `Retry-After`. Bodies over 25 MB
  are refused `413` before being read.
- *Webhooks that finish the job*: failed deliveries retry with
  exponential backoff (30 s base, 5 attempts), then dead-letter;
  operators list deliveries (`GET /v1/webhooks/deliveries`) and replay
  them (re-signed, re-delivered). An SSRF guard refuses non-public
  webhook targets before any network call.
- *Encryption at rest for stored media* (`server/storage.py`):
  AES-256-GCM envelope encryption — per-file keys wrapped by a master
  key from `KYC_MASTER_KEY` / `KYC_MASTER_KEY_FILE` (never in the DB
  or repo). Existing plaintext files migrate in place with per-file
  SHA-256 verification (`python3 -m server.storage --data-dir …
  migrate`). Encrypted files fail closed (`503`) when the key is
  absent. Follow-up work needing stored media goes through this
  module's `write_file` / `read_file` / `materialize` — the single
  storage read/write helper for media.
- *Backup + restore, exercised*: `scripts/backup.py` produces a
  checksummed backup (DB snapshot + media tree + manifest);
  `scripts/restore_drill.py` restored one for real into a scratch
  instance — restored server healthy, records readable, document
  decrypted byte-identical (measured: benchmarks/BACKUP-RESTORE.md).
- *Self-pen-test*: `scripts/pentest_local.py` — 32 scripted probes
  (auth bypass, cross-tenant, SQLi, traversal, SSRF, upload abuse,
  MFA gate, rate limit, body cap): **32/32 pass, 0 findings**
  (docs/PENTEST.md). An independent external pen test is still open —
  the self-test does not impersonate one.

### Screen-replay + portrait-substitution defence (2026-10-26)

A document shown on another phone/monitor screen and held to the
camera must be caught. Authenticity (`server/authenticity.py`) now
carries four screen-evidence signals alongside ELA/metadata/format:
**moiré** (FFT periodic peak), **pixel grid** (the display lattice —
strong high-frequency FFT peaks on *both* axes), **gloss** (specular
highlight blobs among non-background pixels) and **gamut** (lifted
black floor + pushed saturation). **Moire + any other screen signal →
authenticity FAIL, `document_on_screen`** — that combined case may fail
on screen evidence alone; single weak signals still never fail a
document. Measured on the synthetic fixtures: clean card — no screen
evidence; screen recapture — moiré 0.49 (strong), pixel grid 0.45–0.52
(strong). The client scanner adds a live refresh-banding watch (see
above). Separately, **portrait-region analysis** runs the manipulation
evidence on the portrait zone of card layouts specifically (grain
ratio vs the rest of the card; region ELA vs whole-image ELA): a
manipulated portrait region is the named finding
`portrait_region_tamper` (a smoothed synthetic splice measured grain
ratio 0.02 vs ~1.0 clean).

A **security-feature pack** adds four more calibrated signals, none
failing alone except as combined evidence: **font consistency**
(glyph-height variance + outlier glyphs in the name and
document-number zones from OCR word boxes → `altered_text_suspect`),
**compositing edges** (gradient halo on the portrait region's
rectangular border vs its interior → `compositing_suspect`; measured:
clean card 0.30, pasted-portrait splice 3.23), **border edges**
(document-border double-edge/ghosting via edge-profile runs →
`suspicious_edges`; clean card none, double-drawn border strong on
2 sides) and **pattern presence** (background texture energy in
non-text regions vs the template's `pattern_expected` →
`missing_pattern`; drawn card 6992, flat synthetic fill 0.96).

### Deepfake / fake-camera defence + continuous face tracking (2026-10-26)

The selfie + liveness path is analysed as a **combination**, and the
case records a `biometric_evidence` block listing every component:

- **Continuous face tracking** (`server/facetrack.py`): YuNet + SFace
  over the liveness frames, the selfie and a ~1 s burst of extra
  selfie frames. Presence ratio (≥ 80% of sampled frames), centre/size
  trajectory, and **identity continuity** — every frame's embedding
  vs the track median and its neighbours. A mid-stream face swap /
  embedding jump fails with `face_track_identity_break`. Face match
  compares the document portrait against the track's **aggregate
  (median) embedding**, never a single frame.
- **Liveness**: the server-issued movement challenge (unchanged).
- **Deepfake / injection** (`server/deepfake.py`): rPPG pulse scoring
  (POS + CHROM + green-channel cheek series, 0.7–3 Hz band
  periodicity/SNR under a signal-quality gate — WS2),
  generation-artifact FFT scoring on face crops, motion-trajectory
  statistics, and the client capture signals the flow sends (camera
  track label — a known virtual camera such as OBS/ManyCam/Snap
  Camera is a **hard fail**, `virtual_camera_detected` — plus
  device-motion telemetry). No pulse **plus** high generation
  artifacts fails with `deepfake_suspected`; partial evidence is named
  findings + risk; unanalysable media is unclear/error, never a pass.
- **Combination gate**: an automatic approval requires **all** of
  face track, liveness, face match, capture quality, device signals
  and deepfake present *and* passing together. A failed component
  auto-rejects through the required checks; a merely *absent* one
  (e.g. no device signals recorded) blocks auto-approval.

**Honest limits of the deepfake layer:** rPPG from a ~4.5 s
VP8-compressed webm is a *weak* signal (frequency resolution ≈0.22 Hz;
the codec crushes subtle chroma oscillation). It is weighted
accordingly — evidence-combining only, never sole pass/fail. Positive
control, run 2026-10-26 on the owner's real phone captures: the face
track passed his clean take (presence 0.96, identity min-cosine
0.91); his hard head-turn take collapsed on both identity metrics
(0.13 / 0.10) — at ≤24 sampled frames an extreme pose change between
samples is indistinguishable from a discontinuity, and the tracker
fails closed (a re-scan, not a review). **WS2 update:** the pulse leg
now runs POS + CHROM + green under a signal-quality gate; on the same
real takes POS measures a plausible 1.34 Hz peak (SNR 3.2) but still
below the evidentiary bar, and the WS2 attack suite measured the leg
firing "pulse present" on some jittered presentations of real photos
— so it remains **evidence-only**, and the flow now records ~9 s
liveness clips to give it a measurable window (unmeasured on real
captures until one exists). The artifact leg read clean (0.11) on the
owner's takes — so in the combination gate the deepfake leg is
required to be *not failing*, per its design, rather than a positive
pass. No deepfake detector is claimed to be conclusive; this is
layered evidence, not a proof. Measured detail: benchmarks/
BIOMETRICS.md.

### Voice guidance, phone-only, IP harvest + VPN gate (2026-10-26)

- **Voice guidance**: the scanner *talks* the applicant through
  positioning with the **device's built-in speech voice** (Web Speech
  API `speechSynthesis` — on-device, no server cost). Voice + text +
  frame state are one guidance state machine. Lines are natural and
  descriptive — "The place where you are is dark. Move to a brighter
  place.", "There's a glare on your ID. Tilt it slightly.", "This
  looks like a screen. Scan the physical document." — spoken on state
  change, repeated at most every ~6 s, never overlapping; starts only
  after the consent tap (autoplay policy); a mute toggle is provided;
  without `speechSynthesis` the flow is text-only.
- **Phone-only**: the scanner does not run on desktop browsers at all.
  A non-mobile browser gets a "Continue on your phone" handoff screen
  — a QR code of the exact flow URL generated client-side by a small
  inline QR implementation (no external CDN), with the full link and
  a Copy button as fallback.
- **IP harvest + location check**: the tunnel Worker stamps
  `X-Client-IP` (from `CF-Connecting-IP`) and `X-IP-Country` (from
  `request.cf.country`) onto forwarded requests — the tunnel protocol
  carries headers, so this *is* wired end-to-end. The server records
  the client IP + IP country on the session at flow start and at
  submission, and runs `location_consistency`: IP country vs declared
  country — match passes; unknown (local/dev) is recorded honestly;
  mismatch is a **risk contribution (+15, `ip_country_mismatch`)**,
  shown masked in the console (e.g. `41.203.x.x`), and never rejects
  on its own (travel and VPNs exist). Consent (text version **v2**)
  discloses device + IP collection.
- **VPN/proxy hard gate**: at flow start and again at submit, the
  client IP is checked against IP intelligence (keyless ip-api.com:
  proxy/hosting/mobile flags + ISP/ASN; 3 s timeout; per-IP cached in
  the DB for 24 h), corroborated — record-only — by device-timezone vs
  IP-country and a WebRTC local-IP probe. **Detected** (proxy flag, or
  hosting on a non-mobile connection) **blocks the flow** with "VPN or
  proxy detected. Turn off your VPN or proxy and try again." — the
  scanner never starts — and any submission under a detected
  VPN/proxy auto-rejects (`vpn_proxy_detected`, a hard fail, not risk
  points). If the lookup itself is unreachable the verdict is recorded
  as `unknown` — never a fake pass. **Limits, honestly:** residential
  proxies and fresh VPN ranges can evade IP intelligence; the free
  ip-api tier is rate-limited and HTTP-only; timezone and WebRTC are
  corroboration, not proof. Detection is strong evidence, not a
  guarantee.

### Per-country document registry

`server/docregistry.py` is the source of truth: every document type
carries facts — `sides` (1|2), `has_expiry`, `mrz` — that drive
validation, the scanner's automatic back-side prompt, and the expiry
check. Owner-specified: **Nigeria** — passport, driver's licence,
national ID, voter's card (INEC PVC, *no expiry*), NIN card (*no
expiry*), NIN slip (*no expiry*); **United States** — passport,
passport card, driver's license, state ID. Beyond those two: driver's
licences for GB/CA/AU/DE/GH with generic card facts, national ID only
for DE/GH, and passport-only for KE/ZA/IN/PH/SG/AE/FR/NL/IE — all
pending the Phase 4 WS1 researched per-country merge (see the launch
coverage section and docs/CLAIMS-AUDIT.md).
A document type with `has_expiry: false` **never** fails or goes
unclear for a missing expiry date — the expiry check passes with the
detail "document type has no expiry date" (age is still checked).

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
  the real face checks, so sandbox Level 2/3 sessions with synthetic
  media are **auto-rejected by the engine** (fail-closed) under the
  automatic-decision rules; the E2E completes them through the
  console's four-eyes override path, which is what the console is for.
- **Authenticity signals are heuristics**, calibrated on synthetic
  images (ELA block spread, moiré FFT energy share). Combined evidence
  decides; one weak signal alone never fails a document. They are a
  routing/tamper-triage layer, not a forensic guarantee.
- **Sandbox honesty note:** this build does **not** fake outcomes: test
  keys run the identical real checks; "test" means strict data
  separation from live (a test key can never read live data), nothing
  more.
- No billing, no email sending. Tenant "teams" exist as named
  reviewer tokens with roles (admin/reviewer) for console actions —
  not full user accounts with passwords (reviewers can add TOTP MFA,
  WS3). No malware scanning of uploads; no CI vulnerability scanning;
  no external penetration test yet (a scripted self-pen-test is green
  — docs/PENTEST.md). The SQLite database file itself is not
  encrypted (stored media files are, WS3).

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
The applicant completes a short flow on their phone (the scanner is
phone-only — a desktop browser gets a "continue on your phone"
handoff screen; the tenant console remains a desktop web app):

1. Enter basic details (legal name, date of birth, country).
2. Live-scan a government ID with the camera (front, and back when the
   document has one) — the scanner captures automatically when the
   document is aligned; there is no gallery/upload path.
3. Live selfie — captured automatically when the face is in the oval,
   checked against the ID photo, with a live movement-challenge
   liveness check so a photo of a photo does not pass.
4. Depending on the level: proof of address, and screening against
   sanctions / PEP / watchlists.

KYC runs its checks and produces a **decision**: approved or rejected
automatically in the standard path. The only routes to a human are the
named exceptions — a tenant configuration that requires review, a Level 3
screening hit awaiting disposition, KYB, or a platform error. The result
goes back to the business by API and signed webhook, and is visible in the
review console. The business never has to build document capture, OCR,
face matching, case review, or audit trails itself.

## Verification levels

| Level | Name | Checks |
|---|---|---|
| 1 | Basic | Live document scan with capture quality, framing, layout classification, OCR, expiry/age, profile consistency and cross-source data consistency |
| 2 | Standard | Everything in Basic + MRZ where the document carries one, authenticity and security-feature evidence, continuous face tracking, face match, active liveness and deepfake evidence |
| 3 | Enhanced | Everything in Standard + proof of address + sanctions screening against the lists actually loaded + ongoing monitoring. PEP/adverse-media coverage exists only when such a list is loaded — it is never implied |
| KYB | Business | Registration-number format validation + company document + reviewer confirmation (no live government registry connection yet), with directors / ultimate beneficial owners each verified at Level 2+ |

## The blueprint

Read in this order:

1. **[docs/BLUEPRINT.md](docs/BLUEPRINT.md)** — the full product blueprint:
   users, journeys, every check in detail, the decision engine, the review
   console, pricing shape, and what "done" means for each part.
2. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — original proposed
   architecture; superseded in part by the built system (see its status
   banner and docs/CLAIMS-AUDIT.md).
3. **[docs/DATA-MODEL.md](docs/DATA-MODEL.md)** — database schema draft
   (the SQLite implementation mirrors it; see its status banner):
   tenants, applicants, sessions, documents, checks, cases, webhooks, audit.
4. **[docs/API.md](docs/API.md)** — REST API and webhook contract:
   implemented endpoints plus explicitly marked unimplemented items.
5. **[docs/COMPLIANCE-AND-PRIVACY.md](docs/COMPLIANCE-AND-PRIVACY.md)** —
   the legal/privacy ground rules this product must be built inside.
6. **[docs/SECURITY.md](docs/SECURITY.md)** — threat model and control
   targets; implementation status lives in docs/CLAIMS-AUDIT.md.
7. **[docs/ROADMAP.md](docs/ROADMAP.md)** — phased build record and plan.
8. **[docs/DECISIONS.md](docs/DECISIONS.md)** — the owner's decisions
   D1–D8, settled 2026-10-26 (Nova Inc product, internal first, expanded
   worldwide coverage, local-first build, Cloudflare as production home).
9. **[docs/AMBITION.md](docs/AMBITION.md)** — the standing bar: more
   advanced than Sumsub, Persona, and Onfido — claimed only where built,
   tested, and measured.
10. **[docs/CLAIMS-AUDIT.md](docs/CLAIMS-AUDIT.md)** — the Phase 4 WS0
    audit: every public claim checked against the code, with gaps
    assigned to workstreams.
11. **[docs/PHASE4-PLAN.md](docs/PHASE4-PLAN.md)** — the approved
    Phase 4 plan (WS0–WS8).

## Non-negotiable build rules

- **Real or not shipped.** Every check named in a release actually runs in
  that release. No placeholder checks, no demo decisions, no fake results.
- **Fail closed.** If a check cannot run, times out, or returns unclear,
  the outcome is *rejected* or one of the named review exceptions —
  never an automatic approval.
- **Automation decides; humans audit and override.** The standard path
  is fully automatic. A trained reviewer in the console can overturn a
  decision only with a reason, the overturn is audited, and four-eyes
  confirmation applies where the flow configuration requires it.
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
Ireland**. **Passports are accepted for every country in that list**
(the MRZ is a worldwide standard). The full per-country document list
with per-document facts (sides / expiry / MRZ) lives in the registry,
`server/docregistry.py` — Nigeria and the United States carry the
owner-specified document sets (incl. NG voter's card, NIN card and
NIN slip; US passport card and state ID). Driver's licences are also
listed for the United Kingdom, Canada, Australia, Germany and Ghana
using generic card facts pending the Phase 4 WS1 researched merge.
A general national identity card is listed only where that document
class exists (Nigeria, Germany, Ghana) — there is no generic
"national ID" for the US, UK, Canada or Australia. The other nine
launch countries are passport-only today.

## Licence / visibility

Public repo for now, by the owner's instruction; it may go private later.
No licence is granted by the presence of this blueprint.
