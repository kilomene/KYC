# Specimen dossier — Nigeria INEC Permanent Voter's Card (PVC)

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source. Layout
boxes are relative fractions of the card face (x0, y0, x1, y1), origin top-left,
and are **[estimate]** calibration priors derived from INEC's own published feature
diagram as described by Dubawa — NOT measured pixel-by-pixel from the diagram.

## 1. Issuer, official name

- Issuer: **Independent National Electoral Commission (INEC)**, Nigeria.
- Official document name: **Permanent Voter's Card (PVC)**.
- The authoritative layout reference is **INEC's own 14-feature PVC diagram**,
  reproduced and broken down feature-by-feature by the fact-checker Dubawa
  (published 2023-01-23):
  https://dubawa.org/all-you-need-to-know-about-your-pvc-features-and-what-they-represent/?amp=1
  The annotated diagram image itself (credited to INEC) is hosted with that article:
  https://lh6.googleusercontent.com/_puc0NNv1NjyuJ8bqcsmMshbPF6g0UbkOMVPeXcDMWXElFbGByK3NZYNubt_06tBP0fxxM3Fu0q4FQtMlu_8fFIRXdww_6qBpFjklI4eIg2WDvxsLTP1nRvSmulP6D1pCpX0JL-xI6sTgM85fAdgLmxvJdR1C4k3rxkwDIwDXHbZgeKyZfP2ryExTi0INg
- New variant to expect: a **downloadable/printable PVC** for lost or defaced cards
  under the Electoral Act 2026, piloting at the Osun governorship election (Aug 2026)
  — conditions: prior collection of the original + a formal complaint ≥90 days before
  the election (TechNext: https://technext24.com/news/inec-introduces-downloadable-pvcs/).
  A home-printed variant will lack the chip/hologram/lamination of the issued card.

## 2. Physical format

- **Dimensions: UNVERIFIED.** No opened source (INEC or otherwise) states the card's
  size in millimetres. It is a plastic chip card of standard wallet format in common
  parlance, but do NOT assert ID-1 (85.60 × 53.98 mm) as sourced fact — settle the
  aspect ratio from the owner's card during calibration.
- Orientation: **landscape**.
- Construction (INEC factsheet components, via EPA's reproduction of INEC material:
  https://epa.com.ng/2022/01/24/the-permanency-of-nigerias-permanent-voter-card/):
  base substrate, security printing, personalisation, **lamination**, **chip
  embedding**; designed average lifespan **10 years**.

## 3. Front layout (per INEC's 14-feature diagram, via Dubawa)

| # (INEC) | Zone | Box (fractions) | Contents |
|---|---|---|---|
| — | Header band | (0.00, 0.00, 1.00, 0.18) **[estimate]** | INEC identification / card title band |
| 3 | **VIN** | (0.03, 0.20, 0.62, 0.30) **[estimate]** | Voter Identification Number — runs **parallel to the PU code** across the top band, left/centre |
| 1 | **Polling Unit (PU) code** | (0.63, 0.20, 0.97, 0.30) **[estimate]** | **Top right** of the front |
| 4 | Delimitation | (0.03, 0.30, 0.62, 0.40) **[estimate]** | State, LGA and Ward names, just below the VIN |
| 5 | **Voter's name** | (0.03, 0.40, 0.62, 0.52) **[estimate]** | Below the VIN/delimitation — **surname, first name, middle name** order |
| 2 | **Voter's image (portrait)** | (0.66, 0.30, 0.97, 0.78) **[estimate]** | **Below the PU code**, right side |
| 6 | **Date of birth** | (0.03, 0.52, 0.40, 0.62) **[estimate]** | Just below the name — day, month, year |
| 7 | **Gender** | (0.40, 0.52, 0.62, 0.62) **[estimate]** | **Parallel to the DOB** (same band, right of it) |
| 8 | Occupation | (0.03, 0.62, 0.62, 0.72) **[estimate]** | Under the DOB |
| 9 | Address | (0.03, 0.72, 0.62, 0.92) **[estimate]** | Under the occupation |
| 14 | Fingerprints indicator | (0.66, 0.78, 0.97, 0.92) **[estimate]** | **Underneath the voter image** on the front |

Back of card (per the same INEC diagram):

| # (INEC) | Zone | Contents |
|---|---|---|
| 10 | **Barcode** | At the **top of the back** |
| 11 | **Card serial number** | Printed **parallel to the batch number** |
| 12 | Name + VIN + registration date | Surname / first name, the **VIN repeated**, and the **date of registration** |
| 13 | **Batch number** | A letter before the state number, in a PU-code-like series, plus a trailing two digits |

There is **no signature field and no MRZ** in INEC's feature list. There is **no
expiry date** (see §5).

## 4. Printed label wording

INEC's diagram labels the data by function rather than by long printed captions;
the field identifiers used on/around the card are: **"VIN"** for the voter number,
the **PU code** (polling-unit code), **delimitation** (state/LGA/ward), name,
date of birth, gender, occupation, address. Exact caption typography beside each
field on the physical card is **UNVERIFIED** beyond the VIN label — calibrate label
anchors from the owner's specimen rather than assuming US-style "DOB"/"EXP" labels.
There is no "EXP" label because there is no expiry (§5).

## 5. Document numbers and validation

- **VIN (Voter Identification Number)** — the primary key.
  - Length/charset: **sources conflict.** The weight of the better sources is
    **19 characters, alphanumeric** (letters + numbers): Roundcheck's fact-check,
    quoting the card/TVC, says the VIN "is a combination of numbers and letters
    which makes up 19 in total"
    (https://roundcheck.com.ng/2023/01/28/claim-that-vin-can-be-used-to-vote-in-nigerias-election-is-incorrect/);
    awajis.com likewise describes a "19-digit number printed on the front"
    (https://awajis.com/inec-voters-status-verification/). One BVAS technical
    document illustrates it as 19 numeric characters ("VIN: 1234567890123456789"),
    and one low-quality source claims a "10-digit alphanumeric" VIN — that claim is
    **not** corroborated and should be disregarded unless the specimen says otherwise.
  - Verification keying: INEC's voter-verification service (cvr.inecnigeria.org/vvs)
    accepts the **full VIN or its last 10 digits** (Tribune Online, reporting INEC's
    verification service). Older SMS check flows used shorter suffixes (last 5 or
    last 7 digits per various guides) — suffix lengths in guides conflict; the
    last-10 figure is the one tied to the current VVS by a national newspaper.
  - **No check digit is published by INEC.** Validate as: strip spaces → expect 19
    alphanumeric characters; treat any shorter/longer read as suspect, not auto-fail,
    until the owner's specimen settles the format. **Exact VIN format remains
    partially UNVERIFIED from INEC primary documentation.**
  - Position conflict to note: INEC's diagram (via Dubawa) places the VIN on the
    **front**, parallel to the PU code, and **repeated on the back** (feature 12);
    awajis places the "VIN" line "below your photograph", which conflicts with the
    diagram. Trust the diagram; the back repetition is a useful cross-check channel.
- **PU code: 9 digits**, structure **2 (state) + 2 (LGA) + 2 (ward) + 3 (polling
  unit)**; state codes run Abia = 01 … FCT = 37 (Dubawa/INEC diagram). Note: INEC's
  own polling-units page says the "8-digit or 9-digit Polling Unit code printed on
  the front of the voter's card" (http://inecnigeria.org/polling-units/) — record
  both: 9-digit is the diagram's structure; 8-digit forms exist in INEC's wording
  (older/zero-suppressed codes).
- **Card serial number** and **batch number** (back): formats as described in §3;
  no validation rule published.

## 6. Security / originality features — photo visibility

Per INEC (Chairman Jega's enumeration, via the INEC factsheet reproduced by EPA):
**embedded chip, printed voter details, photograph, barcode, micro-text, hologram,
fingerprints** (biometrics held in the chip).

| Feature | Visible in an ordinary photo? |
|---|---|
| Hologram | Only as an angle-dependent sheen — a single still may catch it partially; tilt/video shows it properly |
| Micro-text | Only at macro/zoom range |
| Barcode (back) | Yes — machine-readable by the camera, a genuine cross-check channel |
| Embedded chip (fingerprints + facial image, read by card reader / BVAS) | **No** — electronic only; a camera cannot read it. Chip's visible contact plate position on the front is **UNVERIFIED** from an opened source |
| Fingerprints indicator (front, under the photo) | Yes as a printed indicator graphic — it is not itself biometric evidence |
| Lamination / substrate | Surface sheen only |

Colour/design: the card is widely described in Nigerian press and photos as a
**green-and-white** card (low-authority blog phrasing: "Green and white card with
your photo") — treat the colourway as well-attested visually but not from an INEC
specification document.

**No expiry — by design.** INEC has stated repeatedly that the PVC carries no expiry
date and does not expire: "A PVC does not have an expiry date on it, therefore, it
does not expire. As long as the security chip on it is not damaged, it remains
valid" (INEC spokesman Rotimi Oyekanmi, via TheCable's fact-check:
https://www.thecable.ng/fact-check-tinubu-says-current-pvcs-have-expired-is-this-true/).
**The scanner must NOT expect or require an expiry field for this type.**

## 7. Live-scan practicalities

- **Material/glare:** laminated plastic — moderate gloss; lamination seams/edge
  glare possible, less hard-glossy than polycarbonate.
- **Background behind text:** comparatively plain light background behind the data
  fields vs. the NIN slip's watermark-heavy paper (researcher observation from the
  published diagram/photos, not an INEC claim) — OCR conditions are the friendliest
  of the four types here, but the printed portrait is often low-contrast.
- **Number repetition:** the VIN appears on the **front AND the back** (back feature
  12, alongside the registration date) — two independent reads of the key number are
  available. The PU code is front-only.
- **No expiry, no signature, no MRZ** — do not let generic ID templates hunt for them.
- Expect the **downloadable PVC variant** (§1) in the future: paper printout, no
  chip/hologram — originality checks must degrade honestly for it rather than
  hard-failing on missing card security features.
