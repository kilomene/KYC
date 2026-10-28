# Recalibration evaluation — authenticity, classification, US reads (2026-10-28)

*Owner's orders 2026-10-28 05:08 + 05:27 PDT ("fix it with full
functionality and high advancement… thoroughly"). Measured with the
production document-side pipeline on the local corpus. Document
values are never recorded here — structure and scores only.*

## Why

The Stage-4 fake battery and the owner's scan batches 1–13 exposed
three calibration defects:

1. **Authenticity convicted genuine documents.** A signal census over
   the 14 genuine corpus documents (11 signals each) showed 9 of 14
   scoring ≥ 60 — the old automatic-fail line. Two signals drove it:
   ELA "strong" (50 pts) fires on most genuine phone photos, and
   font-consistency "strong" (25 pts) fired on 13 of 14 genuine.
   Together they alone crossed the fail line. The owner-tagged fake,
   by contrast, scored 70 with a completely different fingerprint —
   the corpus's ONLY metadata/editing-trace points (30) plus a
   portrait anomaly.
2. **Nigerian voter's-card classification was mis-calibrated.** The
   template carried the driver's-licence portrait zone (left) while
   the PVC prints its portrait on the right; blameless elements
   (frame-only aspect, an unfound portrait) dragged the score as
   failures; and a 1.4%-of-frame noise box counted as "portrait
   found, misplaced".
3. **US dates and numbered labels were misread.** The date parser
   read day-first only: any US date with day > 12 was unparseable,
   and ambiguous US dates were silently month/day-swapped. The
   issue date was scooped into both the DOB and expiry slots (the
   Wisconsin false decline: a card in date to 2031 was declined as
   "expired"). AAMVA numbered labels (3 DOB, 4b EXP, 4d LIC NO)
   anchored weakly or not at all — both Illinois expiries were
   missed by the platform's own read.

## What changed

- **Authenticity (server/authenticity.py):** a points hard-fail now
  requires ≥ 60 points AND corroboration — at least two non-edit
  signal families (screen / provenance / portrait / structure /
  data) at moderate or above. Edit-family signals (ELA,
  font-consistency, compositing edges) can no longer convict alone.
  The screen rule is unchanged. The altered-text annotation now
  requires font-consistency strong AND a metadata signal — it no
  longer fires on ordinary genuine photos.
- **Classification (server/templates.py):** NG voter_card portrait
  zone corrected to the right side; INEC issuer aliases added;
  frame-only aspect and unfound-portrait elements are neutral
  (excluded) instead of scored failures; fewer than two scored
  elements returns "evidence insufficient"; micro-boxes (< 5% of
  frame width) count as not found; a claim whose country anchor is
  absent is capped below the pass line unless a check-digit-valid
  MRZ names the claimed country as issuer. PASS_SCORE stays 70.
- **US extraction (server/fieldtemplates.py):** `parse_date_value`
  gains validity-swap (a second number > 12 with the first ≤ 12 can
  only be month-first) and a month-first locale for US/PH documents;
  fused numbered labels anchor (`3DOB`, `4BEXP`); composite AAMVA
  labels added for US licence/ID (4D LIC NO, 4B EXP, LN/FN);
  a borrowed-date gate drops any DOB/expiry value that would make
  a document expire on or before the holder's birth date unless
  the value came from its own printed label.

## Measured before → after

### Authenticity verdicts over the census corpus (new rule applied to the recorded signal sets)

| Set | Before (old rule) | After (corroboration rule) |
|---|---|---|
| 14 genuine documents | 9 at fail-level points (≥ 60) | **0 fail** — all pass/unclear |
| Owner-tagged fake CA ID | fail (70 pts) | **fail** — provenance + portrait corroborate; altered-text annotation intact |
| 7 subject cards | 1 fail (damaged slip) | 0 fail — all unclear |

Violations at the gate: **0** (criterion: no genuine fails; the fake
still fails).

### Classification

| Case | Before | After |
|---|---|---|
| Subject NG voter's card | FAIL 43.3 | **PASS 79.2** |
| Genuine control voter's card | FAIL 21.1 | FAIL 61.5 — improved; residual below |
| CA licence claimed as NG voter's card | — | FAIL 29.2 (guard holds) |
| Wisconsin DL | PASS 100 | PASS 100 |

### US extraction

| Case | Before | After |
|---|---|---|
| Wisconsin DL | issue date in both date slots → "expired" | DOB and EXP each from its own label; **expired: false**; verdict corrected to APPROVED |
| Illinois ID #1 (expiry 2022) | number + surname only; expiry missed | all four fields; expiry from label; **expired: true** — the platform now catches this decline itself |
| Illinois ID #2 (dim photo) | number + surname only | number + surname; expiry still missed on this photo (named gap) |
| Colorado DL | number + surname only | all four fields; expiry from label; expired: false |

## Named residuals (not hidden, not threshold-tuned away)

- **Control voter's card still fails classification (61.5).** Its
  photo is sideways and the current build's orientation stage does
  not rotate it — verified again with a fresh normalisation during
  this gate (output still portrait). The score gain (21.1 → 61.5)
  came from the zone and neutrality fixes. Orientation behaviour
  varies by tesseract build; this is an ingest-orientation gap on
  one photo, not a scoring-threshold problem, and PASS_SCORE was
  not lowered to mask it.
- **Wisconsin number reads as a 4-character fragment** from the zone
  step; the full number never enters the candidate set on this
  photo, and its back PDF417 does not decode at this resolution
  (all decoder families). The format check is behaving correctly —
  the gap is extraction completeness on one photo.
- **DD audit-line consistency** (several states print an audit line
  embedding the licence number / birth date — a free internal
  cross-check) is designed but not built: per-state formats differ
  and need research before the check can be real rather than
  decorative.
- **Illinois ID #2's expiry** remains unread on its dim photo.

## Standing principles confirmed by this programme

- A document stays valid until its printed expiry even when the
  issuing state changes its design — template generations are
  equally valid; verdicts rest on originality forensics, expiry,
  and data consistency, never on design generation.
- One noisy signal family never convicts. Conviction requires
  independent corroboration.
