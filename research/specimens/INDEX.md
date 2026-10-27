# Specimen dossiers — index

Research date: 2026-10-27. Layout dossiers for the document types the owner
will use to calibrate the live scanner. Built only from official/public sources
(issuer pages, official specimen material, reputable reporting), each claim cited
in its file. **No real person's document was used.** Fractions in the dossiers are
relative (x0, y0, x1, y1) of the card face; anything marked **[estimate]** is a
calibration prior, not a measurement, and items marked **UNVERIFIED** are flagged
gaps, not facts.

| File | Type | Issuer | Key number | Sides/channels |
|---|---|---|---|---|
| [dl-us.md](dl-us.md) | US Driver License — Texas | Texas DPS | DL number, **8 digits** | Front fields + back PDF417 (DAQ = DL no.) & mag stripe |
| [state-id-us.md](state-id-us.md) | US State ID Card — Texas | Texas DPS | ID number, **8 digits** (same format as DL) | Same DPS platform as DL, minus driving fields |
| [voters-card-ng.md](voters-card-ng.md) | Nigeria Permanent Voter's Card | INEC | **VIN, 19 alphanumeric** (format partly unverified) + 9-digit PU code | VIN on front **and** back; barcode on back; chip (camera-unreadable) |
| [nin-card-ng.md](nin-card-ng.md) | Nigeria National Identity Card (GMPC) | NIMC | NIN = **11 digits but NOT printed** on the current card | NQR code (contains NIN), MRZ on back, chip |
| [dl-ng.md](dl-ng.md) | Nigeria National Driver's Licence | FRSC | Licence number, **12 characters, letters+digits** (no published segmentation or check digit) | Two vintages (2007 / 2011 scheme — photo side and features differ); barcode symbology **unverified**; back class text + acronym index |
| [dl-ca.md](dl-ca.md) | California Driver License **and** Identification Card | California DMV | DL/ID number, **1 letter + 7 digits**; DD audit string (**opaque** — no published segmentation) | Three generations (2010 / 2018 / **2025**); back PDF417 (AAMVA); mag stripe pre-2025 only, 2025 has two barcodes |
| [state-id-ny.md](state-id-ny.md) | New York State Non-Driver ID Card | NY DMV | Client ID number, **9 digits** (check digit unpublished); Document Number 8 numeric / 10 alphanumeric | **Landscape** (21+) / portrait (under-21); laser-engraved; **clear window** with ghost photo (2013) / MLI flip window (2022); back PDF417 |
| [passport-ca.md](passport-ca.md) | Canada Passport — data page | IRCC | Passport number: 2013 **2 letters + 6 digits**; 2023 **1 letter + 6 digits + 2 letters** | Data page + **MRZ TD3** fully check-digit validatable; variable laser image carries DOB (angle-dependent) |
| [us-states-catalogue.md](us-states-catalogue.md) | All 50 US states' driver licences — catalogue | State DMVs / AAMVA | Per-state number format (officially published for only AL, MA, NY, OH, WA + FL/OR partial) | **PDF417 on all current designs by mandate** (AAMVA Zone V + 6 CFR §37.19); state sources opened for a subset — two tiers distinguished in-file |

## The four in a few lines each

- **Texas DL** — ID-1 polycarbonate, landscape (vertical if under 21). 2025 design:
  black laser-engraved REAL ID star upper-right; **DL number and DOB share the
  first data line**; AAMVA numbered labels (1 surname, 2 given, 3 DOB, 4a Iss,
  4b Exp, 4d number, 5 "DD" audit number = 20 digits, changes per reissue, no
  published check digit for either number). Back PDF417 repeats the DL number.
  Glossy → high glare; engraved greyscale portrait.
- **Texas ID card** — same DPS card, same redesign dates, **same 8-digit number
  format** (DPS's status service treats DL/ID numbers identically). Distinguish
  from the DL by the header title and the **absence of class/endorsement/
  restriction fields** — never by the number.
- **INEC PVC** — layout per INEC's own 14-feature diagram: **PU code top-right**,
  **VIN parallel to it** across the top, delimitation under the VIN, name
  (surname, first, middle), DOB with **gender parallel** to it, occupation, address;
  **photo right side under the PU code**, fingerprints indicator under the photo.
  Back: barcode at top, serial + batch numbers, **VIN repeated** with registration
  date. **No expiry exists on this card** (INEC, on record) — never require one.
- **NIMC NIN card** — GMPC chip card. Policy-era card prints surname/first/middle,
  DOB, gender, nationality, portrait + ghost image, expiry, signature, card
  issuance number on the front; **MRZ + mag stripe + signature strip on the back**;
  NIN lives in the chip. **Current (2024, AfriGO) card does not print the NIN at
  all** — it is in the **NQR code**; identity part has an issue date and no expiry,
  payment part prints an expiry on the front. Scanner must target QR → MRZ →
  document number, not a printed NIN.

## The five additions in a few lines each

- **FRSC licence (NG)** — two vintages circulate and must not be merged:
  the 2007 card (photo left, thumbprint, barcode on the front bottom,
  ~9.5 × 6 cm) and the 2011 scheme (photo **right**, no thumbprint,
  coat-of-arms hologram). Number: **12 characters, letters+digits** — the
  segmentation/"centre code" hypothesis in the original brief was **not
  supported by any opened source** and is recorded in-file as unverified;
  no check digit. Term **3 or 5 years**; birthday-anchored expiry is
  documented only in a 2003 account and conflicts with a current
  "from issue" source — never gate on it. **Barcode symbology is
  unverified** (do not assume PDF417). Back (2007): non-magnetic brown
  strip, class definitions, and the acronym index ("BG: Blood Group") —
  the key to the front's abbreviations. Classes A–J (I skipped; V convoy
  on the Highway Code page).
- **California DL & ID** — one family, two titles, **three generations**:
  2010, 2018, and a **2025 design (from 30 Sep 2025)** with redwoods/
  poppies/coastline art, **AAMVA-numbered labels** (RSTR→**REST**, DL→
  **DLN/4d**), **no mag stripe**, and **two back barcodes, one digitally
  signed**. Number **1 letter + 7 digits** for both documents; DOB/EXP/
  number print **red**; **DD is an opaque audit string** — its date+office
  segmentation is unverified (an earlier draft's DD↔ISS rule is withdrawn);
  cross-check DD against barcode **DCF** instead. REAL ID = **white star
  in the golden bear**; "FEDERAL LIMITS APPLY" is a variant, never a
  defect. Ghost-photo position varies by generation/orientation.
- **New York non-driver ID** — **landscape for 21+, portrait only for
  under-21** (correcting the brief's premise); polycarbonate, greyscale
  laser-engraved portrait; generations 2013 and **2022**. **9-digit**
  client ID (a check digit exists in DMV's system per NY regulation; the
  algorithm is unpublished). The window is officially a **CLEAR window**:
  2013 — beveled, lower-right, ghost photo visible from both sides, name
  "wave" through it; 2022 — **multiple-laser-imaging window at right
  center flipping photo ↔ birth month+year**. It only *looks* black in
  photos. The per-card **Document Number is 8 numeric or 10 alphanumeric
  characters** (back, after "Doc #") — not the long production string also
  printed on specimen backs. Standard marking per DMV: **"NOT FOR FEDERAL
  PURPOSES"**; Enhanced is discriminated by a **US flag image**. Tactile
  raised text: ID number, DOB, expiry, signature.
- **Canada passport** — 2013 book: pages 2–3, laminated, colour printed
  photo, OVI + embossed hologram laminate + "CAN" see-through register.
  **2023 book: polycarbonate leaf at the front, laser-engraved data, chip
  in a transparent window in the page**, kinegram over the photo, a
  **variable laser image carrying photo + DOB** (angle-dependent), a
  temperature-sensitive red maple leaf, visible chip/antenna. ⚠️ **The
  number format changed: 2023 = 1 letter + 6 digits + 2 letters (9
  chars)** vs 2013's 2 + 6 — accept both, bound to generation. **MRZ TD3
  2×44, all five ICAO check digits computable**; VIZ sex includes **X**,
  which maps to MRZ `<`; Canada's use of the MRZ personal-number zone is
  unverified (an earlier draft's "fillers, never a SIN" claim is
  softened accordingly). Adult validity 5 or 10 years.
- **50-state catalogue** — number formats for all 50 states under a strict
  honesty standard: **only AL, MA, NY, OH and WA officially publish their
  pattern** (FL's 2024 rule — at least 4 digits of the number must now be
  random — and OR's two-family system are official partials); everything else
  is a secondary-sourced prior. Multi-family and variable-length states (AZ,
  MO, NC, OR, SC, WA…) defeat single-pattern gates; coded formats
  (FL/IL/MD/MI/MN/MT/ND/NH/NJ/WI, classic WA) double as name/DOB cross-checks.
  **PDF417 is mandated on every current card** (AAMVA Zone V + the REAL ID
  rule 6 CFR §37.19) — the file distinguishes that standard-level fact from
  per-state specimen confirmation. One correction is flagged in-file: Ohio's
  number is officially **2 letters + 6 digits** (an early research pass's
  "1 + 7" claim has no official support; Ohio's 2018 change was issuance,
  not the number).

## Cross-cutting calibration notes

- **Two of the four types defeat naive templates:** the PVC has no expiry/signature/
  MRZ; the current NIN card has no printed primary number. Per-type field
  expectations must be configurable, with honest degradation.
- **Photo-visible originality signals** (all types): layout/typography conformance,
  ghost images, guilloche/fine-line print quality, colour-shift behaviour over a
  tilt sequence, barcode/MRZ/QR payload cross-checks. **Not photo-visible anywhere:**
  UV artwork, tactile features, and every chip — camera verdicts must say so.
- **Glare:** polycarbonate types (TX DL/ID, NIMC card) are the worst; the laminated
  PVC is milder. Busy backgrounds behind text: NIMC card > TX 2025 design > PVC.

## Open gaps (see "UNVERIFIED" items in each file)

1. TX 2025 front layout fractions are AAMVA-zone estimates — no official specimen
   image was measured; DPS's DL-73 PDF is the official source (form page:
   https://www.dps.texas.gov/InternetForms/home/Details/3300).
2. TX "DD" audit-number exact front position unconfirmed from DPS; 20-digit length
   is secondary-sourced.
3. TX ID-card header wording and its number-field label attested only by
   low-authority sources.
4. PVC physical dimensions are not published in any opened source (do not assume
   ID-1 as fact); PVC chip's visible contact-plate position unverified.
5. PVC VIN: 19 characters alphanumeric is the best-supported reading, but INEC
   primary documentation was not captured; guides conflict (incl. a disregarded
   "10-digit" claim and suffix-length disagreements).
6. NIMC cards: no measurable official specimen image captured; GMPC front has a
   contents list (§3.5.1) but no coordinates; 2024-card field positions, MRZ
   format, and substrate unverified; validity differs by generation (10 years
   policy-era vs 5 years reported for the 2024 card).
7. FRSC licence: the current card's dimensions/substrate are unpublished
   (2007 specimen ≈9.5 × 6 cm only); the number has **no published
   segmentation at all**; the barcode's symbology, position on the current
   card, and payload are unverified; exact printed label strings are
   unconfirmed beyond "BG" (via the back index) — all to be settled from
   the owner's specimen (front + back, both vintages if available).
8. California: DD internal format and its position on the 2025 face are
   unverified (treat DD as opaque, cross-check via DCF); the second 2025
   barcode's symbology is unconfirmed for CA; senior-ID validity is
   conflicted in sources (8 vs 10 years); card material is unpublished.
9. New York: NDID header typography, a class-"ID" field, PDF417 position,
   and any mag stripe on the current card are unverified from DMV text;
   the client-ID check-digit algorithm is unpublished; the role of the
   long production string on specimen backs is unidentified.
10. Canada passport: the 2023 data page's exact printed page number, an
    official-text statement that its portrait is greyscale, the VIZ date
    format, Canada's use of MRZ positions 29–42, and OVI's presence on the
    2023 page are all unverified — specimen MRZ + page inspection needed.
11. 50-state catalogue: design generations were out of scope except where they
    change the number format; most states' formats rest on secondary sources
    (SD's conflict the most) and PDF417, while mandated universally, was
    specimen/state-source confirmed only for a subset — specimen confirmation
    required before any hard gate. The Ohio 2+6 vs 1+7 conflict is resolved
    in-file in favour of the official form, flagged for specimen check.
