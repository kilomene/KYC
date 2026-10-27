# Specimen dossiers — index

Research date: 2026-10-27. Layout dossiers for the four document types the owner
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
