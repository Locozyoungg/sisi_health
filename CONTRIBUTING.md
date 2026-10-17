# Contributing to SISI Health

Thanks for helping. SISI Health is a women's chronic gynecological health
platform built for Kenyan schools and clinics: a private symptom diary, a
**deterministic** triage engine that never diagnoses, a school programme over
USSD/WhatsApp, and a specialist referral corridor.

Two things make contributing here different from an ordinary web project:

1. **It handles minors' health data.** Every contribution must preserve the
   safety and privacy invariants in [`AGENTS.md`](./AGENTS.md) and
   [`docs/SPEC.md`](./docs/SPEC.md) §1–3.
2. **It is clinically reviewed.** Rules, red-flag patterns, and education
   content ship as drafts with `clinically_validated: false` until a licensed
   Kenyan clinician signs them off. Do not present a draft as validated, and do
   not enable unvalidated rules outside dev/demo.

Read [`docs/rule-change-sop.md`](./docs/rule-change-sop.md) before touching
anything under `/ontology/rules`, `/ontology/redflags`, or
`/ontology/golden`.

## Ground rules (non-negotiable)

1. **Never commit real patient data.** Synthetic data only — in tests, fixtures,
   seeds, screenshots, logs, issues, and PR descriptions. The seed scripts
   generate synthetic users; keep it that way.
2. **The LLM never assigns a band.** Bands and condition indicators come from
   the deterministic rules engine; model output only explains them. A change
   that lets a model set, change, or contradict a band is rejected.
3. **Nothing condition-identifying in notifications, SMS, USSD screens,
   filenames, notification previews, or crash reports.** There are string lints
   for this — keep them passing.
4. **Tests come with the change.** A failing red-flag or band test blocks a
   merge, always.
5. **No secrets in the repo.** `.env.example` is the only committed env file;
   CI runs `gitleaks` and `pip-audit`.
6. **Migrations are forward-only** and every migration carries a rollback note.
7. **Schema, rule-schema, or API changes need a numbered note** in
   [`docs/contract-changes.md`](./docs/contract-changes.md) plus a migration.
8. **Be decent.** Harassment, discriminatory language, and dismissive conduct
   are not acceptable here — many contributors and users are minors and health
   workers. Report concerns to the maintainers privately.

## Setup

### Windows (the primary development path)

`make` is not installed on the reference machine; `make.ps1` is the wrapper for
the same tasks.

```powershell
.\make.ps1 setup          # Python 3.12 venv + backend[dev] install
.\make.ps1 db-up          # Docker Postgres+Redis if Docker is available,
                          # otherwise the portable PostgreSQL under .tools/
.\make.ps1 migrate        # alembic upgrade head
.\make.ps1 seed           # synthetic demo data (safe to re-run; idempotent)
```

| Task | Command |
|---|---|
| Backend unit + integration tests | `.\make.ps1 test` |
| Coverage (fails under 70%) | `.\make.ps1 coverage` |
| Lint (backend) | `.\make.ps1 lint` |
| Types (backend, `mypy app`) | `.\make.ps1 typecheck` |
| USSD/WhatsApp gateway tests | `.\make.ps1 ussd-test` |
| AI service tests | `.\make.ps1 ai-test` |
| AI guardrail eval (177 cases: 157 + 20 cervical) | `.\make.ps1 ai-eval` |
| Android unit tests (golden parity, vault, property tests) | `.\make.ps1 android-test` |
| Web Playwright e2e (needs the backend running on :8000) | `.\make.ps1 web-test` |
| Audit chain verification | `.\make.ps1 audit-verify` |
| Encrypted DB backup / restore drill | `.\make.ps1 backup` / `.\make.ps1 restore` |
| OpenAPI export (`docs/openapi.yaml`) | `.\make.ps1 openapi` |

### Linux / CI

```bash
make setup db-up migrate seed
make test coverage lint typecheck
```

The Makefile currently covers the backend, AI service, backups, and the
`phase5-demo` / `phase7-demo` Playwright flows. It has **no** dedicated targets
for the USSD/WhatsApp gateway tests, a standalone web e2e run, or Android — run
those directly:

```bash
cd ussd-whatsapp && ../backend/.venv/bin/python -m pytest
cd ai_service    && ../backend/.venv/bin/python -m pytest
cd web           && npm install && npx playwright install chromium && npm run e2e
cd mobile        && ./gradlew testDebugUnitTest
```

### Per-service environment notes

- **Backend** (`/backend`): Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2.
  PostgreSQL 16 required; `pgvector` is optional (migration 0007 branches).
- **USSD/WhatsApp gateway** (`/ussd-whatsapp`): installed into the backend venv
  (`.\make.ps1 ussd-setup`); Redis is the primary session store, with the
  Postgres fallback (`SISI_USSD_SESSION_BACKEND=auto`) used when Redis is
  absent (assumption A19).
- **AI service** (`/ai_service`): `.\make.ps1 ai-setup`. Dev/demo run
  deterministic **stub** LLM/embedding providers; staging/prod refuse to boot
  with stubs. Never commit provider credentials (assumption A33).
- **Web** (`/web`): React + Vite on :5173, proxying `/v1` to the backend on
  :8000; `npm run e2e` runs Playwright.
- **Android** (`/mobile`): the portable toolchain (JDK 17, Android SDK, Gradle
  8.9) lives under `.tools/` and is wired by `scripts/android.ps1`. The Kotlin
  engine reads the *same* `/ontology` JSON as the server — a Gradle `Sync` task
  copies `rules/`, `golden/`, `redflags/`, and `schema/` into the app assets on
  every build. Golden parity is enforced by tests on both sides.

## What CI runs (and therefore what your PR must satisfy)

| Job | Gate |
|---|---|
| `test` | ruff + mypy (`backend`), `pytest --cov=app --cov=app.rules --cov-fail-under=70`, `pip-audit`, `gitleaks` |
| `gateway` | ruff + mypy + pytest in `ussd-whatsapp` (e2e journeys, timeout/resume, 160-char lint, consent paths) |
| `ai` | ruff + mypy + pytest in `ai_service`, then `scripts/eval_guardrails.py --ci`: ≥150 cases, **100% red-flag routing**, every answer cites a chunk, no marker leaks |
| `android` | `gradlew testDebugUnitTest`, release build, APK ≤ 25 MB |

`mypy` runs with `disallow_untyped_defs`, and **strict mode on
`app.rules` and `app.consent`** — annotate those packages fully.

## Pull request rules

1. One concern per PR; keep the diff reviewable (bug fixes stay scoped to the
   bug).
2. State what safety/privacy surface the change touches — band assignment, red
   flags, consent, minors' data, channels, audit, encryption. Say "none" if
   none.
3. Add or update tests. New triage behaviour needs a golden case that
   distinguishes it from the previous behaviour.
4. Update the docs you invalidate: `/docs/role-matrix.md` for permission
   changes, `/docs/data-dictionary.md` for schema changes,
   `/docs/contract-changes.md` for frozen-contract changes,
   `/docs/assumptions.md` for any judgement call affecting safety, privacy,
   cost, or the database.
5. Do not re-format unrelated files; keep generated artefacts
   (`docs/openapi*.yaml`, `docs/clinician-review-packet.md`) regenerated only
   when their source changed.
6. Commit messages follow the repository convention:
   `feat|fix|refactor|docs|test|chore|perf|ci: <description>`.

## Where help is most useful

- **Translations and content**: Kiswahili review, plus Luo, Kalenjin, and
  Somali stubs, in `/ontology/content`.
- **Rule evidence**: finding and citing published guidance for a threshold
  (a clinician still signs it).
- **Accessibility**: TalkBack labels, large text, low-literacy icon mode.
- **Tests**: property tests for sync merge, k-anonymity differencing attacks,
  guardrail cases in Swahili/Sheng.
- **Docs**: the templates in `/docs/templates` need real-world adoption
  feedback.

## License and attribution

- **Code: MIT** — see [`LICENSE`](./LICENSE).
- **Ontology and content (`/ontology`): CC-BY 4.0** — see
  [`ontology/LICENSE`](./ontology/LICENSE). By contributing content or
  ontology data you agree to license it under CC-BY 4.0, with attribution to
  Kairon Technologies Limited and the SISI Health project.

Copyright © 2026 Kairon Technologies Limited.
