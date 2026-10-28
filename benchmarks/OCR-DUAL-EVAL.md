# Dual-Engine OCR Capability Evaluation

Measured 2026-10-28 on the owner's labelled real-sample set (genuine
documents; values never recorded — counts only). Every case is read
under production conditions: the orientation-normalised rendition
ingest stores, front side, through the production extraction brain.

Arms:
- **TESS** — Tesseract word stream only.
- **PADDLE** — PaddleOCR (PP-OCRv5 mobile) word stream only.
- **UNIFIED** — the merged stream + cross-engine arbitration
  (production `_read_document` logic).

Score = applicable identity fields extracted (surname, given names,
dob, number, expiry). Fields a document type does not print are
excluded (NIN slips print no DOB/expiry; the NIN card and the
voter's card print no expiry).

## Main set — fields extracted

| Case | TESS | PADDLE | UNIFIED |
|---|---|---|---|
| NG voter's card front | 2/4 | 2/4 | **3/4** |
| NG FRSC licence front | 0/5 | 3/5 | **3/5** |
| US California DL front | 2/5 | 2/5 | **3/5** |
| US New York ID front | 1/5 | 1/5 | 1/5 |
| Canada passport | 3/5 | 3/5 | 3/5 |
| NG digital NIN slip | 3/4 | 3/4 | **4/4** |
| NG NIN slip A (glare) | 3/3 | 3/3 | 3/3 |
| NG NIN slip B (clean) | 3/3 | 2/3 | 3/3 |
| NG NIN slip C | 3/3 | 3/3 | 3/3 |
| NG NIN slip D (sideways photocopy) | 2/3 | 1/3 | 2/3 |
| NG NIN slip raw photo | 3/3 | 3/3 | 3/3 |
| **Total** | **25/43** | **26/43** | **31/43** |

The unified reader is never below the best single engine on any
case, strictly above both on three (voter's card, California DL,
digital NIN slip — the digital slip's complete date of birth is a
unified-only read; Tesseract's long-standing residual on that
document was year-only). New York's front is the tie: that
document's identity is carried by its back's PDF417 payload in
production, which these front-only arms do not model.

## Robustness (UNIFIED arm, fields retained)

Degraded copies of three cases, read WITHOUT re-normalisation
(production ingest normalises orientation at upload, so rotation
rows understate the deployed pipeline):

| Case | rot90 | rot180 | rot270 | 1024px | 640px | JPEG q55 |
|---|---|---|---|---|---|---|
| Digital NIN slip (clean 4/4) | 3/4 | 3/4 | 3/4 | 4/4 | 2/4 | 3/4 |
| NIN slip B (clean 3/3) | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| California DL (clean 3/5) | 2/5 | 3/5 | 3/5 | 3/5 | 2/5 | 3/5 |

## Barcode decoding (document backs)

Decoder ensemble = zxing ladder, then OpenCV arms
(cv2.barcode + WeChatQRCode) when zxing finds nothing.

| Back | Ensemble result | OpenCV arms alone |
|---|---|---|
| NG voter's card | PDF417 | — |
| NG FRSC licence | PDF417 | — |
| US California DL | Code 128 | — |
| US New York ID | PDF417 + Code 128 | — |

**No measured gain from the OpenCV arms on this set** — every code
found was found by zxing, and the California back's PDF417 remains
undecodable at that photo's resolution across all decoder families
tried (zxing, cv2.barcode, WeChatQR). The arms stay as zero-cost
redundancy (they run only when zxing finds nothing); no capability
is claimed for them.

## Portrait detection (fronts)

YuNet found the printed portrait on 8 of 11 fronts. The ResNet-10
fallback detector added **zero** saves on this set — both detectors
miss the same three (voter's card, slips B and C, whose printed
portraits are very small). The fallback stays wired (presence-only,
for the capture-coaching statistic) with no claimed improvement.

## Quality gate (per capture)

`vision.quality_report` (blur score, glare fraction, grade) is
computed on every production read. On this set it graded the
California DL photo "poor" (blur 55 — it is visibly soft) and the
remaining captures fair/good, matching their known condition.

## Notes

- A first battery run was killed by a VM replacement after 8 of 11
  cases; the re-run completed all sections (one robustness row and
  the portrait/quality rows were finished by a follow-up pass).
- Read timings on this 2-core VM: ~40–145s per document for the
  three-arm battery path (production runs the unified arm only,
  with the model kept loaded).
