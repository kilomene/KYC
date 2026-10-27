# Specimen dossier — New York State Non-Driver ID Card (NDID)

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source. The
NDID shares its card platform with the NY driver license and learner permit;
platform facts are stated for the platform.

> **Two corrections to common assumptions, established by DMV sources:**
> (1) the standard adult card is **LANDSCAPE** — portrait means under-21;
> (2) the window feature is officially a **CLEAR window** — the dark look in
> photos is the greyscale engraving inside it.

## 1. Issuer, official name, variants

- Issuer: **New York State Department of Motor Vehicles (DMV)**.
- Official name: **non-driver ID card (NDID)** (VTL §490; DMV:
  https://dmv.ny.gov/id-card/get-non-driver-id-card-ndid). Front title
  wording: "NEW YORK STATE / IDENTIFICATION CARD" (the AAMVA Zone I type
  indicator for an ID card is "IDENTIFICATION CARD"; exact NDID header
  typography is in DMV's sample images, not their text — **UNVERIFIED** at
  character level).
- Variants (§5): **Enhanced (ENDID)**, **REAL ID**, **Standard** — all three
  are issued as non-driver IDs, each in over-21 and under-21 forms.

## 2. Physical format

- Orientation: **LANDSCAPE for 21+; PORTRAIT (vertical) for under-21** —
  DMV's Sample Photo Documents are structured as separate "Over 21"
  (landscape) and "Under 21" samples, and DMV states under-21 cards are
  vertically oriented (the AAMVA national rule). **A portrait NY card is an
  under-21 issuance, not the standard adult format.**
  (https://dmv.ny.gov/node/4501)
- Material: **polycarbonate** (rigid; metallic sound when dropped).
- Personalisation: **laser-engraved** — data and photo are "burned into" the
  card; the portrait is **greyscale (black-and-white)** on a fine-line
  graphic background.
- Design generations: **2013** (first NY polycarbonate card) and **2022**
  (redesign effective **10 Mar 2022**; new/renewal/replacement transactions
  from that date get the new credential; older cards valid to expiry — both
  generations circulate).
  (https://dmv.ny.gov/news/dmv-release-redesigned-driver-license-non-driver-id-featuring-enhanced-security-features)

## 3. Front layout

Confirmed in aggregate from DMV samples, the federal REAL ID surface rule
(6 CFR 37.17) and AAMVA zones; per-field positions on the NDID face are in
DMV's sample *images* rather than text, so treat zone geometry as
**[estimate]** and settle it from a specimen:

- **Header (Zone I):** "NEW YORK STATE" + the document-type indicator
  "IDENTIFICATION CARD"; variant marking (§5) in the top area.
- **Portrait (Zone III): left side** of the face — laser-engraved greyscale.
- **ID number:** "located on the front **near the top**" (DMV) — §4.
- **Fields NY prints on the front** (per 6 CFR 37.17's required surface set,
  which NY follows): full legal name, date of birth, sex, ID number,
  photograph, address of principal residence, signature, issue date,
  expiration date. Height/eye-colour are standard AAMVA elements (DAU/DAY)
  in the barcode; their front print position/labels on the NDID are
  **UNVERIFIED** from opened DMV text.
- **Signature:** on the front — and in the 2013 design it is **raised/
  tactile** (§6).
- **Class "ID": UNVERIFIED** from an opened official source — do not
  hard-code a class field for this document.
- **"EXCELSIOR" banner on the NDID front: UNVERIFIED** (Excelsior is the
  state motto/seal text and is prominent on NY plates; no opened source
  puts a banner on this card). The **state seal** is confirmed as a front
  security element in the 2022 design (multiple laser imaging, §6); its
  exact position is **UNVERIFIED**.

**The window feature (key originality element):**
- **2013 generation (DMV/SLA brochure, official):** "a secondary photo, laser
  engraved into a **clear window with beveled edges in the lower, right hand
  corner**"; the holder's name runs as a "wave" of variable-size text that
  "continues through the clear secondary window"; the ghost image is
  **visible from the front and the back**.
- **2022 generation (DMV):** clear windows and the state seal are produced by
  **multiple laser imaging / etching** — "two images – the ID holder's photo
  and **birth month and year** — are engraved into the card so that an
  **irregularly-shaped image in the right center** of the card changes
  depending on the angle it is viewed at." Note: the 2022 window's second
  image is **birth month + year, not the full DOB**.
- **"Raised/tactile window": UNVERIFIED as stated.** Tactility on NY cards
  attaches to raised laser-engraved *text* (2013) and embossed text/images
  (2022) — §6 — not to the window itself.
- Photo doctrine: in photos the clear window often reads as a dark/black
  patch (the greyscale engraving inside it against a dark background) —
  **window presence + an engraved face inside it + angle-dependent flip
  (2022) is the originality signal**, not the window's colour.

## 4. Document numbers and validation

- **DMV ID Number / Client ID Number (CID): 9 digits, numeric only** —
  "the 9-digit 'ID' number printed in the upper portion of your driver
  license, learner permit, or non-driver ID… Enter the 9 digits only; do
  not enter spaces, hyphens, or other punctuation" (DMV). It identifies the
  **person** and does **not change** on renewal/replacement. Same number
  system across license/permit/NDID.
  - Printed grouping on the face (e.g. 3-3-3 spacing): **UNVERIFIED** from
    opened official text — do not validate spacing; strip whitespace and
    expect 9 digits.
  - **Check digit:** a NY regulation (15 NYCRR §32.4(f), insurance-ID
    context) references validation by "a check digit computation, as
    employed by the DMV developed software" — a check digit therefore
    exists in DMV's system, but **no algorithm is published in any opened
    source. Do not implement a guessed Luhn/mod-10 check.**
- **Document Number (per-card control number) — do not confuse with the
  CID:** **8 characters (all numeric) or 10 characters (alphanumeric,
  uppercase letters)** per DMV's transaction guidance. It is unique to the
  physical document and **changes on every renewal/replacement**. Location
  on post-29 Jan 2014 documents (i.e. on the **back**): REAL ID/Standard —
  "upper right side after Doc #"; Enhanced — "first line of text after
  IDUSA"; Under-21 — "upper left after Doc #". A claim that it prints
  *vertically* is **UNVERIFIED** in official sources.
  (https://dmv.ny.gov/transaction-message/information-about-transaction-entries)
- Longer alphanumeric strings also appear printed on specimen backs; their
  role is **not** identified by any opened DMV source — record them as
  production data, not as the Document Number, until a specimen decode says
  otherwise.

## 5. Variants and front markings

| Variant | Front marking (DMV wording) | Notes |
|---|---|---|
| **Standard** | **"NOT FOR FEDERAL PURPOSES"** (DMV comparison-table wording, all caps) | Applies to documents issued after 30 Oct 2017; not usable for domestic flights/federal facilities as of 7 May 2025. **Still a fully valid NY identity document** — record the variant, never treat the marking as a defect |
| **REAL ID** | A **star**: "a black circle with a white star centered within the circle" | Issuance began 30 Oct 2017; no extra fee |
| **Enhanced (ENDID)** | An **image of the U.S. flag** on the front | REAL ID-compliant **plus** land/sea return from Canada/Mexico/some Caribbean; +$30; US citizens only; carries an RFID chip (exposed in the 2022 redesign per DMV). The printed word "ENHANCED" on the face: **UNVERIFIED** — the flag is the documented discriminator |

## 6. Back layout

- **PDF417: present** — the mandatory AAMVA machine-readable technology; it
  encodes the front data as AAMVA elements (DAQ = CID, DCS/DAC name, DBB
  DOB, DBA expiry, DBD issue, DBC sex, DAU height, DAY eyes, DAG/DAI/DAJ/DAK
  address, DCF = document discriminator). NY's AAMVA Issuer Identification
  Number is **636001** (secondary AAMVA listings; the 636000 figure in blogs
  is Virginia's — treat the IIN as partially verified). Exact PDF417
  position on the NY back: **UNVERIFIED** from opened official text (it is
  in DMV's sample back images) — locate it from the specimen.
- **Document Number:** on the back, positions per §4.
- **Signature / address-change boxes (2013):** confirmed — "matte finish for
  the signature and address change boxes on the back of the card" (DMV/SLA
  brochure). Persistence in identical form on the 2022 back: **UNVERIFIED**.
- **Donor:** enrolment prints a **heart symbol + "Organ Donor" on the
  FRONT** (Donate Life NY: "Signing the back of your license does not
  enroll you"); VTL §504 likewise provides for "ORGAN DONOR" on the front.
  There is **no** confirmed dedicated donor line on the back of the current
  card — do not template one.
- **Magnetic stripe on the current polycarbonate card: UNVERIFIED** — no
  opened DMV source states one; do not calibrate expecting it.
- **A separate small 1D barcode: UNVERIFIED** from official sources (the
  claim circulates on fake-ID vendor sites only — not citable).
- **"dmv.ny.gov" printed on the back: UNVERIFIED** from opened official
  text.

## 7. Security / originality features — photo visibility

**2013 generation (DMV/SLA brochure):**

| Feature | Visible in an ordinary photo? |
|---|---|
| Laser-engraved greyscale portrait on fine-line background | Yes |
| **Clear beveled window (lower right) with laser-engraved secondary photo**, visible front and back; name "wave" running through it | Yes — window + face inside it |
| **Tactile laser engraving:** raised lettering on the **ID number, birth date, expiration date, and signature** | Touch-only (may shadow at raking light) |
| Rainbow printing, anti-copy inks, fine-line colour graphics | Yes (print conformance) |
| UV graphics over the front (NY state map, starbursts, fine lines in the window) | **No** — UV light required |

**2022 generation (DMV):** embossed text and images (touch-detectable);
**multiple laser imaging** — clear windows + state seal whose engraved image
**flips with viewing angle (photo ↔ birth month and year)** at right center;
Enhanced: embedded chip now exposed. DMV expressly does not publish its
other security features.

## 8. Live-scan practicalities

- **Orientation classifies age band:** landscape = 21+, portrait = under-21.
  Never force a landscape template onto a portrait NY card, and never read
  portrait orientation as a forgery sign.
- **Greyscale portrait** — face detection/matching must not expect colour;
  the window ghost is a second, lower-contrast face: use it as a
  presence/consistency signal, not the primary match.
- **Two numbers, two jobs:** CID (9 digits, person-stable) is the identity
  key; Document Number (8 numeric / 10 alphanumeric, back, changes per card)
  is the document-instance key — ideal for duplicate-document detection.
- **Window check:** clear window present (either generation), engraved face
  inside it, readable from both sides; on 2022 cards ask for a slight tilt —
  the right-center image should flip between the photo and birth month+year.
- No mag stripe, 1D barcode, or back donor line should be required (§6).
