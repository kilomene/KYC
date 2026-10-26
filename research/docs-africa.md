# Document-Type Matrix — African Launch Countries (NG, GH, KE, ZA)

Researched 2026-10-26 for the Nova Inc KYC platform. Per-document facts: official name, issuing authority, capture sides, **expiry (critical for verification logic)**, photo, and machine-readable features (MRZ / barcode / QR / chip).

⚠️ = uncertain or conflicting sources — flagged inline, do not hard-code without checking a real specimen.

**The headline finding for the verification engine: expiry is per-document, NOT per-country.** Nigeria's core identity documents (NIN slip, NIN itself, PVC) have **no expiry at all**, Kenya's older national ID has **no expiry** while its replacement (Maisha Card) expires after 10 years, and South Africa's green ID book has **no printed expiry** but stops being legally valid on a fixed calendar date (31 March 2028). Any rule of the form "reject if document expired / require an expiry date" will wrongly reject legitimate users of these documents. Expiry must be an optional, per-document-type field.

---

## Nigeria (NG)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **Nigerian Passport** (Standard e-Passport, "international passport") | Nigeria Immigration Service (NIS) | Biodata page (booklet) | **YES** — 32-page booklet: **5 years**; 64-page booklet: **10 years** (a 64-page/5-year variant is also reported — NIS via press, Sept 2025 fee/validity schedule) | Yes | **MRZ + contactless chip** (ICAO e-passport, enhanced ePassport since 2019, polycarbonate data page) | Booklet, green cover; all NIS passports biometric since 2007 |
| **National Driver's Licence** | Federal Road Safety Corps (FRSC) | Front primary (⚠️ back content not verified from an official source) | **YES** — holder chooses **3 years or 5 years** at issue/renewal (Joint Tax Board decision; FRSC portal guides, 2025–2026 fees ₦15,000 / ₦21,000) | Yes | No MRZ. Chip/barcode ⚠️ not confirmed from official source — treat as visual card | Plastic credit-card-style card; a 60-day paper temporary licence is issued while the card is produced |
| **Permanent Voter's Card (PVC)** | Independent National Electoral Commission (INEC) | Front (photo + voter details); back carries card/security data ⚠️ layout varies by issue batch | **NO — no expiry date, valid indefinitely.** INEC Chairman Mahmood Yakubu (2022): "PVCs have no expiry dates… PVCs issued by the Commission remain valid for all elections." INEC spokesman Rotimi Oyekanmi (TheCable fact-check, 2022): "A PVC does not have an expiry date on it, therefore, it does not expire. As long as the security chip on it is not damaged, it remains valid." | Yes | **Embedded chip** holding holder biometrics (fingerprints + facial image), read by INEC card readers/BVAS; printed barcode also reported (INEC, via IRB Canada response / The Nation 2013). No MRZ | Plastic smart card; designed physical lifespan ~10 years (INEC factsheet) — **physical lifespan ≠ legal expiry** |
| **NIN Slip** (Standard and Premium/Improved) | National Identity Management Commission (NIMC) | Front only (single-sided printout) | **NO — no expiry.** NIMC Ag. DG Hadiza Dagabana: "The National Identification Number does not have expiry date… The NIN slip which Nigerians identify as temporary is not temporary… it is a unique ID for that particular person for life." The NIN is rested only on death | **Yes** on the current standard/premium slips (name, DOB, photo printed; the earliest enrolment printouts had no photo — ⚠️ older slips in circulation may be photo-less) | **QR code** (verifiable via the NIMC MWS Mobile ID app). No MRZ, no chip | **Paper slip** — a printed PDF/printout (A4 or card-sized print), NOT a plastic card. "Premium" slip adds card-style layout + enhanced security print; third-party shops laminate/print it on PVC, which is not a NIMC product |
| **NIN Card / National e-ID card** (legacy NIMC plastic card) | NIMC | Front + back | **The NIN: NO expiry (lifetime). The physical card: ⚠️ UNCERTAIN** — secondary sources say the plastic National ID card "may have an expiry period, often between 5 to 10 years" after which reissue is required; legacy e-ID cards carried printed dates. Verify against a specimen before relying on a card expiry | Yes | Chip on legacy e-ID card (it doubled as a payment card); new **General Multipurpose Card (GMPC)** announced by NIMC for rollout from Oct 2025 — chip + payment (AfriGO) functions, full spec/expiry not yet published ⚠️ | Plastic card. Historically very limited issuance — most Nigerians hold only the slip. **Do not make the plastic NIN card a required document type** |
| **Digital NIN / Mobile ID** (virtual NIN, NIMC Mobile ID app) | NIMC | n/a (screen) | **NO** (same lifetime NIN) | Yes (in-app digital ID) | QR code displayed in app for verification | Phone-screen credential, not a physical document — relevant only if the flow ever supports app-based proofing |

**Nigeria notes**
- The documents a Nigerian user is *most likely to actually hold*: NIN slip (paper, no expiry, QR), PVC (plastic, no expiry, chip), driver's licence (3/5-yr expiry), passport (5/10-yr expiry). Requiring an expiry date would break the two most common ones.
- State ID: Nigeria has **no US-style state ID card** — the NIN credential is the national equivalent. (The owner mentioned "state ID for US"; Nigeria issues nothing comparable at state level.)

---

## Ghana (GH)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **Ghana Card** (National Identification Card) — citizens | National Identification Authority (NIA) | **Front + back** | **YES — 10 years** from issue, then renewal required by law. NIA press statement, 23 Sept 2025: "the Ghana Card remains valid for 10 years from the date of issuance, after which it must be renewed as required by law" (debunking rumours of a shorter period) | Yes | **Chip (dual-interface/contactless) + MRZ on the back + 2D barcode** on the back holding biometric/personal data (Wikipedia, from NIA card spec); chip stores fingerprints, photo, signature | Plastic smart card; also serves as an ECOWAS travel document within the region |
| **Ghana Card — Non-Citizen** (FIMS card) | NIA (Foreigners Identification Management System) | Front + back | **YES — 1 year**, renewed annually (NIA renewal guidance: non-citizen renewal fee = USD 78 equivalent per year) | Yes | Same chip/MRZ/barcode platform as citizen card | Plastic smart card for legally resident foreign nationals |
| **Ghana Passport** | Passport Office, Ministry of Foreign Affairs | Biodata page (booklet) | **YES — 10 years** (standard ordinary passport validity; Ghanaian passport cited at 10-year validity in DVLA/political reporting, 2024) | Yes | **MRZ + chip** (biometric e-passport) | Booklet |
| **Driver's Licence** | Driver and Vehicle Licensing Authority (DVLA) | Front + back ⚠️ (back layout not verified from official source) | **YES — expiry printed on card.** Per DVLA clarification under the Road Traffic Regulations, 2026 (L.I. 2519), Sept 2026: licences **must be renewed every 2 years** and the **card replaced after 6 years** from issue; renewal requires an eye test. ⚠️ Some older guides describe a single 5- or 6-year validity — the 2026 DVLA position (2-yr renewal cycle on a 6-yr card) is the current one | Yes | Smart card with chip/biometrics ⚠️ (DVLA "smart" licence; chip details from secondary sources) | Plastic card; temporary paper cover note issued while card prints |
| **Voter ID Card** | Electoral Commission (EC) of Ghana | Front | **NO printed expiry — "unlimited validity"** per Keesing Reference Systems (via IRB Canada response). ⚠️ Caveat: cards are superseded when the EC compiles a new voter register (EC stated old cards stay valid only until a new register is legitimised, 2020) — validity is register-dependent, not date-based | Yes | Barcode (biometric data — photo + fingerprints — barcoded on the card, EU EOM report 2017). No MRZ/chip | **Laminated paper card** (~95 × 65 mm), printed and laminated at the district office |

**Ghana notes**
- Ghana Card is the anchor document: front+back capture, expiry check valid and required (10-yr), and it has all three machine-readable features (chip, MRZ, 2D barcode).
- The EC has signalled the Ghana Card will become the sole basis of the voter register — the separate voter ID card is a legacy/secondary document.

---

## Kenya (KE)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **National Identity Card — 2nd Generation** (the card most adult Kenyans still hold) | National Registration Bureau (NRB) | Front + back | **NO — no expiry date.** Biometric Update (2024): the Maisha Card's 10-year validity is "a major shift from the previous generation of ID cards in Kenya which had no expiry date" | Yes | **MRZ on the back** (CIPIT policy paper: 2nd-gen card upgraded with "a machine readable zone on the back through which the ID card can be authenticated"); no chip. Photo, signature and one fingerprint printed | Teslin/laminated card (2011 upgrade of the 1995 plastic card), credit-card sized |
| **Maisha Card** (3rd Generation ID, with Maisha Namba) | National Registration Bureau (NRB), State Dept. for Immigration & Citizen Services | Front + back | **YES — 10 years**, renewal required. Immigration PS Julius Bitok (2024): "Holders will need to renew their national ID cards every ten years… the cards have a service life of ten years" — driven by the chip's ~10-year shelf life; expiry does **not** affect citizenship. First cards issued 2023 → first expiries 2033 | Yes | **Machine-readable microchip**; QR code reported in rollout plans ⚠️ (chip confirmed by Kenya News Agency; QR from secondary roadmap sources) | Plastic smart card, rolling out since Nov 2023 — **both this and the 2nd-gen card must be supported in parallel** |
| **Kenyan e-Passport** (Ordinary, A/B/C series) | Directorate of Immigration Services | Biodata page (booklet) | **YES — 10 years** for adults; **5 years** for minors under 18 | Yes | **MRZ + chip** (ICAO 9303-compliant e-passport) | Booklet, 34/50/66 pages |
| **Smart Driving Licence** | National Transport and Safety Authority (NTSA) | Front + back ⚠️ (back layout not verified from official source) | **YES — 3 years** standard validity for the smart DL card (NTSA, widely reported; one secondary source lists longer renewal options — ⚠️ treat 3 years as the norm) | Yes | **Chip** (stores name, blood group, biometric data — NTSA via Nairobi News). No MRZ confirmed | Plastic smart card; older booklet/paper licences still in circulation |

**Kenya notes**
- Kenya is a **two-generation problem**: the no-expiry 2nd-gen card (with back MRZ) and the 10-year Maisha Card (chip) will both appear. Document detection must distinguish them — same country, opposite expiry logic.

---

## South Africa (ZA)

| Document | Issuing authority | Sides | Expiry? | Photo? | MRZ / barcode / QR / chip | Format note |
|---|---|---|---|---|---|---|
| **Smart ID Card** | Department of Home Affairs (DHA) | Front + back | **⚠️ UNCERTAIN / DISPUTED — no expiry date is printed on the card and DHA publishes no renewal cycle for it; treat as NO expiry until verified against a specimen.** Multiple secondary guides claim "valid for 10 years," but this appears to conflate the card's physical lifespan — at the 2013 launch, Minister Naledi Pandor described the card as having "a life span of at least 10 years" (physical durability, gov.za/Vuk'uzenzele). One explainer states flatly the SA ID (book or card) "does not expire." A forthcoming separate **digital ID credential** (MyMzansi app, draft regulations 2026) would have a **5-year** validity — that is a different, not-yet-launched credential | Yes (laser-engraved) | **Contactless chip** with biometric data (fingerprints, photo), laser-engraved personalisation. No MRZ (⚠️ card carries a card-number/barcode area on the back — verify on specimen) | Plastic credit-card-sized card, issued since 2013 |
| **Green ID Book** (bar-coded identity book) | Department of Home Affairs (DHA) | Photo page inside booklet (multi-page) | **NO printed expiry — BUT legally time-bombed:** DHA (Minister Leon Schreiber, 1 Oct 2026) — production stops **31 March 2027** and green ID books **will no longer be recognised as valid ID from 31 March 2028**. ~14.7 million people still hold only a green book | Yes | **Barcode** (hence "green bar-coded ID book"); no chip, no MRZ | Paper booklet with green cover; the long-standing SA ID, being phased out for fraud reasons |
| **South African Passport** | Department of Home Affairs (DHA) | Biodata page (booklet) | **YES — 10 years** (age 16+); **5 years** (children 15 and under). Passports are not renewed — a new one is issued (DHA) | Yes | **MRZ + chip** (e-passport) | Booklet |
| **Driving Licence Card** | Department of Transport / RTMC (via driving licence testing centres) | Front + back | **YES — 5 years** from the date the card is ordered (Road Traffic Regulations reg 108(5)(a)). **Change gazetted Aug 2026 but NOT yet in effect:** 10-year cards for codes A1, A, B, EB (heavy codes stay 5 years; PrDP stays 2 years) — until the amendment commences, the expiry printed on the card governs. Note: the underlying licence itself never expires; only the card does | Yes | No MRZ; card carries barcode ⚠️ (verify on specimen) | Plastic card. The licence-in-ID-book era (pre-1998) documents had no expiry at all |

**South Africa notes**
- The green book is the trap: no expiry date to OCR, yet it becomes worthless on a fixed date. Verification logic needs a **document-type validity end-date** (2028-03-31 for ZA green ID book) separate from any printed expiry.
- Do not build SA Smart ID expiry logic on the "10 years" claim until a specimen or DHA ruling confirms a legal expiry — the evidence points to lifespan, not expiry.

---

## Cross-country summary — expiry logic implications

| Country | Document | Expiry behaviour |
|---|---|---|
| NG | NIN slip / NIN | **None — lifetime** |
| NG | PVC (voter's card) | **None — lifetime** (chip damage = replacement, not expiry) |
| NG | Driver's licence | 3 or 5 years (holder's choice) |
| NG | Passport | 5 years (32 pp) / 10 years (64 pp) |
| GH | Ghana Card (citizen) | 10 years |
| GH | Ghana Card (non-citizen) | 1 year |
| GH | Voter ID card | None printed; superseded by new register |
| GH | Driver's licence | Printed expiry; 2-year renewal cycle, card replaced at 6 years |
| GH | Passport | 10 years |
| KE | National ID (2nd gen) | **None** |
| KE | Maisha Card (3rd gen) | 10 years |
| KE | Passport | 10 years (adults) / 5 years (minors) |
| KE | Smart driving licence | 3 years |
| ZA | Green ID book | None printed; **invalid after 31 Mar 2028** |
| ZA | Smart ID card | ⚠️ Disputed — no printed expiry found; "10 years" claims appear to be card lifespan |
| ZA | Passport | 10 years (adults) / 5 years (children) |
| ZA | Driving licence card | 5 years (10-year change gazetted, not yet effective) |

**Design rules that follow:**
1. Expiry date is an **optional** field per document type — never a required capture, never a hard reject when absent for a no-expiry type.
2. Support **document-level validity windows** independent of printed dates (ZA green book cutoff).
3. Two generations of the "same" national ID can have opposite rules (KE) — key the rules to the exact document type/generation, not the country.
4. Nigeria's highest-coverage documents are the weakest physically (paper NIN slip, no MRZ/chip — QR only) — capture and OCR flows must handle paper, glare and print-shop laminations.

## Sources (principal)

- NIMC Ag. DG Hadiza Dagabana on NIN lifetime validity — Nigeria Communications Week / The Sun / Daily Trust (NAN interview)
- INEC Chairman Mahmood Yakubu + spokesman Rotimi Oyekanmi on PVC having no expiry — Ripples Nigeria, The Star, TheCable Fact Check, Africa Check (2022)
- INEC PVC construction (chip, biometrics, 10-yr physical lifespan) — IRB Canada Response NGA105486 (ecoi.net), The Nation (2013)
- NIS passport validities/fees (32 pp/5 yr, 64 pp/10 yr, Sept 2025 schedule) — NIS press release via LegalClarity / Travo
- FRSC licence 3-yr/5-yr options — Joint Tax Board decision via Pulse Nigeria; FRSC portal renewal guides (2026)
- NIMC NIN slip formats (standard vs premium, QR, photo, paper) — AndroidPols, CorporateZaddy portal guides (2025–2026) ⚠️ secondary sources; NIMC does not publish a full slip spec
- NIMC GMPC announcement (Oct 2025) — NIMC DG remarks via The Sight News / Realnews Magazine
- NIA Ghana Card 10-year validity — NIA press statement 23 Sept 2025 via BusinessGhana / The Vaultz News / Ghana Guardian; card features (MRZ back, 2D barcode, chip) — Ghana Card, Wikipedia (NIA spec)
- DVLA licence renewal cycle (2-yr renewal, 6-yr replacement; L.I. 2519) — DVLA statement Sept 2026 via MyJoyOnline / Citi Newsroom
- Ghana voter card (laminated, unlimited validity, barcoded biometrics) — IRB Canada Response GHA106033 (ecoi.net), EC Ghana registration page
- Kenya Maisha Card 10-year validity — Immigration PS Julius Bitok via KBC, The Standard, NTV Kenya, Kenya News Agency (2024); 2nd-gen no-expiry contrast — Biometric Update (2024); 2nd-gen MRZ on back — CIPIT, *Digital ID in Kenya* policy paper
- Kenya passport 10-year validity / chip — Kenyan Wall Street (Directorate of Immigration Services fees/validity, 2026)
- Kenya smart DL 3-year validity + chip — NTSA via Nairobi News / Business Daily
- SA green book phase-out dates (production ends 31 Mar 2027; invalid from 31 Mar 2028; 14.7 m holders) — DHA Minister Leon Schreiber, 1 Oct 2026, via BusinessTech / The South African / Newsroom.co.za
- SA Smart ID chip + "life span of at least 10 years" — Minister Naledi Pandor launch statement, Vuk'uzenzele (gov.za), 2013; "valid for 10 years" claims — SkillsPortal / PressPortal guides ⚠️ unverified against DHA
- SA passport validity (10 yr adult / 5 yr child) and DL card validity (5 yr, reg 108(5)(a); 10-yr extension gazetted Aug 2026, not in effect) — DHA / Dept. of Transport via KuduDoc, BusinessTech, MyBroadband
