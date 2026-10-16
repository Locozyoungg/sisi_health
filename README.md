# SISI Health

Women's chronic gynecological health platform for Kenya — private symptom
tracker, deterministic AI triage, "Period-Friendly School" program, and a
specialist referral corridor. Built by **Kairon Technologies Limited** for
review by UNICEF's Venture Fund and deployment in real Kenyan schools.

**SISI supports you and your doctor — it does not diagnose.**

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend core, deterministic rules engine, audit trail, consent/erasure | ✅ **Complete** — 111 tests, 91% coverage, demo 13/13 |
| 2 | Consumer Android app (offline diary, pattern engine, privacy vault) | ✅ **Complete** — 39 tests incl. golden parity, release APK 15.0 MB |
| 3 | USSD + WhatsApp assessment flows | ✅ **Complete** — 36 gateway tests, demo green |
| 4 | School nurse console, dashboards, M-Pesa vouchers | ✅ **Complete** — 55 k-anon property tests + school/voucher suites, 3 Playwright e2e |
| 5 | Specialist corridor (+ cervical screening module) | ✅ **Complete** — 423 backend tests (186 new), 4 corridor Playwright e2e, 37 golden cases on both engines |
| 6 | AI conversation layer with RAG + guardrails | ✅ **Complete** — 260 ai-service tests, 150-case guardrail suite (100% pass, +20 cervical cases), 100% red-flag routing, 92-chunk RAG index, stub comparison report (real run = H15) |
| 7 | Employer admin (minimal) | ⏳ Next |
| 8 | Hardening: pen-test checklist, load test, deploy | ⏳ |

## Monorepo

| Path | Purpose |
|---|---|
| `/backend` | FastAPI API, deterministic rules engine, hash-chained audit trail, consent/erasure, DSR, school module, specialist corridor + cervical screening (Python 3.12, PostgreSQL 16) |
| `/ontology` | Open-source symptom ontology: rule JSON, red-flag patterns (en/sw/sheng), golden parity cases, screening schedule config, education content, cervical guardrail cases (CC-BY 4.0) |
| `/mobile` | Android app: offline-first diary (Room + SQLCipher), Kotlin engine (same JSON rules as the server), privacy vault, discreet alias |
| `/ussd-whatsapp` | USSD (`*XXX#`) + WhatsApp assessment gateway (Africa's Talking sandbox contract, resumable sessions, 160-char screen lint) |
| `/web` | Staff console: school nurse queue, dashboards, vouchers, corridor queue, consults, referrals, surgery + follow-up trackers, facilities (React + Vite + Playwright e2e) |
| `/docs` | SPEC, assumptions, contract changes, human tasks, role matrix, hazard log, OpenAPI (frozen), clinician review packet |
| `/ai_service` | AI conversation layer: LLM + RULES endpoints, RAG over the CC-BY content library (pgvector with JSONB fallback), deterministic guardrails (red-flag routing, post-filter, citations), 150-case eval harness |

## Quick start — backend (Phase 1)

```powershell
# Windows: PowerShell wrapper (uses portable PostgreSQL; no Docker needed)
.\make.ps1 setup        # create venv + install backend
.\make.ps1 db-up        # portable PostgreSQL 16 at .tools/ (auto-inits on first run)
.\make.ps1 demo-phase1  # migrate + seed synthetic data + 13-step live demo
.\make.ps1 test         # 423 tests
```

```bash
# Linux / CI: plain make + Docker
make setup db-up demo-phase1
```

## Specialist corridor demo (Phase 5)

```powershell
.\make.ps1 db-up                     # portable PostgreSQL (idempotent)
.\make.ps1 migrate                   # migrations 0001-0008
.\make.ps1 web-setup                 # npm install + Playwright chromium
# start the backend manually on :8000, then:
.\make.ps1 phase5-demo               # corridor seed (synthetic) + Playwright e2e:
                                     # booking→review→consult→referral flow,
                                     # patient-approval gating, facility staleness
```

## AI conversation layer demo (Phase 6)

```powershell
.\make.ps1 db-up                     # portable PostgreSQL (JSONB fallback branch)
.\make.ps1 migrate                   # migrations 0001-0008
.\make.ps1 ai-setup                  # pip install -e ai_service[dev]
.\make.ps1 ai-demo                   # scripted en/sw/sheng conversation through the
                                     # real pipeline: red-flag routing to the urgent
                                     # script + hotlines, minor gating, citations,
                                     # injection blocked, rules/evaluate parity
.\make.ps1 ai-eval                   # 170-case guardrail suite (150 + 20 cervical)
.\make.ps1 ai-compare                # hosted-vs-open-weight STUB RUN report
```

## Quick start — Android app (Phase 2)

```powershell
.\scripts\android.ps1 testDebugUnitTest   # 39 tests: golden parity, property tests, vault
.\scripts\android.ps1 assembleRelease     # R8-minified release
.\make.ps1 android-size                   # release build + 25 MB budget check (currently 15.0 MB)
```

The Android toolchain is fully portable (JDK 17, Android SDK, Gradle 8.9 under
`.tools/`, gitignored) — `scripts/android.ps1` wires `JAVA_HOME`,
`ANDROID_HOME`, and `GRADLE_USER_HOME` (cache on E:).

## Safety architecture (how the non-negotiables are enforced)

| Non-negotiable | Enforcement |
|---|---|
| Rules engine assigns every band; the LLM never does | `backend/app/rules/` + `mobile/.../engine/` run the **same JSON** from `/ontology`; golden parity tests on both sides; LLM endpoints (Phase 6) are explain-only by contract |
| Synthetic data only | Synthetic-only seeders/fixtures; CI + demo use generated data |
| Every rule ships `clinically_validated: false` until a Kenyan clinician signs off | Validator enforces empty sign-off fields; the engine refuses unvalidated rules unless `ALLOW_UNVALIDATED_RULES` (dev/demo only); two-person activation workflow with a golden-suite gate |
| Nothing condition-identifying in notifications/SMS/USSD/app-switcher | `StringsPrivacyTest` scans app strings; backend channel limits; discreet launcher alias ("Notes") |
| Minors' raw symptom data invisible outside the clinical corridor | RBAC matrix + encrypted diary schema; school staff see bands only; corridor endpoints decrypt computed feature snapshots only — raw diary ciphertext is never opened, and every case view writes an audit entry (Phase 5) |
| UTC storage / Nairobi display; UUIDv7 only | `core/time`, `core/ids` (Python) + `Uuid7` (Kotlin), tested |
| Secrets never in the repo | `.env.example` only; gitleaks in CI |
| Tests before done; failing band test blocks merge | CI gates (backend + Android jobs) |
| Unspecified safety/privacy/cost/DB questions go to the maintainer | `/docs/assumptions.md` A1–A31, every entry recorded before coding |

See `/docs/SPEC.md` for the full build specification, `/AGENTS.md` for the
session protocol, and `/docs/contract-changes.md` for frozen-contract changes.

## License

Code: MIT. Ontology and content: CC-BY 4.0.
Copyright © 2026 Kairon Technologies Limited. See `/LICENSE` and
`/ontology/LICENSE`.
