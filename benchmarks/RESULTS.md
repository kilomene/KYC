# Vision Extraction Benchmark — Results (Phase 4 WS1)

Measured 2026-10-26 by running `scripts/benchmark_vision.py` against the
real pipeline (`vision.read_document_text` + `fieldtemplates.extract_fields`).
These are the numbers as measured in that run; nothing here is estimated.

## Corpus

- Document types (12): NG/passport, NG/drivers_licence, NG/voter_card, NG/nin_card, NG/nin_slip, US/passport, US/passport_card, US/drivers_license, US/state_id, GB/drivers_licence, DE/national_id, IN/aadhaar
- Synthetic identities per type: 2
- Degradation levels: clean, blur_light, blur_heavy, downscale_50, dark, rotate_4
- Documents total: 144 (type x identity x level)

Degradations are applied to the rendered document image at named levels:
`blur_light` = Gaussian blur radius 1.2; `blur_heavy` = radius 2.5;
`downscale_50` = rendered at 50% size; `dark` = brightness x0.65;
`rotate_4` = rotated 4 degrees. `clean` = undegraded.

## Headline numbers

- Clean corpus: exact-match **1.0000**, mean CER **0.0000**
- All levels combined: exact-match **0.9554**, mean CER **0.0288**

Clean per-field exact-match: dob 1.000, expiry 1.000, given_names 1.000, number 1.000, surname 1.000

## Per degradation level

| Level | Exact-match | Mean CER | Field values |
|---|---:|---:|---:|
| blur_heavy | 0.7679 | 0.1452 | 112 |
| blur_light | 1.0000 | 0.0000 | 112 |
| clean | 1.0000 | 0.0000 | 112 |
| dark | 1.0000 | 0.0000 | 112 |
| downscale_50 | 1.0000 | 0.0000 | 112 |
| rotate_4 | 0.9643 | 0.0276 | 112 |

## Per document type (all levels)

| Type | Exact-match | Mean CER | Documents |
|---|---:|---:|---:|
| DE/national_id | 0.9333 | 0.0375 | 12 |
| GB/drivers_licence | 0.9667 | 0.0042 | 12 |
| IN/aadhaar | 0.9375 | 0.1213 | 12 |
| NG/drivers_licence | 0.9667 | 0.0042 | 12 |
| NG/nin_card | 0.9375 | 0.0885 | 12 |
| NG/nin_slip | 0.9583 | 0.0038 | 12 |
| NG/passport | 0.9500 | 0.0539 | 12 |
| NG/voter_card | 0.9583 | 0.0052 | 12 |
| US/drivers_license | 0.9667 | 0.0042 | 12 |
| US/passport | 0.9500 | 0.0352 | 12 |
| US/passport_card | 0.9667 | 0.0042 | 12 |
| US/state_id | 0.9667 | 0.0042 | 12 |

## Per field (all levels, all types)

| Field | Exact-match | Mean CER | n |
|---|---:|---:|---:|
| dob | 1.0000 | 0.0000 | 144 |
| expiry | 1.0000 | 0.0000 | 96 |
| given_names | 1.0000 | 0.0000 | 144 |
| number | 0.8264 | 0.0636 | 144 |
| surname | 0.9653 | 0.0708 | 144 |

## Honest limits

- The corpus is SYNTHETIC: documents are drawn programmatically to each
  type's template layout with known ground truth. These numbers measure
  the extraction wiring (zones, label anchors, format validators, OCR)
  on template-conformant documents. They are an UPPER-BOUND signal, not
  a real-world accuracy claim: real documents vary in layout, print
  quality, wear, and capture conditions in ways a drawn corpus cannot.
- No licensed specimen corpus was available for this run; the Phase 4
  plan's 'synthetic + licensed specimen' corpus is therefore only half
  met, and this file says so rather than implying otherwise.
- Accuracy collapses first under heavy blur (blur_heavy exact-match
  0.7679): the pipeline's answer to that in production is
  the capture-quality gate (blurred captures are rejected/rescanned),
  not extraction heroics.
- Dates in the corpus are printed in unambiguous formats (ISO, or
  DD.MM.YYYY for DE). Ambiguous locale formats (e.g. US MM/DD/YYYY vs
  DD/MM/YYYY on unlabelled fields) are not measured here.
- The test-suite floor (tests/test_benchmark.py) is calibrated from
  this run: clean exact-match measured 1.0000, floor set at 0.90.
