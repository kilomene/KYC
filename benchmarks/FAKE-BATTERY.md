# Stage-4 fake-ID battery — 2026-10-28

The labelled benchmark set: genuine samples must pass; the owner-tagged
fake must be caught. Three California documents were run through the
production document-side pipeline offline (orientation normalisation,
framing, unified dual-engine read + extraction, template
classification, authenticity signals). No document values are recorded
here — statuses, scores and reason codes only.

| Case | Classification | Authenticity | Extraction | Outcome |
|---|---|---|---|---|
| Fake CA ID card (owner-tagged) | pass 85.6 | **FAIL** — suspected_recapture_or_edit, altered_text_suspect | number (format-valid) + given names | **CAUGHT at the authenticity layer** |
| Second CA DL (same name, different DOB/number/address) | **fail 57.8** — document_classification_mismatch | unclear — authenticity_signals_present, altered_text_suspect | surname + given names + number (format-valid) | **Stopped at classification; authenticity also elevated** |
| Genuine CA DL (control) | pass 85.6 | unclear — authenticity_signals_present, altered_text_suspect | surname + given names + number (format-valid) | Passes; NOT rejected |

Findings:

1. The template/classification layer cannot separate the fake from the
   genuine card (both 85.6 — the fake is a faithful visual copy). The
   **forensic authenticity layer is the discriminator**: it failed the
   fake outright with recapture/edit + altered-text reason codes.
2. The second card was stopped independently — classification mismatch
   (older-generation design + capture conditions score 57.8 < 70) with
   authenticity elevated. The two same-name cards carry mutually
   inconsistent birth dates/numbers; both were stopped on their own
   evidence, before any cross-document comparison.
3. **Signal-noise gap (named honestly)**: `altered_text_suspect` fired
   on the genuine control as well. It does not fail a document by
   itself (authenticity verdict: unclear, not fail), but the ELA-based
   altered-text signal false-positives on genuine phone photos and is
   a tuning candidate — it must never be promoted to a hard fail at
   its current precision.
4. Framing failed on all three equally (full-scene photos with
   backgrounds, not flow-framed captures) — not a discriminator.

Stage 4 is CLOSED: the fake is caught by the layer designed to catch
it, and the genuine control is not rejected.
