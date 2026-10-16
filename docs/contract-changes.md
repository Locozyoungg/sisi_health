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

### CC-3 (2026-10-15, Phase 5) — specialist corridor + cervical screening & navigation

- **Migration 0005** adds schema `corridor` (spec 5.4 + 5.4.1):
  - consult requests/sessions/consents (`consult_requests`,
    `consult_events`, `consult_sessions` — `recorded` CHECKed False,
    `consult_consents`), with envelope-encrypted computed-features snapshots
    (corridor code never opens raw diary ciphertext — non-negotiable 5)
  - facility directory `facilities` with screening fields (`screening_tests`,
    opening hours, cost estimates, `last_verified_at` for the 90-day staleness
    flag)
  - `referrals` + `sharing_approvals` (patient-approved sections, revocable)
  - surgery navigation: `surgery_cases`, `surgery_events`, `pricing_stubs`
    (`indicative` CHECKed True, `source` required), `outcome_logs`
  - cervical follow-up tracker: `follow_up_tracker` (status-only; no
    results-detail column exists), `tracker_events`, `reminders` (generic
    message keys only, idempotent per user/kind/due date)
- **Rule schema**: the closed `condition` enum gains `postcoital_bleeding`,
  `intermenstrual_bleeding`, `postmenopausal_bleeding`, `persistent_discharge`
  (4 new draft red-flag rules in `/ontology/rules`, all
  `clinically_validated: false`, min band ORANGE).
- **Diary payload schema**: `symptoms` gains `postcoital_bleeding`,
  `intermenstrual_bleeding`, `postmenopausal_bleeding`, `unusual_discharge`
  (18+/45+ collection gating per the dyspareunia precedent: server validates
  shape, app gates collection).
- **Engine**: `RULE_SET_VERSION` → `ontology-1.1` in both engines; golden
  file → 1.1.0 (37 cases). New invariant in both engines: a minor
  (`age < self_consent_age`) with `postcoital_bleeding_signal` sets
  `safeguarding` and floors the band at ORANGE (spec 5.4.1, hazard C5). New
  rules are `red_flag: true` with ORANGE output, so `urgent` becomes true for
  cervical ORANGE flags (conservative, upward — documented in hazard log C2);
  guardian alerts still key on band == RED only.
- **RBAC**: new `corridor:*` permissions (queue, consults, referrals, surgery,
  facilities read/write, tracking, aggregates, education:read, reminders);
  roles extended in `docs/role-matrix.md`. MOH_VIEWER gains
  `corridor:aggregates`.
- **OpenAPI**: regenerated for the new `/v1/corridor/*` surface (backend
  OpenAPI v3 frozen in `docs/openapi.yaml`).

### CC-4 (2026-10-15, Phase 6) — AI conversation layer RAG tables (conditional pgvector)

- **Migration 0007** adds schema `ai`: `content_chunks` (deterministic chunk
  ids `{slug}#{n}`, unique) and `chunk_embeddings`. The embedding column is
  `vector(768)` + ivfflat cosine index when the pgvector extension is available
  on the server, else JSONB (Python brute-force cosine — documented fallback).
  The migration gates on `pg_available_extensions`; `CREATE EXTENSION IF
  EXISTS` alone would error when the extension is unavailable.
- **Embedding writes are raw-SQL casts only** (`CAST(:emb AS vector|jsonb)`) so
  one code path serves both modes; the ORM models are metadata-only.
- **CI**: the `test` job and the new `ai` job use
  `pgvector/pgvector:pg16-alpine` (vector branch); the `gateway` job keeps
  plain `postgres:16-alpine` (JSONB branch). Both branches are CI-covered.
- **AGENTS.md §2** DB schemas row gains `ai` (approved with this phase).
- **OpenAPI**: the new service exports `docs/openapi-ai.yaml` (backend
  OpenAPI unchanged).

### CC-5 (2026-10-16, Phase 7) — employer admin (minimal): wallet + aggregate dashboard

- **Migration 0009** adds (spec build order item 7 — "employer admin (future
  revenue) — minimal: wallet + aggregate dashboard"):
  - `core.employers` (name, county, status)
  - `core.employer_staff` (staff → employer binding, unique per pair) — the
    own-scoping surface an `employer_admin` is limited to
  - `core.users.employer_id` — nullable FK (`ON DELETE SET NULL`): the
    admin-action opt-in link that lets the dashboard count a sponsor's own
    employees; set explicitly by a super_admin and audited.
- **No new wallet schema**: employer wallets reuse the Phase 4
  `school.wallets` / `school.wallet_ledger` with `owner_type='employer'` (CC-2),
  through `app.school.service.fund_wallet`. The ledger stays append-only.
- **Aggregates**: the employer dashboard passes through the same shared
  `app/k_anon.py` module as the school dashboard (cells < 5 suppressed with
  complementary suppression; below 20 linked employees the answer is
  `not_enough_data`, never a zero). It publishes band cells and a total only —
  never employee-level data.
- **RBAC**: `EMPLOYER_ADMIN` is activated with exactly
  `employer:wallet` + `employer:dashboard`; `SUPER_ADMIN` gains
  `employer:admin` (create employer, bind staff, fund) plus the two reads.
  Role matrix doc updated with the permission rows + the Phase 7 data classes.
- **OpenAPI**: regenerated for the new `/v1/employers/*` surface (backend
  OpenAPI v4 frozen in `docs/openapi.yaml`).


