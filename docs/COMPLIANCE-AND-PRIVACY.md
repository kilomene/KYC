# KYC — Compliance & Privacy Ground Rules

*This document is engineering ground rules, not legal advice. Before the
first live tenant, the platform needs review by a qualified lawyer in each
launch jurisdiction. The build does not wait for that review to behave
properly — these rules are how it behaves from day one.*

## 1. Why this product is regulated territory

KYC exists because laws (AML/CFT regimes, e.g. the US BSA, EU AML
directives, Nigeria's Money Laundering (Prevention and Prohibition) Act
and CBN rules, UK MLR) require many businesses to identify customers.
We are a **tool** tenants use to meet **their** obligations. That means:

- We never market KYC as "making you compliant" on its own. A tenant's
  compliance also depends on their policies, training, and regulators.
- Features tenants need for audit (records, retention, exports, reason
  codes) are core functionality, not extras.

## 2. Privacy principles (hard rules)

1. **Consent first.** No collection before the consent screen (BLUEPRINT
   §4). Consent text is versioned and the record is kept.
2. **Minimum collection.** A check that does not need a field does not
   get it. No advertising trackers anywhere in the applicant flow. Ever.
3. **Purpose lock.** Applicant data is used to verify that applicant for
   that tenant — nothing else. No cross-tenant matching for marketing,
   no sale of data, no training external models on applicant images
   without explicit, separate, lawful basis and owner sign-off.
4. **Retention with teeth.** Defaults: document/selfie images deleted
   90 days after decision unless the tenant's lawful rule requires
   longer (tenant-configurable inside platform bounds); biometric
   templates on the shortest clock; decision records and audit skeletons
   kept per the tenant's regulatory need. Deletion is a scheduled,
   verified job (DATA-MODEL), and erasure requests are honoured with a
   webhook confirmation.
5. **Data-subject rights.** Access, correction, and deletion requests are
   routed via the tenant, fulfilled within the platform's stated window,
   and audited. An applicant can always find out *that* a verification
   happened and its outcome category.
6. **Biometrics are special-category data.** Treated accordingly under
   GDPR / Nigeria Data Protection Act 2023 / applicable US state laws
   (e.g. Illinois BIPA): explicit consent, separate retention, no
   secondary use, deletion first-class.
7. **Cross-border honesty.** Where data is stored/processed is stated in
   the tenant DPA. We do not silently move applicant data to new regions
   or sub-processors; the sub-processor list is published to tenants and
   changes are notified.

## 3. Fairness

- Face-match and liveness systems perform differently across demographics
  if built carelessly. Phase 2 acceptance includes performance testing
  across skin tone, age, and gender cohorts, with review routing —
  not auto-rejection — absorbing borderline cases.
- A rejection always carries reason codes, and tenants are given an
  appeals / re-verification path to offer applicants.

## 4. Records tenants can rely on

Per decision: checks run, providers used, rules version, timestamps,
reviewer actions, screening list sources + versions. Exportable per
applicant and in bulk. If we cannot produce the record, the decision
does not count as defensible — that is the standard the build is held to.

## 5. Incidents

Suspected breach: contain first, notify affected tenants without undue
delay (target ≤ 72h from confirmation), cooperate with their regulator
timelines, post-mortem in writing. The incident process is written and
rehearsed before launch, not invented during one.
