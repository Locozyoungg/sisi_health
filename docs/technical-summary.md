# SISI Health — Technical Summary (one page)

**One line.** A privacy-first platform for chronic gynecological conditions
(endometriosis, PCOS, uterine fibroids, chronic pelvic pain) in Kenyan girls and
women — a private encrypted symptom diary, a deterministic triage engine that
never diagnoses, a school programme reachable by USSD/WhatsApp, and a
specialist referral corridor.

**One sentence of clinical honesty:** *SISI supports you and your doctor — it
does not diagnose.*

## The problem

Chronic gynecological conditions in Kenya go undiagnosed for years. Girls miss
school for pain that is treated as normal; women reach a specialist only after
years of self-management; school staff have no privacy-preserving way to notice
who needs help. Existing tools are smartphone-only, English-only, and built
around pregnancy rather than chronic pain.

## The solution (three layers)

| Layer | What it is | Reach |
|---|---|---|
| 1 — Private tracker | Offline-first Android diary (pain, bleeding, cycle, GI/urinary, fatigue) + deterministic pattern engine + clinic-ready PDF summary | Smartphone users, works offline |
| 2 — Period-Friendly School | 10-question self-assessment over USSD and WhatsApp, school-nurse console with pseudonyms and severity bands, guardian consent flow, RED-only guardian alerts, M-Pesa-linked product vouchers, aggregate school dashboard | Feature phones and shared phones |
| 3 — Specialist corridor | Nurse review → gynecologist telehealth (one-time, unrecorded rooms) → patient-approved referral letters → surgery/follow-up navigation → cervical screening follow-up tracker | Referral and follow-up |

## Architecture in five lines

Monorepo: FastAPI backend (deterministic rules engine, audit trail, consent and
erasure, school/corridor/employer modules) · USSD+WhatsApp gateway · AI service
(RAG + guardrails, explain-only) · React staff consoles · Kotlin app that runs
**the same rule JSON** as the server · PostgreSQL 16 with pgvector and a Redis
session/queue tier. Full diagrams, trust boundaries, and encryption envelopes:
[`docs/architecture.md`](./architecture.md); the data journey with audit points:
[`docs/data-flow.md`](./data-flow.md).

## Safety architecture (the part that matters)

| Invariant | How it is enforced |
|---|---|
| The rules engine assigns **every** band and indicator; the LLM never does | One JSON rule set in `/ontology` executed by a Python engine and a Kotlin engine with golden-file parity; the AI service explains only, cites chunks, and its post-filter rejects any band that differs from the engine's |
| Uncertainty escalates upward | A missing/invalid red-flag input counts as *matched*; band = max of matched rules; a minor reporting post-coital bleeding is floored at ORANGE and flagged for safeguarding |
| Red-flag text always gets the urgent script first | Deterministic multi-language pattern matching runs **before** any model call; the urgent script carries the hotlines (116 / 1195, marked UNVERIFIED until human task H9) |
| Minors' raw symptom data never leaves the clinical corridor | Nurses see pseudonym + band + actions; the corridor decrypts only a computed-feature snapshot; every case view is audited; re-identification needs ORANGE/RED or a contact request, a typed reason, and an audit entry |
| Nothing condition-identifying on a shared phone or in a channel | No history on the handset, generic SMS wording, discreet launcher alias, string lints in the gateway and app |
| Rules are not usable until a clinician signs them | Validator requires empty sign-off fields on drafts; the engine refuses unvalidated rules unless the dev/demo flag is set (staging/prod refuse to boot with it); activation is two-person with a golden-suite gate and instant rollback |
| Accountability | Hash-chained, append-only audit trail written by a DB trigger; nightly verifier; consent events, DSR requests, and erasure are all first-class |

## Stack

Python 3.12 / FastAPI / SQLAlchemy 2 / Pydantic v2 / Alembic (forward-only) ·
PostgreSQL 16 + pgvector · Redis + arq workers · Kotlin + Compose + Room +
SQLCipher + WorkManager · React + TypeScript + Vite + TanStack Query +
Playwright · Docker Compose + Caddy (TLS 1.3) · GitHub Actions CI.

## Status (as of the Phase 8 docs cut)

- Phases 1–7 implemented and green; Phase 8 (hardening: rate limiting, retention
  purge, backups + restore drill, prod deploy assets, load test, SBOM, this docs
  bundle) in progress.
- Test counts from the last full gate run: **backend 467**, **AI service 292**,
  **USSD/WhatsApp gateway 36**, **Android 39**, **web e2e 9** (plus 37 golden
  parity cases on both engines and a 177-case guardrail suite — 157 + 20
  cervical).
- Deferred to humans, by design: clinician sign-off of all rules and content
  (H7), ODPC registration and a signed DPIA (H5), third-party penetration test
  (H8), hotline verification (H9), provider go-lives (H2–H4, H15), and the VPS
  (H17). See [`docs/human-tasks.md`](./human-tasks.md).
- **No real patient data exists anywhere in this repository.** Every user,
  diary, assessment, consult, and voucher is synthetic.

## Numbers a reviewer should sanity-check

| Number | Meaning |
|---|---|
| 12 | triage rules in `/ontology/rules` (5 indicator rules, 4 cervical red flags, 3 general red flags), all `clinically_validated: false` pending sign-off |
| 37 | golden cases that both engines must reproduce identically |
| 63 | red-flag text patterns across English (22), Kiswahili (22), Sheng (19) |
| 177 | guardrail eval cases; the CI gate requires ≥150 with 100% red-flag routing |
| 54 | database tables across 8 schemas (audit is append-only and hash-chained) |
| 0 | model calls made when a red-flag or self-harm signal is detected |

## Read next

[`docs/architecture.md`](./architecture.md) · [`docs/data-flow.md`](./data-flow.md)
· [`docs/hazard-log.md`](./hazard-log.md) · [`docs/templates/clinical-safety-case.md`](./templates/clinical-safety-case.md)
· [`docs/impact-metrics.md`](./impact-metrics.md) · [`docs/cost-model.md`](./cost-model.md)
· [`docs/rule-change-sop.md`](./rule-change-sop.md)
