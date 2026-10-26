# Biometrics Benchmark — Results (Phase 4 WS2)

Measured 2026-10-26 on this machine, through the production pipeline
(`server/bioprovider.py` → `server/face.py`: YuNet detection + SFace
embeddings). Raw data: `benchmarks/biometrics.json` (FAR/FRR) and
`benchmarks/attacks.json` (attack suite). Nothing here is estimated;
where a number could not be measured in this environment, this file
says UNMEASURED and why.

## 1. Face match — FAR/FRR on LFW (real labelled faces)

Dataset: **Labeled Faces in the Wild, deep-funneled release**
(13,233 images, 5,749 identities — the published counts, verified on
the extracted corpus). Protocol: the **official View-2 pairs.txt —
all 6,000 pairs** (10 folds × 300 same + 300 different), no
subsampling. Provenance: the UMass host was unreachable from this
network, so the archive came from the figshare mirror scikit-learn
uses (`ndownloader.figshare.com/files/5976015`); the pairs.txt used
here is **byte-identical (sha256 ea42330c…) to the pairs.txt inside
the dataset authors' own archive** and to two independent GitHub
mirrors. Embeddings were computed for the 7,701 unique referenced
images, each through the production adapter.

| Measure | Value |
|---|---|
| Pairs scored | 6,000 / 6,000 |
| Detection failures (YuNet found no face) | **0 pairs (0.0%)** |
| EER | **1.07%** at threshold 0.288 |
| **At production threshold 0.363** | **FAR 0.10% · FRR 2.00% · accuracy 98.95%** |
| Standard protocol accuracy (per-fold threshold, 10 folds) | **99.13% ± 0.38%** |

Honest reads on these numbers:

- **Zero detection failures is a property of this corpus, not of the
  product.** Funneled LFW images are pre-cropped faces. On real phone
  media the same detector measured a 0.76 presence ratio on the
  owner's hard head-turn capture (§4). Do not quote the 0% outside
  this corpus.
- The production threshold costs genuine users more than it costs
  security: at 0.363, 60 of 3,000 genuine pairs are rejected (FRR
  2.0%) against 3 of 3,000 impostor pairs accepted (FAR 0.10%).

### Threshold analysis (from the measured curve, not defaults)

| Use case | Data-supported threshold | Measured FAR | Measured FRR |
|---|---|---|---|
| Auto-approve (target FAR ≤ 0.1%) | 0.351 | 0.10% | 1.87% |
| **Production today: 0.363** | — | **0.10%** | **2.00%** |
| High-assurance (target FAR ≤ 0.01%) | 0.413 | 0.00% (0/3,000) | 3.33% |

**Verdict: keep 0.363.** It sits 0.012 from the data-derived
auto-approve threshold and already delivers the target FAR; moving
to 0.351 would buy 0.13 points of FRR with no FAR change at this
resolution. The high-assurance figure (0.413, FAR 0/3,000 at FRR
3.33%) is recorded for tenants who want a stricter tenant-configured
threshold — it is a tenant option in the flow config, not a new
default. `face.DEFAULT_THRESHOLD` is unchanged; this table is the
measurement it now stands on.

### Condition slices — SIMULATED degradations

Same protocol, folds 1–2 (1,200 pairs), degradation applied to the
second image of each pair. These are **simulations on real faces**
(labelled as such): darkening ×0.45 (low-light proxy), downscale to
25% and back (low-resolution / device-tier proxy), Gaussian blur
9×9 (defocus proxy). Detection failures: 0 in every slice.

| Slice (simulated) | EER | FAR @0.363 | FRR @0.363 | Accuracy @0.363 |
|---|---|---|---|---|
| Clean (folds 1–2 subset) | — (full-set EER 1.07%) | 0.10% (full set) | 2.00% (full set) | 98.95% (full set) |
| Dark | 1.33% | 0.00% | 2.33% | 98.83% |
| Downscale | 1.67% | 0.00% | 3.83% | 98.08% |
| Blur | 1.50% | 0.00% | 3.50% | 98.25% |

Degradations tax genuine users (FRR up to ~2× clean) and do not open
a false-accept hole in this corpus — consistent with the capture
quality gate's job of forcing a re-scan instead of a guess.

### Demographic slicing — UNMEASURED, stated plainly

LFW carries **no skin-tone, age, or demographic attributes**, and no
attribute-labelled public face set could be downloaded in this
environment without an account/licence gate (FairFace/UTKFace are
Kaggle-gated; the LFW attribute annotations from the literature were
not reachable). Rather than fabricate labels, **no demographic
accuracy claim is made**. This remains an open WS2 remainder: the
moment a lawfully downloadable attribute-labelled set is available,
the harness slices by it with the same code path (the pair records
already carry per-pair metadata hooks). COMPLIANCE §3 fairness
testing stays open until then.

## 2. Presentation-attack suite

Sources: the owner's own stored real captures (his data, his
platform) + LFW faces. Every artefact ran the PRODUCTION defences
(liveness, deepfake, face track, face match, plus document-path
moiré/pixel-grid signal readings on attack frames). An attack is
**rejected** when a required leg fails (production auto-rejects) and
**blocked** when it is not rejected but the combination would not
auto-approve it. Full per-artefact detail: `benchmarks/attacks.json`.

| Family | Label | N | Rejected | Blocked (not rejected) | Blocked-or-rejected |
|---|---|---:|---:|---:|---:|
| Video replay | **REAL artefacts** | 2 | 1 | 1 | **2/2** |
| Printed photo | SIMULATED print | 3 | 0 | 3 | **3/3** |
| Screen replay | SIMULATED screen | 2 | 1 | 1 | **2/2** |
| Mask | SIMULATED rigid proxy only | 2 | 0 | 2 | **2/2** |
| Deepfake (morph/composite) | SIMULATED | 2 videos + 2 stills | 2/2 videos, 2/2 stills | 0 | **4/4** |

Per family, honestly:

- **Replay (REAL).** The owner's genuine liveness videos, replayed
  verbatim, were judged against 3 fresh server challenges each:
  liveness passed **0 of 6** evaluations — challenge freshness alone
  kept a bit-perfect replay from passing. The clean take was blocked
  (not rejected); the hard take was rejected (it fails its own
  track/liveness on the merits). A replay's only road in would be a
  challenge collision, which the randomised 2-movement challenge
  makes a 1-in-12 guess per attempt before any other leg is counted.
- **Print (SIMULATED).** No print artefact was auto-rejected; all
  were blocked because a static presentation cannot pass the
  movement-challenge liveness. The deepfake leg is NOT what stops
  prints: its POS pulse leg fired "present" on 2 of 3 jittered print
  presentations in the seeded run (handheld jitter moves real skin
  tones through the ROI at pulse-like rates). Anyone quoting a
  print catch rate for this platform should quote the combination
  (3/3 blocked), never the pulse leg.
- **Screen (SIMULATED).** 1 of 2 rejected (the hard take fails its
  own track/liveness), 1 blocked. Moiré readings on simulated screen
  frames (0.186, 0.237) ran ~2–3× genuine frames (0.063–0.086), but
  that signal guards the document path in production; the deepfake
  verdict on the screen replays themselves stayed *unclear*, not
  fail. The block came from liveness/track, not screen detection.
- **Mask (SIMULATED proxy only).** A physical mask **cannot be
  produced in this environment — real-mask resistance is
  UNMEASURED.** The rigid 2D proxy (printed texture on a uniform
  oval, rigid motion) was blocked 2/2 by liveness, again not by the
  deepfake leg (POS fired on the periodically-moving proxy in 1 of
  2). Do not convert this into a mask claim.
- **Deepfake (SIMULATED).** No DNN face-swap generator is installed,
  so a true GAN/diffusion swap corpus is **UNMEASURED**. What was
  measured: face-morph stills were **rejected by face match**
  against the owner's selfie reference (similarities 0.12 and
  −0.15, both fail; the production doc match could not score them —
  see §4), and both the morph-composited video and the identity
  crossfade video were **rejected by face-track identity break** —
  the continuity leg doing exactly its designed job.

## 3. Genuine controls (same harness, reported as-is)

| Control | Liveness | Deepfake | Face track | Face match | Combination |
|---|---|---|---|---|---|
| Owner clean take (real) | unclear | unclear | **pass** | unclear¹ | not rejected, not auto-approved |
| Owner hard take (real) | **fail** | unclear | **fail** | unclear¹ | **rejected** |
| Owner document vs selfie (real) | — | — | — | unclear¹ | — |

¹ Face match is *unclear* because YuNet finds **no face in the
owner's session-1 document capture at any scale** (see §4) — the
leg never reaches a similarity. That is a fail-closed outcome (it
blocks auto-approval), and it is a real product gap for far/angled
document photos, recorded here rather than smoothed over.

Genuine combination pass rate on stored captures: **0/2** — the
clean take is held by its liveness verdict (its recorded movements
do not register as the stored challenge at production sampling) and
by the document-face gap; the hard take is rejected outright
(extreme head turn — the documented fail-closed re-scan case). The
stored captures predate the current scanner; a fresh capture through
the live flow is the honest way to re-measure this, and it has not
been substituted with a friendlier artefact here.

## 4. Detection-at-resolution finding (found by this benchmark)

YuNet's behaviour depends strongly on input size, measured on the
owner's real 2316×3088 selfie against his own video frame:

| Input max-dim | 512 | 640 | 800 | 1024 | 1280 | 1600 | full |
|---|---|---|---|---|---|---|---|
| Same-face cosine | 0.435 | 0.423 | 0.408 | 0.390 | 0.205 | −0.052 | no face |

Pre-WS2, `face.py` detected at native size: multi-megapixel stills
returned **zero faces or corrupted alignments**. WS2 fix (in
`server/face.py`): detection/embedding run in a ≤1024px work space
(`MAX_DETECT_DIM`, `work_image()`); boxes are rescaled for
original-frame consumers. After the fix the owner's full-res selfie
matches itself at 1.0 and his clean-take track (with the selfie as a
track frame) passes. **LFW numbers are unaffected** (250px images
never enter the downscale path). Separately: the portrait in the
owner's session-1 *document* photo remains undetected at every
scale — small, angled portrait in a full-card photo; the current
scanner's close-up, detection-gated document capture is the regime
the pipeline is built for, and far-shot document portraits stay a
known gap (face match returns *unclear*, never a guess).

## 5. rPPG re-measurement (POS/CHROM hardening)

The pulse leg now runs POS (primary) + CHROM + the original green
leg, under a signal-quality gate (face presence, ROI jitter, size
stability). On the owner's two real ~4.5 s stored captures:

| Capture | POS | CHROM | Green | Quality gate | Combined |
|---|---|---|---|---|---|
| Clean take (4.5 s) | score 0.274, SNR 3.2, peak 1.34 Hz — not present | 0.296, SNR 4.2 — not present | 0.357, SNR 4.0 — not present | pass (jitter 0.0018) | **no pulse** |
| Hard take (3.1 s) | 0.312, SNR 2.0 — not present | 0.353, SNR 3.4 — not present | 0.227, SNR 1.4 — not present | pass | **no pulse** |

POS now produces a *measurement* where the old leg produced none
worth reporting — a plausible 1.34 Hz (≈80 bpm) peak on the clean
take — but on 3–4.5 s VP8 clips it stays **below the evidentiary bar**
(share ≥ 0.30 and SNR ≥ 6). Verdict: **the pulse leg remains
evidence-only.** The flow's liveness window is now ~9 s at a raised
recording bitrate so new captures give the leg a real chance; until
a longer real capture is measured, no stronger claim is made. The
synthetic-pulse positive control passes POS/CHROM in tests, and the
attack suite (§2) records the leg's known weakness honestly: it can
fire on jittered presentations of real photos, which is why it is
one leg of a combination and never a gate by itself.

## 6. What remains open in WS2

- Demographic slicing (needs a lawfully downloadable
  attribute-labelled dataset; §1).
- Physical-mask and true DNN-deepfake corpora (cannot be produced
  in this environment; §2 labels stand).
- External provider evaluation: the adapter exists
  (`server/bioprovider.py`, own SFace pipeline is provider #1
  through it; external slots fail closed as `provider_not_configured`)
  — a real head-to-head still needs vendor accounts/keys held by the
  operator. OPEN, not passed.
- Passive liveness: not built; the movement challenge remains the
  liveness mechanism, now measured.
- rPPG on the new ~9 s captures: unmeasured until a real longer
  capture exists (§5).
