# US driver licences — 50-state catalogue (number formats & back barcodes)

Research date: 2026-10-27. Compiled from two independent research passes over
AAMVA public material, state DMV/DOT official pages, state statutes/manuals,
and established secondary references. **No real person's licence number
appears anywhere in this file; every entry is a format pattern.** Where the
two passes disagreed, the cell shows the cross-checked envelope and the
disagreement is noted — nothing was silently picked.

## How to read the two evidence columns

- **Format source — "Official"** is strict: an official state/federal source
  opened in research *states the pattern itself*. Only **AL, MA, NY, OH, WA**
  meet that bar outright (FL and OR are partial — see their rows). Every
  other state's pattern is well attested in agreeing secondary lists (US
  Dept. of State / Office of Foreign Missions table, AZ DPS bulletin IN09008,
  Versa DLP reference, and similar) but is **not officially published** —
  marked as such, per this library's rule that a state publishes its format
  or we say it doesn't.
- **PDF417 — two tiers.** Tier 1 (standard): the AAMVA DL/ID Card Design
  Standard **requires** the PDF417 in Zone V of the card back, and the
  federal REAL ID rule **6 CFR §37.19** mandates ISO/IEC 15438 (PDF417) as
  the machine-readable technology on REAL ID cards, with the licence number
  as a mandatory element. **All 50 states issue REAL ID cards, so PDF417 is
  Yes for all 50 on that basis.** Tier 2 (specimen): a state-specific source
  confirming the barcode was opened for the states marked "state source
  opened". "Yes (standard)" without that mark means: mandated by the
  governing standard, **not** specimen-inspected for that state. If a hard
  calibration gate ever needs specimen-grade proof, it must be collected
  card-by-card.
- **Magnetic stripe:** AAMVA-optional, coexists with PDF417 where present,
  phasing out since ~2017. Not reliably published per state — **do not
  calibrate on mag-stripe presence without a specimen.**
- **Design generation:** a full per-state design survey was out of scope;
  generation notes appear only where they change the number format or
  issuance (AL 2018, MA 2018, OH 2018, WA 2018, FL 2024, TX/CA dossiers).

| State | DL number format (pattern) | Format source | PDF417 on back | Notes |
|---|---|---|---|---|
| AL | 7 digits (legacy); **8 digits for new issues from 1 Dec 2018** | **Official** (ALEA notice: 8-digit from Dec 2018, 7-digit still supported) | Yes (standard) | — |
| AK | Up to 7 digits (1–7) | Not officially published (secondary) | Yes (standard; state source opened) | — |
| AZ | 1 letter + 8 digits; legacy 9 digits (SSN-derived) | Not officially published (secondary, incl. AZ DPS IN09008; an ADOT page describes the field) | Yes (standard; state source opened) | Both families live — don't force one |
| AR | 9 digits (IN09008: begins 9 + 7 sequential + check digit); older lists 4–9 digits, SSN-derived legacy | Not officially published (secondary) | Yes (standard; state vendor RFP opened) | — |
| CA | **1 letter + 7 digits** | Not officially published (no verbatim DMV pattern doc; universally attested) | Yes (standard; state source opened) | Full dossier: dl-ca.md |
| CO | 9 digits; legacy 1 letter + 3–6 digits, or 2 letters + 2–5 digits | Not officially published (secondary; statute shows the field masked) | Yes (standard; state manual opened) | — |
| CT | 9 digits (secondary: first 2 digits encode birth month, offset by birth-year parity) | Not officially published (secondary; a CT DMV page describes the field) | Yes (standard; state source opened) | Enhanced DL discontinued 30 Jun 2025 |
| DE | 1–7 digits (variable) | Not officially published (secondary) | Yes (standard) | Short legacy numbers survive |
| FL | **1 letter + 12 digits** (Soundex-derived segments). **From 31 Jul 2024: at least 4 digits must be randomly generated** (Fla. Stat. §322.14(1)(a)); length/shape unchanged | Pattern: not officially published (secondary). Random-digit change: **Official** (FLHSMV release, 19 Jul 2024) | Yes (standard; FLHSMV AAMVA material opened) | Segments encode name/DOB data |
| GA | 9 digits (current); older lists 7–9; SSN used pre-2007 | Not officially published (secondary; DDS treats the number as confidential) | Yes (standard; DDS design page opened) | — |
| HI | "H" + 8 digits, or 9 digits | Not officially published (secondary; county pages confirm the field) | Yes (standard) | Issued by counties |
| ID | 9 alphanumeric, structured — reported as **2 letters + 6 digits + 1 letter** in one pass and as a letter at position 4 with a check letter at position 9 in another | Not officially published (secondary; passes conflict on internal structure) | Yes (standard) | Treat as "9-char structured alphanumeric" until a specimen settles the layout |
| IL | **1 letter + 11 digits** (Soundex: surname initial + coded name/DOB); some lists also allow 1 + 12 | Not officially published (secondary; an IL Admin Code reference was cited in one pass) | Yes (standard; state source opened) | — |
| IN | 10 digits (grouped 4-2-4); legacy 1 letter + 9 digits, or 9 digits | Not officially published (secondary; a BMV page describes the field) | Yes (standard) | — |
| IA | **3 digits + 2 letters + 4 digits** (9 chars), or 9 digits | Not officially published (secondary; Iowa Code names the field) | Yes (standard; Iowa DOT RFP opened) | — |
| KS | "K" + 8 digits; legacy 9 digits (SSN-derived) | Not officially published (secondary; a KDOR page describes the field) | Yes (standard) | — |
| KY | 1 letter + 8 digits, grouped L##-###-### (secondary structure: letter = surname initial, next 2 = year first issued, then 6 random) | Not officially published (secondary; a KYTC page describes the field) | Yes (standard; KYTC source opened) | — |
| LA | 9 digits, typically beginning 00 (IN09008: 00 or 01 + 7) | Not officially published (secondary) | Yes (standard) | — |
| ME | 7 digits; or 7 digits + 1 letter | Not officially published (secondary; a BMV page describes the field) | Yes (standard) | — |
| MD | 1 letter + 12 digits (Soundex, surname initial first) | Not officially published (secondary; an MVA page describes the field) | Yes (standard) | — |
| MA | Legacy **"S" + 8 digits**; **"SA" + 7 digits for newly issued credentials from 13 Nov 2018** (existing S numbers unchanged on renewal) | **Official** (Mass. RMV ATLAS notice, Nov 2018) | Yes (standard) | S combinations were exhausted — hence SA |
| MI | 1 letter + 12 digits (Soundex); one list records 1 + 10 for older issues | Not officially published (secondary; SOS manual shows the form) | Yes (standard; SOS manual opened) | — |
| MN | 1 letter + 12 digits (Soundex) | Not officially published (secondary) | Yes (standard) | Current design issued since Aug 2018 |
| MS | 9 digits (IN09008 prefixes 000/001/800/801/900 + 6; SSN-derived pre-2006) | Not officially published (secondary) | Yes (standard) | — |
| MO | 1 letter + 6–9 digits (commonly 1 + 9); or 9 digits; SSN option legacy | Not officially published (secondary; DOR FAQ gives examples, not a rule) | Yes (standard; DOR FAQ opened) | Format alone cannot validate a MO card — corroborate |
| MT | **13 digits, structured:** 2 birth month, 3 assigned, 4 birth year, 2 = "41", 2 birth day; a 9-digit variant is also reported | Not officially published (secondary; a DOJ page describes two formats) | Yes (standard) | The "41" constant is a strong structural tell |
| NE | 1 letter (only A, B, C, E, G, H or V) + up to 8 digits | Not officially published (secondary) | Yes (standard; NE DMV barcode page opened) | Holder keeps the same number for life (DMV) |
| NV | **10 digits (current)**; legacy 12 digits, or "X" + 8 digits | Not officially published (secondary; a DMV REAL ID guide describes lengths) | Yes (standard) | Length varies by generation |
| NH | **2 digits + 3 letters + 5 digits** (10 chars, structured: birth month, name letters, birth year/day, check digit) | Not officially published (secondary; a DOS manual describes the structure) | Yes (standard) | One of the few structured formats with a check digit |
| NJ | 1 letter + 14 digits (surname initial; trailing segment encodes birth month/year + eye colour) | Not officially published (secondary; legacy AAMVA D20's SSN-based description is obsolete — do not use) | Yes (standard; MVC source opened) | Longest US format |
| NM | 9 digits (8–9 in some lists) | Not officially published (secondary) | Yes (standard) | — |
| NY | **9 digits (Client ID)** — not the separate 8/10-char document number | **Official** (NY DMV: "The NY driver license number is nine digits", Data Elements page) | Yes (standard; specimen + DMV sources opened) | Full dossier: state-id-ny.md; a check digit is listed for NY in FLHSMV's AAMVA deck but is unpublished |
| NC | 1–12 digits (up to 12, unhyphenated) | Not officially published (secondary; statute confirms the number, not its format) | Yes (standard; NCDMV source opened) | Variable length is genuine — do not length-gate |
| ND | **3 letters + 6 digits** (surname-derived: first 3 letters of surname, or 2 + "X"; then 2-digit birth year + 4 generated digits); legacy 9 digits | Not officially published (secondary) | Yes (standard) | — |
| OH | **2 letters + 6 digits** | **Official** (Ohio Secretary of State form: "two letters followed by six numbers"; corroborated by a county Board of Elections) | Yes (standard; BMV PDF417 fact sheet opened) | **Correction flag:** an earlier pass reported "1 letter + 7 digits (current)" from BMV material — no official source supports a second pattern; Ohio's 2018 change was central issuance + REAL ID design, not the number. Treat 2+6 as authoritative and the 1+7 claim as an error unless a specimen shows otherwise |
| OK | 1 letter + 9 digits (from 1 Jan 2007 per IN09008); legacy 9 digits / SSN-derived | Not officially published (secondary; a Service Oklahoma page describes the field) | Yes (standard) | — |
| OR | Legacy 1–7 (some lists 1–9) digits; **new customers from 21 Oct 2013: 7-character alphanumeric** customer number, reported as 1 letter + 6 digits | **Partial** — ODOT form confirms Oregon has both numeric and alphanumeric Customer ID numbers; the exact 7-char pattern is secondary | Yes (standard; ODOT specs opened) | Variable — corroborate, don't gate |
| PA | 8 digits | Not officially published (secondary) | Yes (standard; PA fact sheet opened) | — |
| RI | 7 digits (first 2 = year-of-issue code); some lists also "V" + 6 digits | Not officially published (secondary) | Yes (standard) | — |
| SC | 5–11 digits (newer lists; 9 in older lists) | Not officially published (secondary) | Yes (standard; SCDMV source opened) | Treat as variable-length numeric, low confidence on bounds |
| SD | 8 digits (current per IN09008); secondary ranges of 6–10 and 12 digits also appear; SSN-derived pre-30 Jun 2005 | **Not officially published** (secondary lists conflict) | Yes (standard) | Weakest-sourced row in this table — specimen required |
| TN | 7–9 digits (commonly 8–9) | Not officially published (secondary; a TDOSHS FAQ describes the number) | Yes (standard; TDOSHS source opened) | — |
| TX | **8 digits** (older OFM list: 7–8) | Not officially published (no DMV pattern spec; universally attested) | Yes (standard; TX DPS sources opened) | Full dossier: dl-us.md (incl. the separate 20-digit DD audit number) |
| UT | 4–10 digits (one pass: 9 digits with a check digit last — unverified) | Not officially published (secondary lists disagree on range) | Yes (standard) | — |
| VT | 8 digits; or 7 digits + 1 letter (usually trailing "A") | **Not officially published** (secondary) | Yes (standard) | — |
| VA | 1 letter + 8 digits typical; ranges of 1 letter + 8–11 and a 9-digit form also reported; legacy SSN-derived and "R"/"T" + 8 | Not officially published (secondary; a DMV page describes the current design, Jul 2023) | Yes (standard; VA DMV source opened) | — |
| WA | Legacy (pre-2018) **structured 12 chars** (surname letters + initials + coded DOB + check digit). **Current, from 4 Sep 2018: "WDL" + 9 random alphanumeric = 12 chars, no name/DOB content** | **Official** (WA DOL format published via WA Liquor & Cannabis Board update citing DOL, and DOL statements) | Yes (standard; WA DOL AAMVA reference opened) | The legacy format leaks name/DOB structure — cross-check only, never an identity source |
| WV | 7 digits; or 1–2 letters + 5–6 digits | **Not officially published** (secondary) | Yes (standard) | — |
| WI | 1 letter + 13 digits (Soundex, grouped 4-4-4-2: surname code, first/middle code, birth year, birth month/day + gender offset, tie-breaker) | Not officially published (secondary; a WisDOT page describes the structure) | Yes (standard; WisDOT source opened) | Current design since Jun 2023 |
| WY | 9 digits (9–10 in the older OFM list; IN09008: assigned 9-digit, spaced 6-3) | **Not officially published** (secondary; privacy rule confirms the element only) | Yes (standard) | — |

## Cross-cutting calibration notes

- **Almost no state officially publishes its number format** — under the
  strict standard only AL, MA, NY, OH, WA (plus FL's 2024 randomisation rule
  and OR's two-family confirmation) qualify. Everything else in the table is
  a secondary-sourced prior: a plausibility signal, never a hard rejection
  gate.
- **PDF417 is universal on current designs by mandate** (AAMVA Zone V +
  6 CFR §37.19), and no exception state was found — but the mandate is a
  standard, not a sighting; the "state source opened" marks show where this
  research went beyond the standard.
- **Multi-family and variable-length states are common** (AZ, IN, MO, NC,
  NV, OR, SC, UT, VA…): a format check must accept every live family for
  the state or it will false-reject genuine cards.
- **Coded formats** (FL, IL, MD, MI, MN, MT, ND, NH, NJ, WI, WA-legacy)
  embed name/DOB data in the number — where a template knows the coding,
  the number becomes an internal cross-check against the printed name/DOB;
  where it doesn't, treat the number as opaque.
- **Check digits are rare and usually unpublished** (structural: NH;
  attested-but-unpublished: NY; segment-internal: FL/WI). Never invent one.
- **Legacy SSN-derived numbers** (AZ, GA, KS, MS, OK, SD…) are phased out;
  encountering one dates the card — it is not, by itself, a forgery signal.

## Principal sources

Federal/standard: AAMVA DL/ID Card Design Standard (Zone V PDF417 mandate;
Annex F mag-stripe optionality); 6 CFR §37.19 (REAL ID machine-readable
technology, via Cornell LII / eCFR); FLHSMV AAMVA D20 deck
(https://www.flhsmv.gov/pdf/cdl/AAMVA-D20.pdf) and FLHSMV release of
19 Jul 2024 (http://www.flhsmv.gov/2024/07/19/flhsmv-implements-legislation-requiring-driver-licenses-and-identification-card-numbers-to-change/);
Washington DOL AAMVA barcode file-format reference
(https://www.dol.wa.gov/sites/default/files/forms/500039.pdf).
Official pattern statements: ALEA notice (https://www.mvtrip.alabama.gov/News/ViewArticle/444);
Mass. RMV ATLAS notice (Nov 2018, via republication:
http://www.tarrtalk.com/2018/11/new-mass-license-and-id-format-change.html?m=1);
NY DMV Data Elements (https://dmv.ny.gov/book/export/html/15111);
Ohio Secretary of State form (https://assets.ohiosos.gov/q3i90m1u8zsl/2W2eL8SSNZ3TIu3vS8u53U/e84f9ee0b0eb31ad12abc49ad2015d72/10-l.pdf)
and Montgomery County (OH) Board of Elections
(https://www.montgomery.boe.ohio.gov/identification-requirements/);
WA DOL via WA Liquor & Cannabis Board update.
Secondary cross-state lists (basis for every "not officially published" row):
US Dept. of State / OFM format table; AZ DPS bulletin IN09008
(https://v.vibdoc.com/in09008-state-dl-formats.html); Versa DLP pattern
reference; dlencoder.com; and agreeing secondary compilations.
