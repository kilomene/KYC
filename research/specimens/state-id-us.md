# Specimen dossier — United States State Identification Card (Texas primary)

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source. Layout
boxes are relative fractions of the card face (x0, y0, x1, y1), origin top-left, and
are **[estimate]** calibration priors unless stated otherwise — the Texas ID card is
issued on the same DPS card platform as the Texas driver license (see `dl-us.md`),
so its geometry mirrors the DL layout minus the driving-privilege fields; the ID-card-
specific boxes were NOT separately measured from an official specimen image.

## 1. Issuer, official name, currency of design

- Issuer: **Texas Department of Public Safety (DPS)**.
- Official document name: **Texas Identification Card (ID card)**.
- It is part of the same redesign family as the DL: DPS began issuing redesigned
  **DL, ID and Election Identification Certificate (EIC)** cards on **18 Aug 2025**,
  covered together by DPS form **DL-73 "2025 MEET THE REDESIGNED TEXAS DRIVER LICENSE
  AND ID CARD"** (official form page:
  https://www.dps.texas.gov/InternetForms/home/Details/3300). The previous (2020)
  design remains valid until its printed expiry, so both circulate.
  (CultureMap, reporting DPS: https://culturemap.com/houston/news/city-life/new-texas-drivers-license-2025/;
  Security Magazine on the 2020 DL/ID redesign:
  https://www.securitymagazine.com/articles/91811-texas-increases-security-features-unveils-new-design-for-driver-licenseid-and-license-to-carry-cards)

## 2. Physical format

- **ID-1 card: 85.60 × 53.98 mm**, aspect ≈ 1.586 : 1 (ISO/IEC 7810 ID-1; AAMVA
  DL/ID Card Design Standard format).
- **Polycarbonate**, laser-engraved personalisation (same platform as the DL — DPS
  statements above cover DL and ID cards together).
- Orientation: **landscape** for 21+; **vertical (portrait) for under-21 holders**
  (secondary state tables: servingalcohol.com, wecard.org; DPS treats DL/ID designs
  as one family). Under-21 ID cards carry the same red "UNDER 21" / "UNDER 21 UNTIL
  \<date\>" treatment as the DL per those tables — ID-specific wording **UNVERIFIED**
  from a DPS source.

## 3. Front layout

Mirrors the Texas DL (see `dl-us.md` §3 for the zone table) with these differences:

- Header carries the identification-card title under "TEXAS". The exact header
  wording "Identification Card" is attested only by low-authority secondary/blog
  sources — treat as **lower confidence**, confirm from the owner's specimen.
- **No driving-privilege fields**: there is no class (9), endorsements (9a) or
  restrictions (12) to read, because the card confers no driving privilege. This is a
  structural inference from the card's purpose plus the AAMVA field model — it was
  NOT explicitly confirmed in an opened DPS source; phrase checks accordingly
  (absence of class fields is expected, not an anomaly signal).
- Present fields (AAMVA refs, same positions as DL **[estimate]**): portrait
  (0.03, 0.20, 0.31, 0.75); signature overlapping/below portrait; **4d number + 3 DOB
  on the first data line** (2025 design); 1 family name / 2 given names; 8 address;
  4a issue / 4b expiry (larger print, 2025); 15 sex and physical descriptors;
  5 DD audit number in small print along the bottom band.
- REAL ID star upper-right: **black, laser-engraved** (2025) / gold (2020).

Back of card **[estimate — no official ID-card back specimen was opened]**:
- **PDF417 barcode** (AAMVA data set as the DL, element DAQ = card number) and a
  **magnetic stripe** along the top edge, per secondary descriptions of the shared
  DPS card platform (e.g. LegalClarity:
  https://legalclarity.org/where-is-the-drivers-license-number-on-a-texas-license/).

## 4. Printed label wording

Same AAMVA numbered-label convention as the DL: 1 family name, 2 given names,
3 DOB (MM/DD/CCYY), 4a "Iss", 4b "Exp", 4d number, 5 "DD", 8 address, 15 sex, 16–19
physical descriptors. The number field's printed label on the ID card (vs the DL's
"DL" label) is **UNVERIFIED** from a primary source — do not hard-code "DL" for the
ID card. (AAMVA field references:
https://cdn.jsdelivr.net/npm/reid@0.0.1/standards-pdfs/AAMVA-V7-2012.pdf)

## 5. Document numbers and validation

- **ID card number (field 4d): 8 digits, numeric only** — the same format as the DL
  number. DPS's status service treats them identically: "Drivers License or ID Card #
  (8 digits number)": https://www.dps.texas.gov/DriverLicense/DLSearch/DLStatus.aspx
- **No check digit is published** for the Texas DL/ID number — validate length +
  numeric class only (any checksum rule is **UNVERIFIED**).
- **Audit number (field 5, "DD"): 20 digits** per secondary sources; changes on every
  reissue; exact front position **UNVERIFIED** (see dl-us.md §5).

## 6. Security / originality features — photo visibility

Same platform as the DL (dl-us.md §6 applies): laser-engraved greyscale portrait,
ghost image (faint, visible), colour-shifting seal (tilt-dependent), black/gold REAL
ID star. UV-only artwork and tactile features are **not photo-visible**; microprint
only at macro range. ID-card-specific UV artwork is **UNVERIFIED** from a DPS source.

## 7. Live-scan practicalities

- Identical to the DL: glossy polycarbonate → **high glare risk**; engraved low-
  contrast text; busy seal/flag artwork behind the data block on the 2025 design.
- The classifier must distinguish ID card from DL: the reliable discriminators are
  the header title and the **absence** of class/endorsement/restriction fields — do
  not classify on the number, which is format-identical to the DL number.
- Number appears once on the front; repeated in the back PDF417 (DAQ) for cross-check.
- Under-21 ID cards are vertical — rotation/framing must handle the portrait variant.

## 8. Official specimen material

- DPS form **DL-73** covers the ID card alongside the DL (official form page:
  https://www.dps.texas.gov/InternetForms/home/Details/3300). Direct PDF URL not
  captured (site rejected the research fetch). No ID-card-only official specimen
  image URL was found in the opened sources.
