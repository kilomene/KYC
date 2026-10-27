# Specimen dossier — United States Driver License (Texas primary)

Research date: 2026-10-27. Sources are official/issuer pages and reputable secondary
sources, each cited inline. **No real person's document was used.** Items marked
**UNVERIFIED** were not confirmed in an opened source and must not be treated as fact.
Layout boxes are given as relative fractions of the card face (x0, y0, x1, y1),
origin top-left. Boxes marked **[estimate]** are calibration priors derived from the
AAMVA zone system and published specimen descriptions — they are NOT measured off an
official specimen image and must be replaced by measurements from the owner's own card.

## 1. Issuer, official name, currency of design

- Issuer: **Texas Department of Public Safety (DPS)**, Driver License Division.
- Official document name: **Texas Driver License (DL)**.
- Two designs will be met in the field:
  - **2020 design** — issued from Feb 2020; polycarbonate, laser engraving, gold REAL ID
    star in the upper-right corner. Previously issued cards stay valid until the expiry
    printed on them, so this design remains in circulation.
    (Security Magazine, 2020-02-28, reporting DPS:
    https://www.securitymagazine.com/articles/91811-texas-increases-security-features-unveils-new-design-for-driver-licenseid-and-license-to-carry-cards)
  - **2025 design** — DPS began issuing redesigned DL / ID / EIC cards on **18 Aug 2025**.
    DPS form **DL-73 "2025 MEET THE REDESIGNED TEXAS DRIVER LICENSE AND ID CARD"** is the
    official specimen brochure (official form page:
    https://www.dps.texas.gov/InternetForms/home/Details/3300 — DPS's site rejected a
    direct text fetch of this page during research; the form title/number are as indexed
    on dps.texas.gov). Changes vs 2020: REAL ID star is now **black and laser-engraved**,
    still upper-right; **date of birth moved up to share the first data line with the DL
    number**; issue/expiry dates printed larger; organ-donor symbol moved; background art
    centres on the Texas State Seal with horses and flowing flag imagery.
    (CultureMap, reporting the DPS announcement:
    https://culturemap.com/houston/news/city-life/new-texas-drivers-license-2025/)

## 2. Physical format

- **ID-1 card: 85.60 × 53.98 mm**, aspect ratio ≈ 1.586 : 1 (ISO/IEC 7810 ID-1; the
  AAMVA DL/ID Card Design Standard conforms US DL/ID cards to this format).
- Orientation: **landscape** for holders 21+. Holders **under 21 receive a VERTICAL
  (portrait) card**, with red "UNDER 21" text near the top and an "UNDER 21 UNTIL
  \<date\>" line above the name (state-comparison tables:
  https://www.servingalcohol.com and https://www.wecard.org — secondary sources).
- Material: **polycarbonate** (both 2020 and 2025 designs; DPS via Security Magazine
  and CultureMap, above). Laser-engraved personalisation.

## 3. Front layout (2025 design unless noted)

Texas cards print the **AAMVA field-number references** beside the data (the small
numbers 1, 2, 3, 4a, 4b, 4d, 5, 8, 9, 15… are part of the printed card, not OCR noise).
Field numbering per the AAMVA DL/ID Card Design Standard (2012 CDS, Zone II data block
/ Zone III portrait):
https://cdn.jsdelivr.net/npm/reid@0.0.1/standards-pdfs/AAMVA-V7-2012.pdf

| Zone | Box (fractions) | Contents |
|---|---|---|
| Header band | (0.00, 0.00, 1.00, 0.18) **[estimate]** | "TEXAS" + credential title; REAL ID star upper-right — black, laser-engraved (2025) / gold (2020) |
| REAL ID star | (0.86, 0.03, 0.97, 0.17) **[estimate]** | Black star (2025 design) |
| Portrait (Zone III) | (0.03, 0.20, 0.31, 0.75) **[estimate]** | Laser-engraved portrait photograph |
| Signature | (0.03, 0.72, 0.31, 0.85) **[estimate]** | Holder signature, overlapping/below portrait (AAMVA places it in Zone II or overlapping the portrait in Zone III) |
| Data block (Zone II) | (0.34, 0.18, 0.97, 0.97) **[estimate]** | All text fields below |
| **4d DL number + 3 DOB (first line, 2025)** | (0.34, 0.20, 0.97, 0.32) **[estimate]** | 2025 design puts number and DOB on the first data line (DPS via CultureMap). On the 2020 design DOB sits lower in the block |
| 1 Family name / 2 Given names | (0.34, 0.32, 0.97, 0.48) **[estimate]** | Printed as separate numbered fields |
| 8 Address | (0.34, 0.48, 0.97, 0.62) **[estimate]** | Mailing/residence address block |
| 4a Issue / 4b Expiry | (0.34, 0.62, 0.97, 0.78) **[estimate]** | Printed **larger** on the 2025 design (DPS via CultureMap) |
| 9 Class / 9a Endorsements / 12 Restrictions; 15 Sex / 16 Height / 17 Weight / 18 Eyes / 19 Hair | (0.34, 0.78, 0.97, 0.90) **[estimate]** | Driving-privilege and physical-descriptor fields |
| **5 DD (audit number)** | (0.34, 0.88, 0.97, 0.97) **[estimate]** | Small print along the bottom band of the data block per secondary descriptions; exact position **UNVERIFIED** from a DPS source (see §5) |
| Ghost image | lower-right area of the data block **[estimate]** | Smaller, faint duplicate portrait (see §6) |

Back of card:
- **PDF417 barcode** (AAMVA-encoded: name, DOB, address, DL number, DD, expiry,
  physical description; barcode element **DAQ = DL number**) — back side.
  (AAMVA element IDs summarised at https://www.docsumo.com/blog/drivers-license-ocr)
- **Magnetic stripe** along the top edge of the back (secondary sources, e.g.
  LegalClarity's Texas DL guide: https://legalclarity.org/where-is-the-drivers-license-number-on-a-texas-license/).
- Explanatory/regulatory text. **[estimate — no official back specimen was opened]**

## 4. Printed label wording

AAMVA-numbered labels as printed on Texas cards (per AAMVA CDS field references):

| Ref | Field | Label/notes |
|---|---|---|
| 1 | Family name | numeric ref "1" |
| 2 | Given names | numeric ref "2" |
| 3 | Date of birth | numeric ref "3"; US format **MM/DD/CCYY** |
| 4a | Date of issue | label convention "Iss" |
| 4b | Date of expiry | label convention "Exp" |
| 4d | Customer identifier (= DL number) | the DL number itself carries the printed label **"DL"** (LegalClarity, above) |
| 5 | Document discriminator (audit number) | label **"DD"** |
| 8 | Address | numeric ref "8" |
| 9 / 9a / 12 | Class / Endorsements / Restrictions | numeric refs |
| 15–19 | Sex, Height, Weight, Eyes, Hair | numeric refs |

## 5. Document numbers and validation

- **DL number (field 4d): 8 digits, numeric only**, no spaces or grouping as printed.
  DPS's own DL-status service asks for "Drivers License or ID Card # (8 digits number)":
  https://www.dps.texas.gov/DriverLicense/DLSearch/DLStatus.aspx
  The number does not change on reissue; it is also the PDF417 DAQ element.
  **No check digit is published by DPS or AAMVA for the Texas DL number** — treat any
  checksum assumption as **UNVERIFIED**; validate length + numeric class only.
- **Audit number (field 5, "DD", document discriminator): 20 digits** per multiple
  secondary sources (LegalClarity and AAMVA-format guides). It **changes with every
  reissued card** (the DL number does not). Exact print position on the 2025 front is
  **UNVERIFIED** — secondary sources disagree (bottom band vs. near the photo), and one
  blog's claimed DOB-derived internal structure is unreliable and is NOT asserted here.
  No check digit published.

## 6. Security / originality features — photo visibility

| Feature | Source | Visible in an ordinary photo? |
|---|---|---|
| Polycarbonate body, personalisation fused into the card layers | DPS via Security Magazine (2020); CultureMap (2025) | Partially — edges/surface look; the "cannot delaminate" property itself is tactile, not photographic |
| Laser engraving (portrait, data, black REAL ID star on 2025) | DPS via CultureMap / Security Magazine | Yes — engraved portrait is greyscale/monochrome, visibly different from inkjet colour printing |
| Ghost image (secondary, faint duplicate portrait) | Sumsub US fake-ID guide: https://sumsub.com/blog/fake-id-in-us/ (secondary) | Yes, faintly — low contrast by design; needs good resolution/angle |
| Optically variable / colour-shifting seal | Sumsub (secondary) | Only when tilted — a single still photo may not show the shift; video/tilt sequence can |
| Tactile (raised) date of birth | Sumsub (secondary) | **No** — tactile only |
| UV-ink features (reported: state outline / DOB in UV) | idone.ph state guide (low-authority secondary): https://idone.ph/news/us-driver-license-by-state-2026-complete-guide-50-state-id-designs/ | **No** — UV-only, not visible in an ordinary photo. Exact UV artwork for the TX 2025 card **UNVERIFIED** from DPS |
| Microprint | Generic AAMVA-era practice; not confirmed for TX 2025 in an opened DPS source | Only at macro/zoom range; **UNVERIFIED** for this design |

Camera-based authenticity can therefore check: layout/typography conformance, laser-
engraved monochrome portrait, ghost-image presence, colour-shift behaviour across a
tilt sequence, PDF417 payload cross-check against the printed fields. It cannot check:
UV artwork, tactile features, chip (none on TX DL), or polycarbonate "ping"/layer tests.

## 7. Live-scan practicalities

- **Gloss/glare: HIGH risk.** Polycarbonate is glossy; laser-engraved zones are matte
  but the card face reflects strongly under point light. Expect specular blow-out over
  the portrait and data block unless angle/lighting is managed.
- **Background complexity:** the 2025 design's artwork (State Seal, horses, flag
  imagery) sits behind/around the data block — moderate OCR interference; the 2020
  design's guilloche-style background is finer but still busy.
- **Repetition of the number:** the DL number is printed **once** on the front (not
  vertical on current Texas designs) and repeated **in the back PDF417 (DAQ)** — a
  front/back cross-check is available if the flow scans both sides. The DD audit number
  is front-only small print.
- **Under-21 cards are portrait-orientation** — the framing/rotation logic must accept
  a vertical card whose data block is rotated 90° relative to the 21+ layout.
- Engraved text has lower contrast than ink; the greyscale portrait will not match a
  colour selfie pipeline tuned for printed photos — face-match thresholds should be
  calibrated on engraved portraits specifically.

## 8. Official specimen material

- DPS form **DL-73** (2025 redesign brochure with card imagery), official form page:
  https://www.dps.texas.gov/InternetForms/home/Details/3300 (dps.texas.gov).
  Direct PDF URL not captured (site rejected the fetch) — retrieve the PDF link from
  that page in a browser. No other official specimen image URL was captured.

## 9. Where other states differ structurally

- **Number format is jurisdiction-assigned** (AAMVA 4d): e.g. Tennessee uses 9 digits
  (secondary tables); other states mix letters and digits. Length/charset rules must be
  per-state, never assumed from Texas.
- **Under-21 treatment varies:** most states switch to a vertical card; some (e.g.
  Tennessee) keep a horizontal card with a red "UNDER 21 UNTIL" bar (state tables at
  servingalcohol.com / wecard.org — secondary).
- Field numbering follows the AAMVA standard on most modern cards, but header wording,
  portrait side, ghost-image placement, and extra features (e.g. California's
  transparent window, laser-perforated images in some states) are state-specific.
  AAMVA CDS is the common frame, not a guarantee of identical geometry.
