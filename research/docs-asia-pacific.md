# Document-Type Matrix — Asia-Pacific & UAE (AU, IN, PH, SG, AE)

Researched 2026-10-26 for the Nova KYC platform. Purpose: tell the live-capture flow, per
document, whether to capture **front only or front + back**, whether an **expiry date exists**
(critical: several major IDs have NO expiry — the engine must not demand or fail on a missing
expiry for those), whether there is a **photo**, and what machine-readable features exist
(MRZ / barcode / QR / chip).

> ⚠️ General rule for the engine: **never treat "no expiry date printed" as a defect** for the
> documents flagged **NO EXPIRY** below. Sources are named per section; items marked
> *(uncertain)* were not confirmed against a primary source in this pass and should be
> re-verified before being hard-coded.

---

## Australia (AU)

Australia has **no national ID card**. Identity relies on the passport, state/territory driver
licences, and state/territory photo cards.

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| Australian Passport (ordinary) | Department of Foreign Affairs and Trade (DFAT) / Australian Passport Office | Booklet — capture biodata page only | **YES** — 10 yrs adults (16+); 5 yrs children <16; 75+ may choose 5 or 10 | Yes | **MRZ + RFID e-chip** (all passports since 2005; chip now embedded in polycarbonate data page, R-series) | ICAO TD3 booklet; biodata page is polycarbonate in current series. |
| Driver Licence (state/territory) | State/territory transport authority (e.g. Transport for NSW, VicRoads, TMR Queensland) | **Front + back** | **YES** — varies by state & term purchased: commonly 5 or 10 yrs (NSW 5/10; QLD up to 5; VIC 3/10) *(state table varies — verify per state before hard-coding)* | Yes | No MRZ. Barcode on back on many state cards *(uncertain — varies by state/series)*; no chip on physical card (digital licences in app) | Credit-card size; front: photo, name, DOB, licence no., expiry, classes. Back: address/conditions. Layout differs per state. |
| State Photo Card / Proof of Age Card | State/territory transport/service authority | **Front + back** | **VARIES BY STATE** — NSW Photo Card: 5 yrs (<21) / 10 yrs (21+); QLD Photo ID Card: 10 yrs; NT Evidence of Age: 5 yrs; TAS Personal Information Card: 5 yrs; WA Photo Card: 5 yrs; **VIC Proof of Age, SA Proof of Age, ACT Proof of Identity: NO EXPIRY** | Yes | No MRZ / no chip *(barcode uncertain, varies)* | Same card stock/security family as the state's driver licence; for non-drivers. Name differs per state — key the catalogue by state, not by one national name. |

Sources: DFAT/embassy passport FAQs (uk.embassy.gov.au); Service NSW (nsw.gov.au); SA.GOV.AU;
Wikipedia "Australian state and territory issued identity photo cards" (state validity table).

---

## India (IN)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **Aadhaar** (letter / PVC card / e-Aadhaar) | Unique Identification Authority of India (UIDAI) | **Front + back** | **NO EXPIRY — valid for life.** No expiry date exists or is printed. (UIDAI recommends updating biometrics/details ~every 10 yrs; children: mandatory biometric updates at age 5 and 15 — an update duty, NOT an expiry.) Aadhaar for resident foreign nationals is the exception: validity tied to visa/status *(per ClearTax summary of UIDAI rules)* | Yes | **Secure QR code** (digitally signed by UIDAI; encodes demographics + photo — designed for offline verification). No MRZ, no chip on PVC card | 12-digit Aadhaar number. PVC card front: photo, name, DOB, gender, QR, hologram, ghost image; back: address, issue/print dates, QR. Paper letter/e-Aadhaar layouts differ from PVC — support all three forms. |
| **PAN Card** (Permanent Account Number) | Income Tax Department (issued via Protean/NSDL & UTIITSL) | Front only (single-sided card; e-PAN is a PDF) | **NO EXPIRY — valid for lifetime** (Income Tax Dept: "PAN obtained once is valid for lifetime"). Can become *inoperative* if not linked to Aadhaar — an administrative status, not an expiry date | **Yes** — physical PAN card carries holder's photograph, name, father's name, DOB, signature | No MRZ / QR / chip on standard card *(older/newer variants may differ — uncertain)*. 10-character alphanumeric number (e.g. ABCDE1234F) | Tax ID first, photo ID second: photo is small and cards are often low-quality laminates — do not weight PAN as a primary photo document. |
| Indian Passport | Ministry of External Affairs (Passport Seva) | Booklet — biodata page only | **YES** — 10 yrs adults; 5 yrs minors (or until 18) | Yes | **MRZ**; chip: India is rolling out **e-passports (RFID chip)** from 2025 — older booklets have MRZ only, so chip must be optional in the flow | ICAO TD3; 36/60-page booklets. |
| Driving Licence | State RTO / Ministry of Road Transport & Highways (Parivahan/Sarathi) | **Front + back** (smart-card form) | **YES** — non-transport: 20 yrs or until age 50, whichever earlier (post-2019 age-banded renewals: 30–50 → 10 yrs; 50–55 → to 55; 55+ → 5 yrs); transport/commercial: ~3–5 yrs | Yes | Chip on newer smart-card DLs *(state-dependent — uncertain)*; QR/barcode on many recent cards *(uncertain)*; no MRZ | Legacy paper/booklet DLs still in circulation alongside smart cards. Front: photo, DL no., validity (NT/TR split dates printed separately). |
| Voter ID / EPIC (Electoral Photo ID Card) — secondary | Election Commission of India | Front + back | **NO EXPIRY** | Yes | Barcode/QR on newer EPIC cards *(uncertain by series)* | Included as a common secondary doc; colour EPIC is current standard. |

Sources: UIDAI (via UIDAI FAQ summaries & ClearTax Aadhaar guide — "Aadhaar issued … does not
have an expiry date"); Income Tax Department statement via Zee Business/PTI (PAN lifetime);
TaxGuru/Protean guides (PAN photo & format); Motor Vehicles Act 1988 as amended 2019 (DL
validity, via Testbook/Parivahan summaries); MEA Passport Seva validity rules *(passport
validity from general MEA rules — re-verify at build time)*.

---

## Philippines (PH)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **PhilID / National ID** (PhilSys; incl. paper ePhilID & digital ID) | Philippine Statistics Authority (PSA), under RA 11055 | **Front + back** | **NO EXPIRY for Filipino citizens — lifetime validity.** **Resident aliens: YES — 1 year**, expiry printed on front | Yes | **QR code** on back (digitally signed; reveals PSN for verification) + **barcode** (card serial) + micro-printed PSN. **No chip, no MRZ** | Polycarbonate CR80. Front: PCN (16-digit card number), photo, full name, DOB, address. Back: issue date, sex, blood type, marital status (optional), place of birth, QR + barcode. **No visible signature by design** (PSA security choice — do not flag missing signature). Paper ePhilID and eGovPH digital ID are legally equivalent forms — the capture flow must accept a paper printout. |
| **UMID** (Unified Multi-Purpose ID) | Social Security System (SSS) for private sector; GSIS for government employees | **Front + back** | **NO EXPIRY — lifetime** (while membership active) | Yes | **Contact smart chip + magnetic stripe**; biometrics stored on chip. No MRZ | CR80 card carrying SSS/GSIS, PhilHealth & Pag-IBIG numbers in one card; Common Reference Number (CRN) printed on front. New UMID issuance has been winding down in favour of PhilID *(status uncertain — still widely held & accepted)*. |
| Philippine Passport (ePassport) | Department of Foreign Affairs (DFA) | Booklet — biodata page only | **YES** — 10 yrs adults; 5 yrs minors | Yes | **MRZ + RFID e-chip** | ICAO TD3 biometric passport. |
| Driver's License | Land Transportation Office (LTO) | **Front + back** | **YES** — 5 yrs on first issuance; **10 yrs on renewal for drivers with no recorded violations** | Yes | Barcode/QR on current plastic card *(LTO card carries a QR/barcode — verify series at build time)*; no MRZ/chip | Plastic card (replaced paper receipts era); front: photo, licence no., expiry, restrictions/conditions codes. Digital version in LTMS/eGovPH also exists. |

Sources: PSA / Inquirer (PhilID: "PhilIDs issued to Filipino citizens do not expire, while
resident aliens get them for one year only"); PSA PhilID design showcase via BalikBayan
Magazine & Wikipedia "Philippine national identity card" (front/back content, QR, barcode);
Home Credit PH & Grit PH valid-ID guides (UMID lifetime, chip + mag stripe; LTO 5/10-yr
validity); DFA passport validity (10/5 yrs).

---

## Singapore (SG)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **NRIC** (National Registration Identity Card, "IC") | Immigration & Checkpoints Authority (ICA) | **Front + back** | **NO PRINTED EXPIRY DATE — but NOT lifetime-unconditional:** no expiry date on the card; holders must **re-register at age 30 and again at 55** (unless issued a card within the preceding 10 yrs). Treat as "no expiry field; age-based re-registration" in the engine — never parse an expiry from an NRIC | Yes | No MRZ / no chip read by third parties. Back carries the holder's fingerprint (thumbprint) image and barcode *(barcode detail uncertain)*; biometrics (thumbprints + iris since 2017) are held by ICA, not on a readable card chip | Polycarbonate credit-card size. **Pink = citizen, blue = permanent resident.** 9-character NRIC number (S/T prefix). Front: photo, name, NRIC no., DOB, race, country/place of birth. Foreigners hold FIN-numbered pass cards instead (green Long-Term Pass card) — FIN cards DO expire with the pass; do not confuse the two in the catalogue. |
| Singapore Passport | Immigration & Checkpoints Authority (ICA) | Booklet — biodata page only | **YES** — **10 yrs for citizens 16+** (issued on/after 1 Oct 2021; previously 5); 5 yrs under 16 | Yes | **MRZ + RFID e-chip** (biometric passport since 2006) | ICAO TD3. ICA form IMME 11 confirms 10-yr validity wording. |
| Driving Licence (Qualified Driving Licence, photocard) | Singapore Police Force — Traffic Police | **Front + back** | **NO EXPIRY for citizens & PRs — valid for life / no expiry date** (SPF: "valid for life with no expiry date"); from age 65, renewal/medical every 3 yrs. **Foreigners: YES — up to 5 yrs** | Yes | No MRZ/chip *(barcode uncertain)* | Photocard QDL; digital licence also shown in Singpass. Engine must branch on holder status (citizen/PR vs foreigner) for expiry expectation. |

Sources: ICA (re-registration at 30/55; passport validity) via ICA form IMME 11 & ICA e-services
summaries; Wikipedia "National Registration Identity Card"; Singapore Police Force ask.gov.sg
("licences issued to citizens and PRs are valid for life with no expiry date, foreigners up to
5 years").

---

## United Arab Emirates (AE)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **Emirates ID** | Federal Authority for Identity, Citizenship, Customs & Port Security (ICP) | **Front + back** | **YES — always expires.** Citizens 21+: **10 yrs**; citizens <21: 5 yrs; GCC nationals resident: 5 yrs; **expatriate residents: tied to residence visa, typically 2–3 yrs** (up to 10 for Golden Visa) | Yes | **Contact/contactless biometric smart chip** (fingerprints + facial data; 15-digit permanent ID number — the number never changes across renewals, only the card validity does). New-generation cards add printed QR/security features *(series-dependent)*; no MRZ | Mandatory for all residents. Front (current gen): photo, name (Arabic/English), nationality, ID number. Since Apr 2022 the ID itself evidences residence (passport visa stickers discontinued). Digital Emirates ID in UAE PASS has equal legal validity. |
| UAE Passport (Emirati passport) | ICP (ordinary); Ministry of Foreign Affairs (diplomatic/service) | Booklet — biodata page only | **YES** — **10 yrs for citizens 21+** (since 8 Jul 2024; previously 5); **5 yrs under 21** | Yes | **MRZ + RFID e-chip** (biometric since Dec 2011; 2nd-generation biometric passport since Sep 2022) | ICAO TD3; citizens only — residents travel on their home-country passports + Emirates ID. |
| Driving Licence | Emirate-level licensing authority (e.g. Dubai RTA; Abu Dhabi Police / TAMM) — federal standards | **Front + back** | **YES** — first licence: 2 yrs (1 yr if under 21). **Renewal: 10 yrs UAE & GCC citizens; 5 yrs expatriate residents**; 65+ renew on 3-yr cycle *(per u.ae summaries)* | Yes | No MRZ/chip *(barcode/QR on some emirate cards — uncertain)* | Card layout is broadly standardised federally but issued per emirate; bilingual Arabic/English. Digital licence in UAE PASS / emirate apps. |

Sources: ICP via Wego/Emirates Times/Times of India (Emirates ID validity by category; one-step
renewal rules); ICP via Khaleej Times & Wikipedia "Emirati passport" (10-yr passport validity
from Jul 2024, chip since 2011); u.ae government portal summaries via RTA-renewal guides
(driving licence validity/renewal periods).

---

## ⚠️ NO-EXPIRY summary — documents the engine must accept with NO expiry date

| Country | Document | Notes |
|---|---|---|
| IN | **Aadhaar** | Lifetime; no expiry printed. Update recommendations ≠ expiry. |
| IN | **PAN card** | Lifetime per Income Tax Department. (May go *inoperative* if unlinked from Aadhaar — status, not expiry.) |
| IN | Voter ID (EPIC) | No expiry. |
| PH | **PhilID / National ID** | Lifetime **for citizens only** — resident-alien PhilIDs expire in 1 yr and DO print an expiry. Branch on holder type. |
| PH | **UMID** (SSS/GSIS) | Lifetime. |
| SG | **NRIC** | No expiry date printed; re-registration duty at 30 & 55 instead. |
| SG | Driving Licence (citizens/PRs) | No expiry / valid for life (65+ medical renewal cycle). Foreigners' licences expire at 5 yrs. |
| AU | VIC Proof of Age, SA Proof of Age, ACT Proof of Identity cards | No expiry — while other states' photo cards DO expire (5–10 yrs). **State-level branch required.** |

**Documents that ALWAYS have an expiry** (safe to require & validate): all passports in scope;
Emirates ID; AU driver licences; AU photo cards in NSW/QLD/NT/TAS/WA; IN driving licence;
PH driver's licence; IN passport; SG passports; UAE driving licence.

## Known uncertainties to verify before hard-coding
1. AU driver-licence barcode presence/format per state; AU photo-card barcode.
2. IN smart-card DL chip/QR rollout by state; PAN card print variants.
3. PH LTO card QR/barcode by series; current UMID issuance status.
4. SG NRIC back-of-card barcode specifics.
5. AE Emirates ID printed QR by card generation; emirate DL barcode/QR.
6. IN passport chip: e-passport rollout is phased (2025+) — chip presence must stay optional.
