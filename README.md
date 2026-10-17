# SISI Health

**Private, offline-first gynecological health for Kenyan girls and women.**
Chronic conditions — endometriosis, PCOS, uterine fibroids, chronic pelvic pain
— are not pregnancy, and they are chronically under-diagnosed. SISI Health
gives a girl or woman a private way to track symptoms, a deterministic triage
engine that tells her what to do next, a school programme she can reach from a
feature phone, and a corridor into specialist care.

**SISI supports you and your doctor — it does not diagnose.**

Built by **Kairon Technologies Limited**, designed for review by UNICEF's
Venture Fund and for deployment in real Kenyan schools and clinics. Code is
MIT-licensed; the symptom ontology, rules, and education content are CC-BY 4.0.

## Why it looks the way it does

- **The users are minors.** Under-13s are blocked; 13–17-year-olds use guardian
  consent plus their own recorded assent; discreet mode, decoy mode, and
  quick-exit exist for every user and are never disabled by a guardian. Nothing
  condition-identifying appears in a notification, an SMS, a USSD screen, or an
  app-switcher preview.
- **Phones are shared and data is expensive.** The school channel runs over
  USSD and WhatsApp, is resumable for five minutes, shows no results history on
  the handset, and tells the user how to clear the call log.
- **Band assignment is a clinical claim.** A deterministic rules engine — not a
  language model — assigns every severity band and every condition indicator.
  The LLM layer explains what the engine decided, cites reviewed content, and
  is rejected if it contradicts the engine.
- **Uncertainty escalates, it never reassures.** A missing red-flag input counts
  as *matched*; a minor reporting post-coital bleeding is floored at ORANGE and
  flagged for safeguarding; "not enough data" is never an all-clear.
- **Nothing clinical is live until a Kenyan clinician signs it.** Rules,
  red-flag scripts, and content ship with `clinically_validated: false` and
  empty sign-off fields; staging/prod refuse to boot with unvalidated rules
  enabled.
- **No real patient data exists in this repository.** Every user, diary,
  assessment, consult, and voucher in seeds, tests, and demos is synthetic.

## Three layers

| Layer | What it does | Where it lives |
|---|---|---|
| 1 — Private tracker + triage | Offline diary, on-device pattern engine, plain-language next steps, clinic-ready PDF summary | `/mobile`, `/backend`, `/ontology` |
| 2 — Period-Friendly School | USSD/WhatsApp self-assessment, nurse flag queue (pseudonyms and bands only), guardian consent, RED-only guardian alerts, vouchers, aggregate school dashboard | `/ussd-whatsapp`, `/backend`, `/web` |
| 3 — Specialist corridor | Nurse review → gynecologist telehealth (one-time, unrecorded rooms) → patient-approved referral letters → surgery and follow-up navigation → cervical screening tracker | `/backend`, `/web` |

## Monorepo

| Path | Purpose |
|---|---|
| `/backend` | FastAPI API, deterministic rules engine, hash-chained audit trail, consent/erasure, DSR, school module, specialist corridor + cervical screening, employer module (Python 3.12, PostgreSQL 16) |
| `/ontology` | Open-source symptom ontology: rule JSON, red-flag patterns (en/sw/sheng), golden parity cases, screening schedule config, education content, guardrail cases (CC-BY 4.0) |
| `/mobile` | Android app: offline-first diary (Room + SQLCipher), Kotlin engine running the same JSON rules, privacy vault, discreet launcher alias |
| `/ussd-whatsapp` | USSD (`*XXX#`) + WhatsApp assessment gateway (Africa's Talking contract, resumable sessions, 160-char screen lint) |
| `/web` | Staff console: nurse queue, dashboards, vouchers, corridor queue, consults, referrals, surgery + follow-up trackers, facilities, employer dashboard (React + Vite + Playwright) |
| `/ai_service` | AI conversation layer: LLM + RULES endpoints, RAG over the CC-BY content library (pgvector with JSONB fallback), deterministic guardrails, eval harness |
| `/docs` | SPEC, architecture, data flow, runbooks, templates, hazard log, assumptions, role matrix, frozen OpenAPI |
| `/scripts` | Portable tooling: `android.ps1`, `pg_local.ps1`, `backup_db.py`, `restore_db.py` |

## Architecture at a glance

FastAPI backend on :8000 · USSD/WhatsApp gateway on :8001 · AI service on :8002
· React console on :5273 (dev) · PostgreSQL 16 with two optional `pgvector`
branches · Redis for sessions and jobs. The Kotlin engine and the Python engine
execute **the same** `/ontology` JSON, with golden-file parity tests on both
sides. Full diagrams: [`docs/architecture.md`](docs/architecture.md); the data
journey with its encryption and audit points:
[`docs/data-flow.md`](docs/data-flow.md).

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend core, deterministic rules engine, audit trail, consent/erasure | ✅ **Complete** — 111 tests, 91% coverage, demo 13/13 |
| 2 | Consumer Android app (offline diary, pattern engine, privacy vault) | ✅ **Complete** — 39 tests incl. golden parity, release APK 15.0 MB |
| 3 | USSD + WhatsApp assessment flows | ✅ **Complete** — 36 gateway tests, demo green |
| 4 | School nurse console, dashboards, M-Pesa vouchers | ✅ **Complete** — 55 k-anon property tests + school/voucher suites, 3 Playwright e2e |
| 5 | Specialist corridor (+ cervical screening module) | ✅ **Complete** — 423 backend tests (186 new), 4 corridor Playwright e2e, 37 golden cases on both engines |
| 6 | AI conversation layer with RAG + guardrails | ✅ **Complete** — 292 ai-service tests, 177-case guardrail suite (157 + 20 cervical), 100% red-flag routing, minor two-step flow, stub comparison report (real run = H15) |
| 7 | Employer admin (minimal) | ✅ **Complete** — employer wallet + ledger invariants + k-anon dashboard, 467 backend tests, 9 Playwright e2e |
| 8 | Hardening: pen-test checklist, load test, restore drill, deploy, full docs | 🔄 **In progress** — rate limiting + retention purge, encrypted backup/restore with a recorded drill, prod compose + deploy assets, docs bundle and README (this file). Final gate pending |

Phase 8's Deploy, load-test, and penetration-test items are shipped as scripts,
checklists, and self-assessment; the real VPS, registry, and third-party test
remain human tasks — see [`docs/human-tasks.md`](docs/human-tasks.md).

## Safety architecture (how the non-negotiables are enforced)

| Non-negotiable | Enforcement |
|---|---|
| Rules engine assigns every band; the LLM never does | `backend/app/rules/` + `mobile/.../engine/` run the **same JSON** from `/ontology`; golden parity tests on both sides; the AI service is explain-only by contract and its post-filter rejects any band that differs from the engine's |
| Synthetic data only | Synthetic-only seeders and fixtures; CI and demos generate data; no real patient data anywhere |
| Every rule ships `clinically_validated: false` until a Kenyan clinician signs off | Validator enforces empty sign-off fields; the engine refuses unvalidated rules unless `SISI_ALLOW_UNVALIDATED_RULES=true` (dev/demo only, refused in staging/prod); two-person activation with a golden-suite gate and instant rollback |
| Nothing condition-identifying in notifications/SMS/USSD/app-switcher | Gateway and app string lints; generic channel wording; discreet launcher alias ("Notes"); no results history on the handset |
| Minors' raw symptom data invisible outside the clinical corridor | RBAC matrix + separately encrypted diary schema; school staff see bands and pseudonyms only; corridor endpoints decrypt a computed-feature snapshot only — raw diary ciphertext is never opened, and every case view writes an audit entry |
| Red-flag text always gets the urgent script first | Deterministic multi-language pattern matching runs before any model call; the urgent script carries the hotlines from config (116 / 1195, currently marked **UNVERIFIED** — human task H9) |
| Safeguarding outranks family notification | Abuse, sexual violence, pregnancy concern in a minor, self-harm, or guardian-risk signals suppress the guardian alert (recorded as `skipped_safeguarding`) and route to the designated safeguarding lead |
| UTC storage / Nairobi display; UUIDv7 only | `core/time`, `core/ids` (Python) + `Uuid7` (Kotlin), tested |
| Secrets never in the repo | `.env.example` only; `gitleaks` + `pip-audit` in CI |
| Tests before done; a failing band test blocks the merge | CI gates (backend, gateway, AI, Android jobs) |
| Unspecified safety/privacy/cost/DB questions go to the maintainer | `/docs/assumptions.md` A1–A40, every entry recorded before coding |

## Quick start

### Backend

```powershell
.\make.ps1 setup          # create the venv + install backend[dev]
.\make.ps1 db-up          # Docker Postgres+Redis if available, else portable PostgreSQL
.\make.ps1 migrate        # alembic upgrade head (forward-only migrations)
.\make.ps1 seed           # synthetic demo data (idempotent)
.\make.ps1 test           # backend suite (467 tests)
.\make.ps1 demo-phase1    # migrate + seed + a 13-step live demo
```

```bash
# Linux / CI
make setup db-up migrate seed test
```

Useful backend targets: `lint`, `typecheck`, `coverage`, `audit-verify`,
`backup`, `restore`, `openapi`, `db-local`, `db-down`, `clean`
(`.\make.ps1 help` lists them).

### USSD + WhatsApp gateway

```powershell
.\make.ps1 ussd-setup     # install the gateway into the backend venv
.\make.ps1 ussd-test      # 36 gateway tests (journeys, resume, 160-char lint, consent)
.\make.ps1 ussd-demo      # full English + Kiswahili journeys through the real engine
```

### AI conversation layer

```powershell
.\make.ps1 ai-setup       # pip install -e ai_service[dev]
.\make.ps1 ai-test        # 292 ai-service tests
.\make.ps1 ai-demo        # scripted en/sw/sheng conversation: red-flag routing to the
                          # urgent script + hotlines, minor gating, citations,
                          # injection blocked, rules/evaluate parity
.\make.ps1 ai-eval        # guardrail suite (157 cases + 20 cervical)
.\make.ps1 ai-compare     # hosted-vs-open-weight STUB RUN report (real run = H15)
```

### Staff console (web)

```powershell
.\make.ps1 db-up
.\make.ps1 migrate
.\make.ps1 web-setup      # npm install + Playwright chromium
# start the backend on :8000 yourself, then:
.\make.ps1 web-test       # 9 Playwright e2e specs
.\make.ps1 phase4-demo    # school world: seed + e2e (queue, k-anon dashboard, vouchers)
.\make.ps1 phase5-demo    # corridor: seed + e2e (booking → review → consult → referral,
                          # patient-approval gating, facility staleness)
.\make.ps1 phase7-demo    # employer: seed + e2e (wallet + ledger, k-anonymized cells
                          # suppressed as "—", role alert for a non-employer role)
```

The employer module is deliberately minimal: a wallet (the Phase 4
`school.wallets` / `school.wallet_ledger` tables with `owner_type='employer'`)
and an aggregate dashboard counting linked employees' evaluations through the
same shared k-anonymity module as the school dashboard — band cells and a total
only, never employee-level data. `core.users.employer_id` is an audited
admin-action opt-in (contract note CC-5).

### Android app

```powershell
.\scripts\android.ps1 testDebugUnitTest   # golden parity, property tests, vault tests
.\scripts\android.ps1 assembleRelease     # R8-minified release
.\make.ps1 android-size                   # release build + 25 MB budget check (currently 15.0 MB)
```

The Android toolchain is fully portable (JDK 17, Android SDK, Gradle 8.9 under
`.tools/`, gitignored) — `scripts/android.ps1` wires `JAVA_HOME`,
`ANDROID_HOME`, and `GRADLE_USER_HOME`.

## Documentation

| Document | What it answers |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | The full build specification (the source of truth) |
| [`AGENTS.md`](AGENTS.md) | The non-negotiables every session loads |
| [`docs/architecture.md`](docs/architecture.md) | Services, schemas, trust boundaries, encryption, key flows |
| [`docs/data-flow.md`](docs/data-flow.md) | The data journey with encryption and audit annotations |
| [`docs/rule-change-sop.md`](docs/rule-change-sop.md) | How a rule change is drafted, signed, activated, and rolled back |
| [`docs/breach-runbook.md`](docs/breach-runbook.md) | 72-hour ODPC notification, evidence preservation, tabletop drill |
| [`docs/hazard-log.md`](docs/hazard-log.md) · [`docs/templates/clinical-safety-case.md`](docs/templates/clinical-safety-case.md) | Clinical hazards and the safety case template |
| [`docs/templates/safeguarding-policy.md`](docs/templates/safeguarding-policy.md) | Child-safeguarding policy template (adopt before real pupils) |
| [`docs/templates/dpia-template.md`](docs/templates/dpia-template.md) | Pre-filled DPIA template for the DPO and counsel |
| [`docs/human-tasks.md`](docs/human-tasks.md) | Everything a human must do (signing, providers, VPS, pentest) |
| [`docs/role-matrix.md`](docs/role-matrix.md) · [`docs/assumptions.md`](docs/assumptions.md) · [`docs/contract-changes.md`](docs/contract-changes.md) | RBAC per endpoint, recorded assumptions, frozen-contract changes |
| [`docs/data-dictionary.md`](docs/data-dictionary.md) · [`docs/impact-metrics.md`](docs/impact-metrics.md) · [`docs/technical-summary.md`](docs/technical-summary.md) · [`docs/cost-model.md`](docs/cost-model.md) | Grant-package artefacts (definitions, tables, one-pager, cost model) |
| [`docs/openapi.yaml`](docs/openapi.yaml) · [`docs/openapi-ai.yaml`](docs/openapi-ai.yaml) | Frozen OpenAPI specs (backend + AI service) |
| [`docs/clinician-review-packet.md`](docs/clinician-review-packet.md) · [`docs/ai-comparison-report.md`](docs/ai-comparison-report.md) · [`docs/backup-restore-drill.md`](docs/backup-restore-drill.md) | Review packet, AI comparison (stub run), restore drill record |

## Roadmap

Phases 1–7 are complete (see the status table). Phase 8 closes hardening:
penetration-test checklist and ASVS mapping, a 1,000-concurrent-session USSD
load test, backup/restore drill, one-command deploy for staging and prod, SBOM
and dependency pinning, retention purge, auth rate limiting, and the docs
bundle you are reading. After that, the path to a pilot runs through the human
tasks: clinician sign-off (H7), ODPC registration and a signed DPIA (H5), the
third-party penetration test (H8), provider go-lives (H2–H4), the VPS (H17),
and ethics approval for the validation study (H11).

## Contributing

Contributions are welcome — setup, test commands per service, PR rules, and the
non-negotiables are in [`CONTRIBUTING.md`](CONTRIBUTING.md). The short version:
synthetic data only, never let a model assign a band, tests before merge, and
never present an unsigned rule as clinically validated. Rule changes follow
[`docs/rule-change-sop.md`](docs/rule-change-sop.md).

## Support

- Questions and bugs: open an issue in this repository (no patient data, no
  secrets, no personal health information — ever).
- Security reports: do **not** open a public issue; contact the maintainers
  privately and follow [`docs/breach-runbook.md`](docs/breach-runbook.md) if
  personal data may be affected.
- Clinical questions: addressed to the reviewing clinician via the review
  packet, not through code review.

## License

Code: **MIT** — see [`LICENSE`](LICENSE). Ontology and content: **CC-BY 4.0** —
see [`ontology/LICENSE`](ontology/LICENSE).
Copyright © 2026 Kairon Technologies Limited.
