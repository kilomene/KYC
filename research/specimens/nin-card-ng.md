# Specimen dossier — Nigeria NIMC National Identity Card (plastic card)

Research date: 2026-10-27. Sources cited inline; **no real person's document was
used.** Items marked **UNVERIFIED** were not confirmed in an opened source.

**Scope warning — three different NIMC artefacts must not be conflated:**
1. **The paper NIN slip** — NOT this dossier (it is the platform's D9 upload-path
   type, covered elsewhere).
2. **The first-generation GMPC** (General Multipurpose Card, issued from 2014) —
   chip card specified by NIMC's National Identity Card Policy.
3. **The current multipurpose card** (announced April 2024; NIMC + CBN + NIBSS,
   powered by **AfriGO**) — the "current design" for calibration. Its printed layout
   differs materially from the GMPC: most importantly, **the NIN is not printed on
   it** (see §5).
Layout fractions are given only where a source supports them; NIMC publishes field
*contents* for these cards but not coordinates, so most boxes here are deliberately
left as **ordering statements**, with fractions marked **[estimate]** where offered
as calibration priors.

## 1. Issuer, official name, generations

- Issuer: **National Identity Management Commission (NIMC)**, Nigeria.
- Official name (current clarification by NIMC): **General Multipurpose e-ID Card
  (GMPC)** (NIMC clarification reported by NewsRangers, crawled 2026-10-27).
- Policy basis: **NIMC National Identity Card Policy** (official NIMC document;
  research copy read via a mirror because the original sits on nimc.gov.ng:
  https://s4.ecirtam.net/autoblogs/autoblogs/lamaredugoffrblog_6aa4265372739b936776738439d4ddb430f5fa2e/media/47b26c1e.id_card_policy.pdf).
  §3: the National Identity Card (NNIC) is a microprocessor-chip GMPC, **has an
  MRZ**, and is intended to qualify as a travel document (ICAO/ECOWAS).
- First generation (2014+): NIMC described it as **100% polycarbonate with 18
  security features** of international standard, 13 applets including payment and
  match-on-card (NIMC via Nigeria Communications Week:
  https://www.nigeriacommunicationsweek.com.ng/new-id-card-is-for-global-identity-nimc).
- Current card (Apr 2024): NIMC + CBN + NIBSS, powered by **AfriGO**; features per
  NIMC's statement: biometric authentication (fingerprint + photograph), offline
  capability, **MRZ with e-passport information**, **identity card issue date
  displayed on the card**, document number per ICAO, **NQR code containing the
  NIN**, debit/prepaid functionality (Radio Nigeria Lagos, reporting NIMC:
  https://radionigerialagos.gov.ng/nimc-partners-with-nibss-for-improved-national-identity-card-with-payment-and-social-service-delivery-capabilities/;
  also Vanguard, BusinessDay, Legit).

## 2. Physical format

- Chip card built to ISO/ICAO standards per the NIMC policy; ID-1
  (85.60 × 53.98 mm) is the applicable card standard for this class of document,
  but NIMC does not state dimensions in the opened sources — **treat ID-1 as the
  expected format, UNVERIFIED from a NIMC dimension statement.**
- Orientation: **landscape**. Material: polycarbonate (first-gen GMPC, NIMC above);
  current-card substrate **UNVERIFIED** in the opened sources.
- Validity — **generation-dependent, sources conflict across generations:**
  - Policy-era GMPC (§3.8): **10 years** for Nigerians; foreigners min(5 years,
    residence status).
  - Current (2024) card: reported **valid 5 years from issuance** (Radio Nigeria,
    above). Attribute each figure to its generation; do not merge them.

## 3. Layout

### 3a. Policy-era GMPC — front contents (Policy §3.5.1, contents list, no coordinates)

Front contains: **card issuance number, surname, first name, middle name, date of
birth, gender, nationality, holder's portrait, ghost image of the portrait, expiry
date, holder's signature, payment platform number.**

### 3b. Policy-era GMPC — back (Policy §3.5.2)

Back contains: **MRZ, card personalisation platform, magnetic strip and signature**
(signature strip).

The policy lists contents but **not positions**; §3.6 of the policy contains a
depiction ("Sample of the National Identity Card") but no image URL was exposed in
the text extraction. **Front layout fractions for the GMPC are therefore NOT
asserted** — any zone boxes must come from measuring the owner's specimen.

### 3c. Current (2024) multipurpose card — what is printed where (from NIMC statements)

- **The NIN is NOT printed visibly on the card** — it is accessed by scanning the
  QR code (BusinessDay / Vanguard reporting NIMC's own caution). The **NQR code
  containing the NIN** is the machine channel for the number.
- **Identity part:** carries an **issue date and no expiration date** — per Legit,
  the identity details sit on the **back** with the issue date only.
- **Payment part:** a **standard card expiry is printed on the front** (the AfriGO
  debit/prepaid function), and the MRZ carries e-passport information.
- Document number per ICAO is present (NIMC statement).
- Precise field positions/fractions for the 2024 card: **UNVERIFIED** — no official
  specimen image with measurable layout was captured (see §8). Calibrate from the
  owner's card.

## 4. Printed label wording

**UNVERIFIED in detail.** The NIMC policy names the front data elements (§3a) but
does not reproduce the printed captions. Do not assume US-style labels. The one
label-critical fact for the scanner is negative: on the current card there is **no
printed "NIN" number line to find** — searching the front for an 11-digit NIN is
the wrong strategy for this type (see §5).

## 5. Document numbers and validation

- **NIN: 11 digits**, numeric, assigned for life and never reassigned (Policy
  §3.5.4). Format-only validation: `^\d{11}$` — **NIMC publishes no check digit**
  for the NIN in the opened sources; any checksum claim is **UNVERIFIED**.
- Where the NIN lives, by generation:
  - GMPC (policy): the NIN is **stored in the chip** (§3.5.3 chip contents: NIN,
    surname, first/middle names, gender, DOB, card expiry, state of origin,
    nationality, fingerprints, head-shot photo). The policy's printed-front list
    (§3.5.1) includes a **card issuance number** — a different number from the NIN.
  - Current card: NIN is **not printed**; it is carried in the **NQR code**
    (BusinessDay/Vanguard; Radio Nigeria feature list).
- **Scanner consequence:** for the plastic NIN card, the extractable printed
  identifiers are the **document/card number**, the **MRZ** (back), and the **NQR
  code** — not a printed NIN. If the product needs the NIN itself from this card,
  the QR channel is the route NIMC designed for it.

## 6. Security / originality features — photo visibility

Card-body security features per Policy §3.4: **guilloche / fine-line design,
rainbow printing, laser printing and engraving, Optical Variable Ink (OVI), UV
printing, microtext, IRIS printing, holder's portrait, holder's signature,
microchip** (plus undisclosed others). Current-card clarification adds **UV marks
and digital verification** (NIMC via NewsRangers).

| Feature | Visible in an ordinary photo? |
|---|---|
| Guilloche / fine-line + rainbow printing | Yes — fine-line colour patterns are visible and hard to reproduce cleanly; good camera signal |
| Ghost image of the portrait (front, §3.5.1) | Yes, faintly |
| Holder's signature (front; signature strip on back) | Yes |
| OVI (optically variable ink) | Only when tilted — still photo may miss the shift; tilt/video sequence can capture it |
| Microtext | Only at macro/zoom range |
| UV printing / UV marks | **No** — UV-only, not photo-visible |
| IRIS printing | Subtle colour-transition print effect; partially visible |
| Microchip | **No** — electronic only; camera cannot read chip contents |
| MRZ (back) | Yes — OCR channel (ICAO-style), the highest-reliability text channel on the card |

## 7. Live-scan practicalities

- **Gloss/glare:** polycarbonate chip card → expect card-face glare like the US
  cards; laser engraving/print contrast varies by zone.
- **Background complexity:** guilloche + rainbow printing behind the data — the
  busiest printed background of the four types here; per-field zone priors and
  contrast passes matter more than for the PVC.
- **The number strategy differs fundamentally** (see §5): no printed NIN to OCR on
  the current card. Prioritise, in order: NQR decode → MRZ OCR (back) → printed
  document/card number → biographic fields. For the older GMPC, the printed
  **card issuance number** is the front identifier; the NIN itself is chip-only
  per the policy.
- **MRZ format** (line count/character set) is **UNVERIFIED** — the policy says
  the card "has an MRZ" and the 2024 statements mention an MRZ with e-passport
  information, but no opened source specifies TD1 (3×30) vs another format.
  Detect at calibration time.
- Expiry expectations differ by generation and by card *part* (identity part: no
  expiry on the current card; payment part: front expiry; GMPC: front expiry +
  10-year validity) — the template must key expiry logic to the generation, or a
  genuine current card will fail a naive "expiry required" rule.

## 8. Official specimen material

- **NIMC National Identity Card Policy** — §3.6 contains a depiction of the card
  ("Sample of the National Identity Card"); the official document is NIMC's, the
  research copy was read via the mirror URL in §1. **No standalone official
  specimen image URL was captured** — this is a known gap; retrieve specimen
  imagery from nimc.gov.ng in a browser before final calibration if possible.
