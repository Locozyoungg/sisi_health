# Contract Changes

Phase 1 freezes the database schema, the rule JSON schema, and the OpenAPI
spec. Later phases change them ONLY through a numbered note here plus a
forward-only Alembic migration (and, for API changes, a regenerated frozen
OpenAPI spec).

## Log

### CC-1 (2026-10-14, Phase 3) — school assessments + USSD sessions + assessment-mode evaluation
- **Migration 0002** adds `diary.school_assessments` (encrypted answers/band)
  and `core.ussd_sessions` (Postgres session fallback); the rules engine gains
  `evaluate_assessment()` (identical band semantics without the 14-day gate).

### CC-2 (2026-10-15, Phase 4) — school module, vouchers, re-identification

- **Migration 0003** adds (school module, spec 5.3):
  - `core.schools`, `core.school_staff` (staff→school binding), `core.students`
    (pseudonym_id is what staff see), `core.student_contact_map` (envelope-
    encrypted name/phone per student — only the re-identify path reads it),
    `core.guardians` (encrypted contact), `core.pharmacies`
  - `school.assessment_actions`, `school.guardian_consents`,
    `school.guardian_alerts`, `school.vouchers`, `school.voucher_redemptions`,
    `school.wallets`, `school.wallet_ledger`, `school.reconciliation_reports`
  - `diary.school_assessments` gains `requested_contact` (student asked to be
    contacted — grounds for re-identification per spec 3.1)
- **RBAC**: new `PHARMACY` role (`vouchers:redeem`); `SCHOOL_ADMIN`/`NURSE`
  gain school-scope permissions (queue read, actions, guardian consent record,
  dashboard read). Role matrix doc updated.
- **k-anonymity**: new shared module `backend/app/k_anon.py` (spec 3.4) —
  all school dashboards pass through it; nothing else may compute aggregates.
- **OpenAPI**: regenerated for the new `/v1/school/*` and `/v1/vouchers/*`
  surface (backend OpenAPI v2 frozen in `docs/openapi.yaml`).

- **Migration 0002** adds:
  - `diary.school_assessments` — one-time USSD/WhatsApp assessments. Health
    answers are envelope-encrypted (per-assessment data key,
    `owner_type='assessment'`); plaintext columns are limited to `phone_hash`,
    `age_band`, `consent_state`, `language`, and timestamps.
  - `core.ussd_sessions` — Postgres-backed session store used as the dev/test
    fallback when Redis is unavailable (assumption A19); the Redis-backed store
    is the primary per spec.
- **Rules engine**: new `evaluate_assessment()` entry point for one-time
  assessments. Identical band semantics and red-flag asymmetry to
  `evaluate()`, but without the 14-diary-day window gate (that gate is a
  diary-pattern rule; a one-time assessment must still produce immediate
  guidance with the same deterministic bands). No rule JSON changes; golden
  parity is unaffected.
- **OpenAPI**: Phase 3 endpoints are served by the separate gateway service
  (`/ussd-whatsapp`) and documented in `docs/openapi-gateway.yaml`; the
  backend OpenAPI is unchanged.
