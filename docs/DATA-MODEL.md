# KYC — Data Model (Draft)

*Postgres (Supabase). All tables carry `created_at` / `updated_at` unless
append-only. All tenant-owned rows carry `tenant_id` and sit behind RLS.
PII fields are marked 🔒 — encrypted at rest, access-logged, never in logs.*

## Tenancy & access

- **tenants** — id, name, status (`active|suspended|closed`), country,
  default retention days, billing reference.
- **tenant_users** — id, tenant_id, email, role
  (`admin|reviewer|developer|billing|read_only`), status.
- **api_keys** — id, tenant_id, env (`test|live`), key hash (plaintext
  shown once), scopes, last_used_at, revoked_at.
- **webhook_endpoints** — id, tenant_id, url, signing secret (encrypted),
  events subscribed, status.

## Verification core

- **applicants** — id, tenant_id, external_ref (tenant's own user id),
  🔒 legal first/last name, 🔒 DOB, 🔒 country, 🔒 address fields,
  🔒 email, 🔒 phone, consent_id, data_deleted_at.
- **consents** — id, applicant_id, text_version, locale, granted_at,
  ip/user-agent summary. (Consent is a record, not a checkbox in a log.)
- **sessions** — id, tenant_id, applicant_id, level (`1|2|3|kyb`),
  status (see BLUEPRINT §6 states), link token hash, expires_at,
  completed_at, decision_id.
- **documents** — id, session_id, kind (`passport|drivers_licence|
  national_id|residence_permit|proof_of_address|company_registration|
  other`), issuing_country, storage paths (front/back), 🔒 extracted
  fields (name, DOB, number, expiry, MRZ raw), retention_delete_at.
- **biometric_captures** — id, session_id, storage path,
  liveness_method (`passive|active|none`), retention_delete_at.
  *Raw biometric templates, if any provider produces them, are stored
  separately from images, encrypted, and deleted on the shortest
  retention clock in the system.*
- **checks** — id, session_id, type (`capture_quality|classification|
  ocr|mrz|consistency|expiry_age|authenticity|face_match|liveness|
  poa|screening_sanctions|screening_pep_media|fraud_signals|…`),
  provider, status (`pass|fail|unclear|not_run|error`), findings (JSONB,
  structured, no raw PII beyond need), confidence, started/finished_at,
  attempt_no.
- **decisions** — id, session_id, outcome (`approved|rejected|
  needs_review|needs_more_information`), decided_by (`engine|reviewer|
  platform`), reviewer_id nullable, reason_codes (array), notes,
  rules_version. **Rules version is stored with every decision** so a
  past decision can be re-explained under the rules that made it.
- **cases** (review work) — id, session_id, tenant_id, assigned_to,
  locked_by/at, sla_due_at, priority, resolution → decision_id,
  four_eyes_required, second_reviewer_id.
- **screening_hits** — id, check_id, list_source, 🔒 matched name/DOB,
  match_score, disposition (`false_positive|confirmed|pending`),
  disposed_by/at. Pending hits block auto-approval.

## Platform

- **webhook_deliveries** — id, endpoint_id, event, payload (decision data
  only, no images), status, attempts, next_retry_at, response summary.
- **audit_log** — append-only: id, actor (type+id), tenant_id,
  action, target (type+id), reason, metadata, at. *No updates, no deletes,
  enforced in the database.*
- **retention_jobs / deletions** — what was deleted, when, under which
  rule or request; deletion is itself audited (the record of deletion
  contains no deleted PII).
- **usage_records** — per-session billable events (level, outcome class,
  add-ons) feeding invoicing; no charge for expired-untouched or
  our-error sessions (BLUEPRINT §10).

## KYB (Phase 3)

- **businesses** — id, tenant_id, 🔒 legal name, registration number,
  country, registry status/findings, registered address.
- **business_people** — business_id, applicant_id (each director/UBO is a
  normal applicant at Level 2+), role (`director|ubo`), 🔒 ownership %.

## Invariants (enforced, not hoped)

1. A session cannot reach `approved` while any required check is
   `not_run`, `error`, or `unclear`, or any screening hit is `pending`.
2. A decision always references the exact check rows it was made from.
3. Deleting applicant PII leaves the audit skeleton (ids, timestamps,
   outcomes) intact but unrecoverable as identity.
4. Test-env rows can never be read by live keys, and vice versa.
