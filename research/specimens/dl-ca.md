# Specimen dossier — California Driver License & California Identification Card

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source. The
DL and the ID card are **different documents on one card family** — §5 lists
what differs.

> **Headline calibration warning:** there are **three co-circulating
> generations** (2010, 2018, and a **new design issued from 30 Sep / 1 Oct
> 2025**). The 2025 card changes the artwork, the label system, and the back
> (no mag stripe, two barcodes). Do not calibrate on the 2018 card alone.

## 1. Issuer, documents, design generations

- Issuer: **California Department of Motor Vehicles (DMV)**. Documents:
  **Driver License (DL)** and **Identification Card (ID)**.
- **2010 generation** — the last full security redesign before 2025 (DMV:
  "The last time the card was made available with a new design and security
  features was in 2010. The look of the cards was changed in 2018 with the
  implementation of REAL ID.").
- **2018 generation** — issued from **22 Jan 2018** with REAL ID rollout.
  Artwork: **golden bear with a white star** upper-right (REAL ID version,
  §4); a **pale colour image of a 49er miner and landscape on the right
  side**; **golden poppies lower-left under the photo, sailboats to their
  right**; a large state-of-California outline through the middle
  background; new header font ("California script" styling: **UNVERIFIED** —
  sources say only "new font").
- **2025 generation (current)** — DMV Law Enforcement Memo 25-15 (30 Sep
  2025); public rollout 1 Oct 2025. Changes: artwork becomes **redwoods,
  poppies and coastline** (miner/sailboats/state outline replaced); **the
  magnetic stripe is removed**; the back carries **two barcodes, one with a
  digital security signature**; personal data is **laser-engraved**; fields
  use **AAMVA-numbered labels** (§2). All previously issued cards remain
  valid to their printed expiry (DMV 2025 release:
  https://www.dmv.ca.gov/portal/news-and-media/dmv-to-release-new-california-drivers-license-and-identification-card-design-with-advanced-security-features/;
  memo via Kern County Sheriff:
  https://kernsheriff.org/documents/policies/Support-Services-Bureau/Training-Bulletins/2025/25-60-Department-of-Motor-Vehicles-Memo-25-15.pdf).

## 2. Physical format

- Landscape for 21+; **vertical for under-21 — for BOTH DL and ID** (the ID
  card does not differ on orientation). Retained in the 2025 generation.
- Vertical-card specifics (We Card): ghost image at the **lower left**;
  **white "AGE 21 IN (YYYY)" in a red bar**; under-18 adds **white
  "PROVISIONAL UNTIL AGE 18 IN (YYYY)" in a blue bar**.
- Material: **UNVERIFIED** — DMV/RBS sources describe only a "printed,
  plastic, wallet-sized card". Polycarbonate/Teslin claims appear only on
  low-quality and fake-ID vendor pages. **Do not calibrate material, bend or
  sound tests for this card.**

## 3. Front layout

Layout facts below are from the CA ABC Responsible Beverage Service (RBS)
training guide's card descriptions and the 2025 specimen (pattern text only,
via the CA Attorney General's copy of the DMV release).

- **Primary photo: LEFT** (large, colour). **Signature: underneath the
  photograph, bottom-left.**
- **Ghost / secondary photo:** smaller black-and-white image at the
  **bottom-right** on the horizontal adult card (RBS). Position **varies by
  generation and orientation**: lower-left on vertical minor cards (We
  Card); "near the main photograph" in 2025 descriptions; the 2025 redesign
  notes "new placement of the ghost image and portrait" (IDScan). **Accept
  all documented positions; never gate on one ghost position.**
- **Red printing (confirmed): DOB in red; card number, issue and expiry
  dates in red** (RBS groups them: "Identifiers: card number, issue & expiry
  date (in red)"). The DL number being *independently* "big and red" is
  **partially verified** — calibrate red-channel detection on DOB + EXP
  first.
- **Label sets — two generations, accept both:**
  - 2018-style face: **DL, EXP, CLASS, END, LN, FN, DOB, RSTR, SEX, HAIR,
    EYES, HGT, WGT, DD, ISS** (label set confirmed via a patent describing
    the CA DL's fixed structure + decoder sources; LN = surname line, FN =
    given-names line).
  - **2025 numbered face (AAMVA numbering):** header "CALIFORNIA / DRIVER
    LICENSE"; **DLN** + number; **4b EXP**; **3 DOB**; **1** surname line,
    **2** given-names line; **8** address; **9 CLASS**; **9a END**; **12
    REST**; **15 SEX, 16 HGT, 17 WGT, 18 EYES, 19 HAIR**. Note the
    conflicts to handle in code: **RSTR (old) vs REST (2025)**, and **DL
    (old) vs DLN / field 4d (2025)**.
  - Name layout 2025: last name on its own line, first + middle names on
    the line below; data laser-engraved rather than ink-printed
    (LegalClarity's account of the new card).
- Zone fractions: **[estimate]** only — DMV publishes no coordinate spec;
  derive zones from the label anchors above and settle from specimens.

## 4. Document numbers and validation

- **DL/ID number: 1 letter + 7 digits** (`LDDDDDDD`) — confirmed across
  multiple sources ("labeled 'DL' followed by one letter and seven
  digits"; pattern example `A1234567`). **The same format and series serve
  both DL and ID cards.** The number stays the same across renewals and
  replacements. **No published check digit** — validate by regex only.
- **DD (Document Discriminator, the audit number):** a unique serial for
  that specific piece of plastic; **changes on every renewal/replacement**
  (it is also encoded in the back PDF417 as AAMVA element **DCF** — §6).
  Position: bottom-front area, near the printed **ISS** date (older face:
  below RSTR, beside ISS).
  - **Exact DD format: UNVERIFIED.** The hypothesised segmentation
    (issue-date prefix + office code + sequence) was **not found in any
    opened official DMV/AAMVA source**; a secondary decoder describes the DD
    only as "a long alphanumeric serial number" (~13–14 chars — itself
    secondary-sourced). The printed ISS date next to it is a known confuser.
    **Calibration rule: treat the DD as an opaque string; validate ISS as
    its own date field; cross-check DD against barcode DCF. Do not parse a
    date out of the DD, and do not require DD↔ISS agreement** (that rule
    appeared in an earlier draft of this dossier from a weaker source and
    is withdrawn).
  - DD position on the 2025 numbered face: **UNVERIFIED** (the specimen
    text extraction did not legibly show a DD/ISS line).

## 5. REAL ID vs "FEDERAL LIMITS APPLY"; ID card vs DL

- REAL ID marking: **a golden bear with a WHITE star** in the **upper-right
  corner** (DMV: the card "is marked with a golden bear and star"; the 2018
  description specifies the *white* star cut into the bear signifies REAL
  ID compliance).
- Noncompliant marking: the text **"FEDERAL LIMITS APPLY"** in the **front
  top-right corner** (RBS). Meaning (DMV): the card cannot be used to board
  domestic flights or enter secure federal facilities after 7 May 2025 —
  **but it remains a fully valid California licence/ID**. The two markings
  are mutually exclusive. Scanner doctrine: record the variant; never
  downgrade a card for carrying FEDERAL LIMITS APPLY.

| Aspect | Driver License | Identification Card |
|---|---|---|
| Title | "DRIVER LICENSE" | "IDENTIFICATION CARD" |
| Number label | "DL" (2025: DLN) | "ID" |
| Number format | 1 letter + 7 digits | **Identical** — never distinguish by number |
| Driving fields | CLASS / END / RSTR (REST) present | No driving privilege; absence of CLASS/END/RSTR on an ID is expected — the inference is logical, **not directly stated in an opened source**, so never fail an ID for missing them nor require them |
| Senior variant | n/a | **62+: no fee**, and the card bears a **"Senior Citizen" notation / a printed "Senior Identification Card" banner** on the front (Vehicle Code §13000(b); DMV form DL 410 ID). Senior **validity is CONFLICTED in sources (8 vs 10 years)** and the current DMV ID-cards page was not opened — **UNVERIFIED; do not hard-code either figure** |
| Age minimum | — | None ("DMV issues ID cards to persons of any age") |

## 6. Back layout and the PDF417

**By generation — calibrate both:**

| | Pre-2025 (2010/2018) | 2025 generation |
|---|---|---|
| Magnetic stripe | **Present** | **REMOVED** (DMV, explicit) |
| Barcodes | One 2D barcode ("replicates and verifies information on the front") | **Two barcodes**, one carrying a **digital security signature** |
| Other | — | Back text notes the card does not establish eligibility for firearms purchases (Memo 25-15); smaller signature on the back; redwoods/poppies/coastline background; **laser perforations: outlines of the state and a California brown bear, visible when a flashlight is pressed against the back** (RBS) |

- Main 2D barcode symbology: **PDF417** (the AAMVA symbology; IDScan calls
  the CA 2025 code a "digitally signed PDF417 barcode"). The **second 2025
  barcode's symbology is UNVERIFIED for CA** — under the AAMVA standard the
  inventory-control element DCK is carried in a 1D barcode (per a state
  AAMVA calibration sheet), which is a plausible model, not a CA
  confirmation. No QR/DataMatrix as the primary back code was confirmed
  anywhere — do not expect one.
- **PDF417 payload (AAMVA standard element set):** DCA class · DCB
  restrictions · DCD endorsements · **DBA** expiry · **DCS** family name ·
  **DAC** given name · **DAD** middle names · **DBD** issue date · **DBB**
  DOB · **DBC** sex · **DAY** eye colour · **DAU** height · **DAG/DAI/DAJ/
  DAK** address/city/state/ZIP · **DAQ** licence number · **DCF** document
  discriminator (= printed DD) · DCG country · DDE/DDF/DDG truncation
  flags · plus DAW weight, DAZ hair, **DDA compliance type (F = REAL ID
  compliant, N = non-compliant)** — the barcode-level expression of §5 —
  DDB card revision date, DDD limited-duration, DDI/DDJ under-19/21-until,
  DDK organ donor, DDL veteran, DCK inventory control, DCU suffix. Barcode
  dates are `MMDDCCYY` (the front prints `MM/DD/YYYY`). (Element dictionary
  per Scanbot's AAMVA documentation and the Nebraska DMV AAMVA calibration
  sheet; a CA-published element layout does not exist — decode the specimen
  and diff DAQ/DBB/DBA/DCF/DDA against the face.)
- Printed donor element location on the CA back: **UNVERIFIED** (the DDK
  donor flag exists in the barcode; that is not a printed back element).

## 7. Security / originality features — photo visibility

| Feature | Visible in an ordinary photo? |
|---|---|
| Ghost/secondary photo (§3 — position varies) | Yes |
| Laser-engraved data (2025: text and images engraved, not ink) | Yes — matte engraved texture |
| Hologram / optically variable element; State Seal over the photo | Patch may appear in a still; **colour-shift behaviour cannot be verified from a single photo** — score presence only |
| Fine-line/guilloche artwork (generation-specific: miner/poppies/sailboats 2018; redwoods/poppies/coastline 2025) | Yes — artwork-vs-generation conformance is itself a check |
| PDF417 ↔ face cross-check (DAQ/DBB/DBA/DCF/DDA) | Yes — the strongest photo-channel test |
| UV artwork: holder's photo, birth date, **Golden Gate Bridge and Coit Tower** (DMV 2018 description); a full-colour UV ghost image is described by a secondary expert source | **No** — UV light required. (A "UV bear/poppies" claim is **UNVERIFIED** — opened sources name the bridge/tower set) |
| Tactile features: **DOB displayed across the primary photo in raised 3D numbers**; signature in raised laser engraving | Touch-only; at most a shadow cue |
| Laser perforations (bear/state outlines, 2025 back) | **Backlit only** — invisible in a normal front photo |
| Microprinting in background patterns (IDScan) | Magnification only — not phone-photo verifiable |
| Digital barcode signature (2025) | Machine-verifiable via the PDF417 only |

## 8. Live-scan practicalities

- **Three generations, three templates** (2010 / 2018 / 2025): artwork,
  labels (RSTR vs REST; DL vs DLN/4d) and the back (mag stripe vs none;
  one vs two barcodes) all differ. A 2018-style card is not "old = fake" —
  all generations are valid to printed expiry.
- **Mag-stripe logic inverts in 2025:** presence fits pre-2025 cards;
  **absence is correct on 2025 cards** — never require a stripe.
- **Red fields are the OCR anchors** (DOB, EXP, number): read them in the
  colour channel where red ink is darkest (blue/green channels).
- **DD is opaque** (§4): the only DD checks are presence/format-length
  sanity and equality with barcode DCF.
- Name assembly follows the labels (LN line then FN line; 2025: field 1
  then field 2), never cross-state position assumptions.
- Vertical under-21 cards carry the red **AGE 21 IN** bar (blue
  PROVISIONAL bar under 18) — read the bar year as an additional printed
  field.
