# SISI Health

Women's chronic gynecological health platform for Kenya — private symptom
tracker, deterministic AI triage, "Period-Friendly School" program, and a
specialist referral corridor. Built for review by UNICEF's Venture Fund and
deployment in real Kenyan schools.

**SISI supports you and your doctor — it does not diagnose.**

## Monorepo

| Path | Purpose | Phase |
|---|---|---|
| `/backend` | FastAPI API, deterministic rules engine, audit trail, consent/erasure | 1 |
| `/ontology` | Open-source symptom ontology: rule JSON, red-flag patterns, golden cases (CC-BY 4.0) | 1 |
| `/docs` | SPEC, assumptions, contract changes, human tasks, role matrix, hazard log | 1 |
| `/mobile` | Android app (offline-first diary, pattern engine, privacy vault) | 2 |
| `/ussd-whatsapp` | USSD + WhatsApp assessment flows | 3 |
| `/web` | Nurse console, school dashboards, admin, M-Pesa vouchers | 4 |
| `/ai` | LLM service, RAG, guardrails, eval harness | 6 |

## Quick start (Phase 1)

```powershell
# Windows (this machine): use the PowerShell wrapper
.\make.ps1 setup      # create venv + install
.\make.ps1 db-up      # postgres:16 + redis via Docker
.\make.ps1 demo-phase1
```

```bash
# Linux / CI: plain make
make setup db-up demo-phase1
```

## Non-negotiables (enforced by tests)

1. The deterministic rules engine assigns every risk band; the LLM never does.
2. Synthetic data only — no real patient data anywhere.
3. Every rule ships `clinically_validated: false` until a Kenyan clinician signs off.
4. Nothing condition-identifying in notifications, SMS, USSD screens, or crash reports.
5. Minors' raw symptom data is never visible outside the clinical corridor.
6. All timestamps UTC in storage, Africa/Nairobi in display; UUIDv7 IDs only.
7. Secrets never in the repo.
8. Every phase adds tests before it is done; a failing band test blocks the merge.
9. Anything unspecified affecting safety, privacy, cost, or the database is a
   question for the maintainer, not a guess.

See `/docs/SPEC.md` for the full build specification and `/AGENTS.md` for the
session protocol.

## License

Code: MIT. Ontology and content: CC-BY 4.0. See `/LICENSE` and `/ontology/LICENSE`.
