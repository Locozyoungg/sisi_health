# Human-Owned Tasks

The agent cannot do these. Each is stubbed cleanly; no credentials are ever
faked. Status: `open` / `blocked` / `in progress` / `done`.

| # | Task | Status | Notes / unblocked by |
|---|---|---|---|
| H1 | Play Console account, upload key, app signing | open | Phase 2 |
| H2 | Africa's Talking production USSD shortcode approval and sender ID | open | Phase 3 (sandbox used until then) |
| H3 | Safaricom Daraja production go-live and credentials | open | Phase 4 (sandbox used until then) |
| H4 | WhatsApp Business verification and message-template approval | open | Phase 3 |
| H5 | ODPC registration and completed DPIA sign-off | open | DPIA template lands with docs (Phase 8) |
| H6 | Legal review: consent age thresholds, minors' health data rules, whether the triage software falls under Kenyan health-software / medical-device regulation | open | Confirms assumptions A1–A3, A7 |
| H7 | Clinician review and sign-off of all rules, content, and red-flag scripts | open | Review packet generator ships with the rules (Phase 1 provides schema + drafts) |
| H8 | Third-party penetration test before any real pilot data | open | Phase 8 checklist |
| H9 | Hotline number verification (116 / 1195) and partner-hospital pricing | open | Config carries UNVERIFIED flags until then |
| H10 | UNICEF application narrative, budget, theory of change | open | Grant package docs (Phase 8) |
| H11 | Pilot validation study ethics approval (sensitivity/specificity vs clinician assessment) | open | Stub in /docs (Phase 8) |
| H12 | Jitsi deployment + account (self-hosted or provider API) | open | Phase 5 ships the JWT room-token contract; server provisioning before pilot (A25) |
| H13 | Confirm current Kenya MoH cervical screening + HPV vaccination schedules (screening start age, interval, HPV doses/ages) | open | Config placeholder in /ontology/config/screening_schedule.json (A26) |
| H14 | Partner-hospital pricing data (real quotes replacing indicative stubs) | open | Pricing stubs marked indicative + sourced (A31) |
| H15 | Run the real hosted-vs-open-weight comparison (real hosted API key + vLLM GPU host), human-rate the Kiswahili/Sheng sample, regenerate `docs/ai-comparison-report.md` | open | Phase 6 ships stub providers + a STUB RUN report with the full procedure (A33/A34) |
| H16 | Kenyan clinician review of the 8 new AI content files (endo/PCOS/fibroids/period health, en+sw) before `clinically_validated=true` | open | Content ships `clinically_validated: false` with DRAFT notes (A10 pattern) |
