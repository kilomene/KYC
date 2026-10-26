# Document-Type Matrix — Americas & Europe (US, CA, GB, DE, FR, NL, IE)

Per-country reference for the KYC document catalogue: which documents exist, what to capture,
and — critically — **which documents have no expiry date or a misleading one**.

Researched 2026-10-26. Sources are named per section; anything not confirmed against a source
is flagged ⚠ *uncertain*.

**How to read "Sides to capture":** this is where the identity data physically lives.
"Front+back" means a front-only scan loses data the platform needs (usually the MRZ or barcode).

---

## 🇺🇸 United States (US)

There is **no general US national ID card**. Federal documents are passports; everyday ID is
state-issued. All state DL/ID cards follow the **AAMVA DL/ID Card Design Standard**: the back
carries a **PDF417 barcode** that encodes the front data (name, DOB, address, doc number,
expiry — barcode element `DBA`), so front OCR can be cross-checked against the back barcode.

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Passport book | U.S. Department of State | Data page only | **Yes** — 10 yrs (age 16+), 5 yrs (under 16) | Yes | TD3 2-line MRZ on data page; contactless eMRTD chip in cover | "Next Generation Passport" (2021+) has a polycarbonate data page; older books have a laminated paper data page. |
| Passport Card | U.S. Department of State | **Front + back** | **Yes** — 10 yrs (16+), 5 yrs (under 16) | Yes (front) | **3-line MRZ on the BACK** + 1-D barcode of the card number on the back; vicinity RFID chip that stores only a database pointer — **not** an ICAO chip, holds no photo/biometrics | Wallet-sized; WHTI document — land/sea crossings to Canada/Mexico/Caribbean/Bermuda only, **not valid for international air travel**. Front-only capture gets you no machine-readable data at all. |
| Driver's License (state) | State DMV / MVD | **Front + back** | **Yes** — typically **4–8 yrs**, varies by state; REAL ID–compliant cards carry a star | Yes | No MRZ; **PDF417 barcode on back (mandatory under AAMVA)**; some states also print a magnetic stripe | ⚠ **Arizona outlier:** a standard AZ licence issued before age 65 is valid **until the holder's 65th birthday** (photo must still be refreshed every 12 yrs; AZ "Travel ID" follows an 8-yr cycle). Montana runs up to 12 yrs. Never hard-code a max validity for US licences. |
| State ID card (non-driver) | State DMV / MVD | **Front + back** | **Yes** — typically 4–8 yrs | Yes | No MRZ; **PDF417 barcode on back (AAMVA)** | Same card stock/design family as the state DL. ⚠ **NO-EXPIRY VARIANT:** Wisconsin issues a **non-expiring ID card to residents aged 65+** on request — it prints a far-future date instead of a real expiry and is REAL ID non-compliant (Wis. Stat. §343.50(5); Wis. Admin. Code Trans 102.16). Other states have similar senior provisions — check per state, don't assume. |
| Enhanced Driver's License (EDL) | State DMV — MI, MN, NY, VT, WA only | **Front + back** | **Yes** — follows the state's normal DL cycle (typically 8 yrs) | Yes | Vicinity RFID chip; US flag printed on front; PDF417 on back; no MRZ | WHTI land/sea border document. Only five states issue it; do not build a separate flow, just accept it as a DL variant. |

*Sources: U.S. Department of State passport-card feature specification (via Washington DOL);
AAMVA DL/ID Card Design Standard (Annex D — PDF417); Arizona Dept. of Transportation / A.R.S.
§28-3171; Wisconsin Legislature (Trans 102.16, §343.50).*

---

## 🇨🇦 Canada (CA)

There is **no Canadian national ID card**. Federal ID = passport (and PR Card for permanent
residents); everyday photo ID is provincial. Provincial cards follow the same AAMVA pattern
as the US: **PDF417 barcode on the back, no MRZ**.

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Passport (ePassport) | IRCC (Passport Program) | Data page only | **Yes** — adults choose **5 or 10 yrs**; children 5 yrs | Yes | TD3 2-line MRZ; contactless chip (all passports since 1 Jul 2013; chip in the back cover) | 2023 redesign moved to a polycarbonate data page. A Canadian passport expiring in <10 yrs is **not** suspicious — the 5-yr option is normal. |
| Driver's licence (provincial) | Provincial authority (e.g. ServiceOntario, ICBC in BC, Alberta registry agents) | **Front + back** | **Yes** — typically **5 yrs** (some provinces 4–5) | Yes | No MRZ; **PDF417 barcode on back (AAMVA)**; some provinces add a magnetic stripe | "Enhanced" driver's licences (with RFID) were discontinued — Manitoba's enhanced ID ended 1 Jun 2022, Ontario/BC programmes also closed. Treat any EDL as legacy. |
| Ontario Photo Card | ServiceOntario | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | For non-drivers 16+. Cannot be held at the same time as a driver's licence. Quirk: the **photo** on the card has its own 10-year life, separate from the card's 5-year expiry. |
| BC identification card (BCID) / BC Services Card (photo version) | ICBC / Service BC | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | BC Services Card is the health card and doubles as photo ID; a non-photo version also exists — **reject non-photo variants for KYC**. |
| Alberta ID Card | Alberta registry agents | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | Available from age 12. |
| Manitoba Identification Card | Manitoba Public Insurance | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | Enhanced version discontinued 2022. |
| Nova Scotia Photo ID Card | Service Nova Scotia | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | No minimum age. |
| New Brunswick Photo ID Card | Service New Brunswick | **Front + back** | **Yes** — **4 yrs** (shortest provincial cycle) | Yes | PDF417 on back; no MRZ/chip | No minimum age. |
| Saskatchewan Photo ID Card | SGI | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | First card free. |
| Prince Edward Island Photo ID Card | Access PEI | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | A 1-year version also exists. |
| Newfoundland & Labrador Photo ID Card | Digital Government & Service NL | **Front + back** | **Yes** — 5 yrs | Yes | PDF417 on back; no MRZ/chip | Senior discount on fee. |
| Québec — **no general photo ID card** | — | — | — | — | — | Québec issues no non-driver photo card. The **RAMQ health insurance card** (Régie de l'assurance maladie du Québec) carries a photo for most adults and is the de-facto ID; it has an expiry (validity periods vary, commonly 4–8 yrs ⚠ *uncertain — verify per card*). Ontario's photo health card exists too but is **not** accepted as general ID — do not catalogue health cards as ID outside Québec without a specific rule. |
| Permanent Resident Card | IRCC | **Front + back** | **Yes** — 5 yrs | Yes | Machine-readable zone on the back; chip reported by some verification vendors ⚠ *uncertain* | Proof of PR status, not citizenship. Laser-engraved photo. Often presented by newcomers who have no provincial ID yet — worth cataloguing. |

*Sources: canada.ca (passport features); Government of Ontario (Ontario Photo Card);
Wikipedia, "Canadian provincial and territorial photo cards" (per-province validity table);
vendor verification references for barcode format.*

---

## 🇬🇧 United Kingdom (GB)

⚠ **The UK has NO national identity card.** The Identity Cards Act scheme was abolished in
2010–11 and issued cards were invalidated. Any "UK national ID card" presented today is either
a PASS proof-of-age card (below) or a fake. Also note: **Biometric Residence Permits all
expired on 31 Dec 2024** and were replaced by the digital **eVisa** — a physical BRP is no
longer a current document.

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| British passport | HM Passport Office | Data page only | **Yes** — 10 yrs (adults), 5 yrs (children) | Yes | TD3 2-line MRZ; contactless chip | Current series has a polycarbonate data page. Burgundy (pre-Brexit EU) passports remain valid until their printed expiry. |
| Driving licence (photocard) | DVLA (Great Britain); DVA (Northern Ireland) | **Front + back** | **Yes** — the **photocard expires every 10 yrs** (field **4b** on the front); at 70 the licence is renewed every 3 yrs | Yes | **No MRZ, no chip, no standard barcode** — the back is only a table of vehicle categories and codes | Two different dates conceptually: the *photocard/photo* expiry (4b, 10-yr cycle) vs the *driving entitlement* (runs to age 70). For KYC use 4b. Paper counterpart was abolished in 2015 — never ask for it. NI licences are a separate issuer/design; accept both. |
| PASS proof-of-age card (CitizenCard / Post Office PASS Card) | CitizenCard (PASS-accredited; endorsed by the Home Office) | Front (primary data side) | **Mixed — ⚠ depends on issue date:** cards issued **before 7 Jan 2021 DO NOT EXPIRE**; cards printed on/after 7 Jan 2021 expire **3 yrs** after issue | Yes | None — no MRZ, barcode or chip; PASS hologram; authenticity is checked via the issuer's online verify service | Proof of **age**, widely accepted in the UK but a lower-assurance document than a passport/DL. The no-expiry pre-2021 population is real — a CitizenCard with no printed expiry is not automatically fake. |

*Sources: GOV.UK / DVLA photocard renewal rules; CitizenCard terms & conditions (clause 10.6)
and Post Office PASS Card pages.*

---

## 🇩🇪 Germany (DE)

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Personalausweis (national ID card) | Local citizens' office (Bürgeramt); produced by Bundesdruckerei | **Front + back** | **Yes** — 10 yrs (age 24+), 6 yrs (under 24) | Yes | **3-line TD1 MRZ on the BACK**; contactless RFID chip (eID) holding photo + fingerprints (fingerprints mandatory since Aug 2021) | Front has name/DOB/photo but **no address** — the address is printed on the back, next to the MRZ. Front-only capture loses both. Also a valid EU travel document. |
| Reisepass (passport) | Passport authority (Bürgeramt); Bundesdruckerei | Data page only | **Yes** — 10 yrs (24+), 6 yrs (under 24) | Yes | TD3 2-line MRZ; contactless chip with fingerprints | Hard polycarbonate data page. |
| Führerschein — EU card licence (issued from 19 Jan 2013) | Driving licence authority (Fahrerlaubnisbehörde) | **Front + back** | **Yes** — the **document** is valid **15 yrs** | Yes | No MRZ; no chip on the German card licence | The 15-year limit applies to the *document* (photo freshness); the underlying car/motorcycle driving entitlement itself does not expire. Back carries the category table. |
| ⚠ Legacy licences — grey/pink **paper** licence and pre-2013 card licences | Fahrerlaubnisbehörde | Front + back (paper licence unfolds) | **NO — no expiry date on the document.** Issued with unlimited document validity | Yes (often decades old) | None | Being phased out by **mandatory exchange, all by 19 Jan 2033**, on staggered deadlines by holder birth year (paper) or issue year (1999–2013 cards). A licence with no expiry date and a 30-year-old photo can be genuine — but treat photo-age mismatch as a review trigger, not an auto-reject. |

*Sources: Bundesportal / City of Hamburg licence-exchange guidance (deadline tables);
BMI/Bundesdruckerei Personalausweis specifications.*

---

## 🇫🇷 France (FR)

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Carte Nationale d'Identité (CNI) — **old large format** (issued up to 2021) | Ministère de l'Intérieur (mairie / ANTS) | **Front + back** | **Yes — ⚠ but the PRINTED date can be wrong.** Adults: **15 yrs**. Cards issued **2004–2013** to adults that were still valid on 1 Jan 2014 were **automatically extended by 5 years beyond the printed expiry** — the printed date understates true validity. Minors: 10 yrs (printed date correct) | Yes | **No chip, no MRZ** | The single biggest expiry trap in this matrix: an old-format French CNI can look expired and be legally valid. Expiry logic must apply the +5-year rule by issue year and holder age at issue. Back carries the home address. |
| Carte Nationale d'Identité électronique (CNIe) — **new card format** (since Aug 2021) | Ministère de l'Intérieur (ANTS) | **Front + back** | **Yes** — 10 yrs | Yes | Contactless chip; **TD1 MRZ on the back**; visible electronic seal (2D-Doc style code) | Credit-card format, issued under EU Regulation 2019/1157. Printed expiry is reliable on this format — the 15-yr/+5-yr rules belong to the old card only. |
| Passeport | ANTS / Ministère de l'Intérieur | Data page only | **Yes** — 10 yrs (adults), 5 yrs (minors) | Yes | TD3 2-line MRZ; contactless chip | Standard biometric passport. |
| Permis de conduire — card format (since Sept 2013) | ANTS / préfecture | **Front + back** | **Yes** — 15 yrs (categories A/B), 5 yrs (C/D) | Yes | Electronic chip in the card (per the 2013 launch spec); no MRZ | Renewal is administrative only (no test/medical for A/B). Back carries categories. |
| ⚠ Permis de conduire — **old pink paper licence** ("permis rose", 3-panel) | Préfecture | All panels | **NO EXPIRY — valid for life** | Yes (often very old) | None | Still held by millions. Remains valid until the mandatory replacement deadline of **19 Jan 2033**. No expiry field exists to check — catalogue it as a no-expiry document or exclude it deliberately; do not let generic expiry logic auto-fail it. |

*Sources: service-public.gouv.fr (CNI validity rules incl. the automatic-extension table by
issue year; driving-licence replacement by 2033); ANTS launch material for the 2013 card
licence.*

---

## 🇳🇱 Netherlands (NL)

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Nederlandse identiteitskaart (national ID card) | Municipality (mayor); RvIG standards | **Front + back** | **Yes** — up to 10 yrs (adults), up to 5 yrs (under 18) | Yes | **TD1 MRZ on the BACK**; contactless chip (photo + two fingerprints on the 2021+ model); Card Access Number (CAN) printed on the front | Back also carries the **BSN** (personal number). Valid travel document across Europe. Front-only capture loses MRZ + BSN. |
| Paspoort (passport) | Municipality / RvIG | Data page only | **Yes** — 10 yrs (adults), 5 yrs (under 18) | Yes | TD3 2-line MRZ; contactless chip | Standard biometric passport. |
| Rijbewijs (driving licence) | RDW (issued via municipality) | **Front + back** | **Yes** — 10 yrs (under 65); ages 65–70 issued until the 75th birthday; 70+ → 5 yrs | Yes | **Chip present** (since the 2014 model; also used as a DigiD login token); no MRZ | Back carries the category table. Validity shortens with age — don't flag a 5-year Dutch licence from a 72-year-old as anomalous. |

*Sources: RvIG identity-card feature brochures (2021/2024 models); RDW / municipal
driving-licence validity tables.*

---

## 🇮🇪 Ireland (IE)

Ireland has **no national ID card**. The Passport Card fills part of that role; the Public
Services Card is a services card, not an official ID card — but both are what Irish users will
actually present.

| Document | Issuing authority | Sides to capture | Has expiry? | Photo | MRZ / barcode / chip | Format note |
|---|---|---|---|---|---|---|
| Passport book | Passport Service, Dept. of Foreign Affairs | Data page only | **Yes** — 10 yrs (adults), 5 yrs (children) | Yes | TD3 2-line MRZ; contactless chip | Standard biometric passport. |
| Passport Card | Passport Service, Dept. of Foreign Affairs | **Front + back** | **Yes** — max **5 yrs, and never beyond the linked passport book's expiry** (card dies with the book) | Yes | ICAO 9303-compliant card with MRZ on the back; chip ⚠ *not confirmed* | Only issued to holders of a valid passport book (book must have ≥3 months left at application). Travel within EU/EEA/CH/UK. Expiry cross-check against the book is a catalogue-level rule, not just a field check. |
| Driving licence | NDLS (National Driver Licence Service) | **Front + back** | **Yes** — 10 yrs for car/motorcycle categories (shorter for older drivers: licences issued at 70+ run ~3 yrs, medical-dependent) | Yes | No MRZ; EU-format category table on the back | Plastic card since 2013 (replaced a paper licence). |
| Public Services Card (PSC) | Dept. of Social Protection | **Front + back** | **Yes** — cards issued **up to Nov 2018: 7 yrs**; issued after Nov 2018: **10 yrs** (some COVID-era urgent renewals only 3 yrs) | Yes (front) | Contact chip; no MRZ | Officially **not** a national ID card, but carries name, photo, DOB and PPS number and is widely held. Validity depends on issue era — the printed expiry governs. |
| National Age Card ("Garda Age Card") | An Garda Síochána | Front (primary data side) | **⚠ NO — there is NO expiry date on the Age Card; it does not expire** | Yes | None — no MRZ, barcode or chip | 18+ proof-of-age card showing DOB. A genuine no-expiry document: any flow that requires an expiry date will wrongly fail it. Lower assurance (age proof) — catalogue accordingly. |

*Sources: Citizens Information (Public Services Card validity by issue date); Dept. of Foreign
Affairs (Passport Card rules); Age Card scheme documentation (no expiry date).*

---

## Cross-country traps — summary for the catalogue build

**Documents with NO expiry date (expiry-required logic will break on these):**
1. 🇮🇪 Ireland — National Age Card: no expiry, by design.
2. 🇫🇷 France — pink paper driving licence: lifetime validity (mandatory replacement by 19 Jan 2033).
3. 🇩🇪 Germany — pre-2013 paper and early card licences: no printed expiry (exchange by 19 Jan 2033).
4. 🇬🇧 UK — CitizenCard PASS cards issued before 7 Jan 2021: do not expire (later cards: 3 yrs).
5. 🇺🇸 US — Wisconsin non-expiring state ID for 65+ (prints a far-future date); similar senior provisions elsewhere — per-state check needed.

**Expiry dates that lie:**
- 🇫🇷 Old-format CNI issued 2004–2013 (adult): legally valid **5 years past** the printed date.
- 🇺🇸 Arizona DL: expiry = 65th birthday (up to ~49 yrs of validity); the *photo* ages out every 12 yrs instead.
- 🇬🇧 UK DL: photocard expiry (4b, 10 yrs) ≠ entitlement expiry (age 70) — use 4b.
- 🇮🇪 Irish Passport Card: expires at min(5 yrs, passport book expiry).
- 🇨🇦 Canadian passport: 5-year adult passports are normal, not a red flag.

**Front-only capture failures (machine-readable data lives on the back):**
- 🇺🇸 Passport Card — MRZ + barcode entirely on the back. US/Canadian DL & ID cards — PDF417 on the back encodes the full front dataset (best anti-tamper cross-check available).
- 🇩🇪 Personalausweis, 🇳🇱 identiteitskaart, 🇫🇷 new CNIe — MRZ on the back (DE/NL backs also carry address / BSN).
- 🇬🇧 UK photocard DL is the exception that proves the rule: the back holds only a category table — no MRZ/barcode exists to capture.
