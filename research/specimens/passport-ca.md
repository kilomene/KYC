# Specimen dossier — Canada Passport (data page)

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source.
Official anchors: IRCC's new-design pages
(https://www.canada.ca/en/immigration-refugees-citizenship/services/canadian-passports/new-passport-design.html)
and the archived features page for the 2013 book
(https://www.canada.ca/en/immigration-refugees-citizenship/services/canadian-passports/about/passport-features.html);
MRZ structure from ICAO Doc 9303 Part 4.

## 1. Issuer, generations

- Issuer: **Passport Program, Immigration, Refugees and Citizenship Canada
  (IRCC)**. Ordinary passport, type P/PP (§3).
- **Current generation: the 2023 redesign** — unveiled 10 May 2023, "New
  design as of June 18, 2023" (CBSA Guide for Transporters), gradually
  introduced from June 2023 and "successfully deployed domestically and
  abroad as of September 1, 2024" (IRCC Minister Transition Binder, 2025).
- **Previous generation: the 2013 ePassport** — still valid until its
  printed expiry (10-year books run into ~2033), so both generations
  circulate and both must be templated.
- Data page material: **2023 = polycarbonate**, all personalisation
  **laser-engraved** ("a polycarbonate data page — a technology similar to
  Canada's driver's licences"; IRCC). **2013 = paper personal-information
  pages under a thin-film laminate with embossed holographic images**,
  photo and data **digitally printed and embedded in the page**.
- Chip: **2023 — embedded in a transparent window in the data page itself**
  (IRCC: the chip sits "in a transparent window on page one"); 2013 — in
  the back cover.
- Data page position: 2013 book — the personal-information pages are
  **pages 2 and 3**, data on page 2. 2023 book — the rigid polycarbonate
  leaf at the **front of the booklet**; its **exact printed page number is
  UNVERIFIED** from opened text sources — do not hard-code "page 2" for
  the 2023 series.

## 2. Photo

- Position: **left side of the data page** (ICAO Doc 9303 Part 4 Zone V is
  the left zone; portrait ≥2.0 mm from the left edge; consistent with the
  official specimen image. An explicit Canada-text statement of
  "photo-left" was not opened — treat as specimen/ICAO-supported).
- Style: 2023 — **laser-engraved** portrait. That it renders **greyscale/
  black-and-white is UNVERIFIED in official text** (consistent with
  engraving and with the specimen image, but not stated) — do not set a
  colour expectation for the 2023 main portrait from this dossier alone.
  2013 — digitally printed colour portrait, plus a **secondary photo that
  "appears in greyscale"** on the personal-information pages (official).
- IRCC lists **"multiple versions of your photo"** as a 2023 feature (§5).
- Signature: no scanned signature on the data page since May 2015 — adults
  sign page 3 in ink on receipt. Do not template a data-page signature.

## 3. Field layout and label wording (bilingual)

Field set and EN/FR label pairs (order per the 2023 data-page field list;
**exact x/y positions on the 2023 page are UNVERIFIED from opened text** —
only the specimen image carries them; settle zones from a specimen):

| Label EN | Label FR | Value |
|---|---|---|
| Type | Type | **PP** (2023 list; older lists give "P") |
| Issuing Country | Pays émetteur | CAN |
| Passport No. | Nº de passeport | §4 |
| Surname | Nom | Primary identifier |
| Given names | Prénoms | Secondary identifier(s) |
| Nationality | Nationalité | "Canadian/Canadienne" (both languages printed) |
| Date of birth | Date de naissance | VIZ bilingual-month rendering **UNVERIFIED** for 2023; MRZ = YYMMDD |
| Sex | Sexe | **F / M / X** ("X" printed in the VIZ since 11 Jul 2019) |
| Place of birth | Lieu de naissance | City + 3-letter country; province/state NOT printed; may be omitted on request |
| Date of issue | Date de délivrance | |
| Date of expiry | Date d'expiration | Relative order of expiry vs authority in the 2023 list is **low confidence** |
| Issuing Authority | Autorité de délivrance (2023 list shortens to "Authority / Autorité") | Issuing office |

The bilingual pairs are high-precision template anchors — key on the French
half too ("d'expiration", "délivrance", "naissance"), which survives partial
English-label damage. **Machine Readable Zone: the last two lines at the
bottom of the data page** (official, 2013; standard TD3 placement, 2023).

## 4. Document number — ⚠️ FORMAT CHANGED IN THE 2023 DESIGN

- **2013 and earlier: 2 letters + 6 digits = 8 characters** (`LLDDDDDD`).
- **2023 design: 1 letter + 6 digits + 2 letters = 9 characters**
  (`LDDDDDDLL`) — per the 2023 data-page list ("Passport No.: 1 letter, 6
  numbers, and 2 letters") and LegalClarity citing IRCC's new-passport
  features material.
- The 9-char number **exactly fills** the TD3 MRZ number field (positions
  1–9, no filler); an 8-char old number is `<`-padded to position 9 (ICAO
  Doc 9303-4).
- **Accept both patterns**, each bound to its generation: a 9-char number
  on a laminated 2013-style page (or an 8-char number in a polycarbonate
  page) is a generation-mismatch signal.
- **No check digit forms part of the number itself** in either format; the
  MRZ check digit over the number field is computed normally (§5).
- (An earlier draft's claim of letter-prefix series per generation, incl. a
  "J" start for 2023, came from a weaker source pass and is **withdrawn** —
  no opened official source in the full research supports prefix series.)

## 5. MRZ — ICAO TD3, 2 lines × 44 (OCR-B)

Confirmed from ICAO Doc 9303 Part 4 (8th ed.):

**Line 1:** pos 1–2 document code — `P` + type letter, giving **`PP`** for
Canada's ordinary passport (matches the VIZ Type) · pos 3–5 issuing state
**`CAN`** · pos 6–44 name: `SURNAME<<GIVEN<NAMES`, single `<` between
components, trailing fill, punctuation dropped/converted, truncated per
Doc 9303-3 if >39 chars.

**Line 2:**

| Positions | Content |
|---|---|
| 1–9 | Document number (§4; `<`-padded if 8 chars) |
| 10 | Check digit over 1–9 |
| 11–13 | Nationality `CAN` |
| 14–19 | Date of birth `YYMMDD` |
| 20 | Check digit over DOB |
| 21 | Sex `M` / `F` / `<` — **Canada prints X in the VIZ; Doc 9303 pairs VIZ X with MRZ `<`** |
| 22–27 | Expiry `YYMMDD` |
| 28 | Check digit over expiry |
| 29–42 | Personal number / optional data — **Canada's use of this field is UNVERIFIED from opened sources** (ICAO default is all `<` fillers if unused). (An earlier draft asserted the field is fillers because the SIN may not be printed; that legal claim was not confirmed in the full research — verify against a specimen MRZ before hard-coding either way) |
| 43 | Check digit over 29–42 (may be `0` or `<` if unused) |
| 44 | Composite check digit over 1–10, 14–20, 22–43 |

Check digits are mod-10 with 7-3-1 weighting — **fully validatable**, and
MRZ↔VIZ agreement (number, DOB, expiry) remains the strongest single
originality test on this document.

## 6. Security / originality features — photo visibility

**2023 design:**

| Feature | Visible in an ordinary photo? |
|---|---|
| **Kinegram over the main photo** — changes colour and appears to move with angle (IRCC) | Patch visible in a still; colour-shift/motion needs tilt or multi-angle capture |
| **See-through window with a secondary image of the holder** (custom window in the data page) | Yes |
| **Variable laser image** — the holder's photo **and date of birth** under a special lens, appearing/disappearing with angle | **Partially** — angle-dependent; expect it missing/inconsistent in a single flat photo. (This — not the kinegram proper — is the DOB-bearing feature; an earlier draft conflated them) |
| Multiple versions of the holder's photo on the page (IRCC feature list) | Yes |
| **Temperature-sensitive ink: a red maple leaf on the data page that disappears when heated by rubbing a finger** | The leaf is visible; the disappearing effect is **not** demonstrable in a photo |
| **Visible chip + antenna** embedded in the data page's transparent window | Yes |
| Laser-engraved text/photo in polycarbonate; **embossed/tactile characters** in a proprietary font (National Post launch reporting, secondary) | Relief may shadow in photos; tactility is touch-only |
| Magnetised colour-shifting ink (deer and snowflake shapes) | Colour-shift needs tilt; its location relative to the data page is **UNVERIFIED** |
| UV seasonal artwork on visa pages | **No** — UV only |
| **OVI on the 2023 data page: UNVERIFIED** (documented for 2013, §below) — do not carry the expectation forward without a specimen | — |

**2013 design** (official features page): laminate with **embossed
holographic images** (viewed by tilting in reflected light); **optically
variable ink** (colour changes under different lighting); **secondary photo
in greyscale**; **see-through register** — the letters "CAN" appear when
looking through the page (needs transmitted light; typically not visible in
a standard front-lit photo); digitally printed photo embedded in the page;
ePassport symbol printed on the page.

## 7. Validity rules

- Adults (16+): **5-year or 10-year** passport at the applicant's election
  (two official sources). Children (under 16): **5 years maximum**.
- Calibration rule: `expiry − issue ≈ 5 or 10 years` for an adult book
  (allow leap-day/issue edge cases); a span outside {~5y, ~10y} on an adult
  regular passport is a red flag. Always read the printed expiry.

## 8. Live-scan practicalities

- **Generation first, fields second:** polycarbonate+engraving (2023) vs
  laminate+print (2013) decides which number format (§4), photo style (§2)
  and feature set (§6) to expect.
- **MRZ is the anchor:** full 7-3-1 validation + MRZ↔VIZ on number/DOB/
  expiry; VIZ Sex **X** must map to MRZ **`<`**, not be read as a mismatch.
- The data page is one leaf of a booklet: expect curvature and gutter
  shadow; on the 2013 book the facing page 3 carries the bearer's ink
  signature — do not mistake the spread for two documents.
- Tilt captures unlock the angle features (kinegram behaviour, variable
  laser image with its DOB) — a flat single photo legitimately lacks them,
  so their absence in one still is not a forgery signal.
