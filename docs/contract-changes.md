# Contract Changes

Phase 1 freezes the database schema, the rule JSON schema, and the OpenAPI
spec. Later phases change them ONLY through a numbered note here plus a
forward-only Alembic migration (and, for API changes, a regenerated frozen
OpenAPI spec).

## Log

### CC-1 (2026-10-14, Phase 3) — school assessments + USSD sessions + assessment-mode evaluation

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
