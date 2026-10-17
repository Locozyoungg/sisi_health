# Human-Owned Tasks

The agent cannot do these. Each is stubbed cleanly; no credentials are ever
faked. Status: `open` / `blocked` / `in progress` / `done`.
Last refreshed: 2026-10-17 (Phase 8 docs bundle).

| # | Task | Status | Notes / unblocked by |
|---|---|---|---|
| H1 | Play Console account, upload key, app signing | open | Phase 2 ships a release APK (15.0 MB budget met); signing key + Play account do not exist |
| H2 | Africa's Talking production USSD shortcode approval and sender ID | open | Phase 3 drives the real AT callback contract; sandbox credentials are still absent, so no sandbox e2e has run (A20). Cost-model SMS/USSD rows are placeholders pending this quote (A40) |
| H3 | Safaricom Daraja production go-live and credentials | open | Phase 4 implements the verified, idempotent callback contract in simulation (A24); production credentials and tariffs (cost model OPS-03) outstanding |
| H4 | WhatsApp Business verification and message-template approval | open | Phase 3 gateway implements the provider interface; the BSP contract and per-message pricing are unconfirmed (A40) |
| H5 | ODPC registration and completed DPIA sign-off | in progress | **DPIA template now shipped**: `/docs/templates/dpia-template.md` (pre-filled data inventory, lawful bases, risks, processor register). Registration, sign-off, and the breach tabletop result (`/docs/breach-runbook.md` §12) remain outstanding |
| H6 | Legal review: consent age thresholds, minors' health data rules, whether the triage software falls under Kenyan health-software / medical-device regulation | open | Confirms assumptions A1–A3, A7 |
| H7 | Clinician review and sign-off of all rules, content, and red-flag scripts | open | Review packet generator ships (`backend/scripts/export_review_packet.py` → `/docs/clinician-review-packet.md`); the SOP is `/docs/rule-change-sop.md`; the safety case template is `/docs/templates/clinical-safety-case.md` |
| H8 | Third-party penetration test before any real pilot data | open | **Checklist now shipped**: `/docs/pen-test-checklist.md` (OWASP ASVS L2 itemized; mappings in `/docs/asvs-mapping.md`). The external test itself has not been commissioned |
| H9 | Hotline number verification (116 / 1195) and partner-hospital pricing | open | Config carries UNVERIFIED flags until then (`SISI_HELPLINE_CHILD` / `SISI_HELPLINE_GBV`); the safeguarding policy and breach runbook both inherit the UNVERIFIED marking. Facility pricing stubs stay indicative (A31, H14) |
| H10 | UNICEF application narrative, budget, theory of change | in progress | **Grant package shipped**: `/docs/impact-metrics.md`, `/docs/data-dictionary.md`, `/docs/technical-summary.md`, `/CONTRIBUTING.md`, `/docs/cost-model.md` + `.csv`. The narrative, budget and theory of change themselves are not written |
| H11 | Pilot validation study ethics approval (sensitivity/specificity vs clinician assessment) | open | Measurement plan and indicator definitions are in `/docs/impact-metrics.md` §2 (metrics for publication require separate ethics approval); no ethics submission exists |
| H12 | Jitsi deployment + account (self-hosted or provider API) | open | Phase 5 ships the JWT room-token contract (one-time, unrecorded, DB CHECK `recorded IS FALSE`); server provisioning before pilot (A25) |
| H13 | Confirm current Kenya MoH cervical screening + HPV vaccination schedules (screening start age, interval, HPV doses/ages) | open | Config placeholder in `/ontology/config/screening_schedule.json` (A26); `verified: false` |
| H14 | Partner-hospital pricing data (real quotes replacing indicative stubs) | open | Pricing stubs marked indicative + sourced (A31) |
| H15 | Run the real hosted-vs-open-weight comparison (real hosted API key + vLLM GPU host), human-rate the Kiswahili/Sheng sample, regenerate `docs/ai-comparison-report.md` | open | Phase 6 ships stub providers + a STUB RUN report with the full procedure (A33/A34). The cost model's LLM row is 0.00 until this task supplies real pricing (A37/A40) |
| H16 | Kenyan clinician review of the 8 new AI content files (endo/PCOS/fibroids/period health, en+sw) before `clinically_validated=true` | open | Content ships `clinically_validated: false` with DRAFT notes (A10 pattern) |
| H17 | VPS provisioning and deploy execution (create the host, DNS/TLS, secrets, run the one-command deploy to staging then prod) | open | Phase 8 ships the deploy assets (prod compose, Caddy config, deploy script, runbook) and validates them without a host; no VPS, no registry access, and no production secrets exist. Host quote/choice also closes the cost-model hosting rows (A40) |
