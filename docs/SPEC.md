# BUILD SPECIFICATION v2: "SISI Health" — Women's Chronic Gynecological Health Platform (Kenya)

Sections marked [ADDED] are new in v2. Everything else is the original spec, kept intact.

## 0. OPERATING PROTOCOL [ADDED]

- Commit this document as /docs/SPEC.md. Create /AGENTS.md at the repo root restating Sections 1 to 3 so every session loads the non-negotiables.
- Work one phase at a time, in the Build Order. Do not start phase N+1 until phase N's Definition of Done passes and the maintainer approves.
- Deliver file by file: state the path, then the full file contents. No placeholders, no "rest unchanged", no TODO stubs except items listed in Section 4 (Human-Owned Tasks). After each group of files, give the exact commands to run and the expected output.
- Never invent facts about Kenyan law, clinical thresholds, API endpoints, or credentials. When unsure, record an ASSUMPTION in /docs/assumptions.md and ask.
- Freeze contracts: Phase 1 produces the database schema and OpenAPI spec. Later phases change them only through a numbered note in /docs/contract-changes.md plus a migration.
- Bug fixes are scoped to the bug. Do not refactor unrelated code while fixing a defect.
- Every phase ends with a runnable command that proves it works (for example make demo-phase1).

## ROLE

You are a senior full-stack engineer, ML engineer, and health-tech product architect. Build SISI Health as if it will be: (a) reviewed by UNICEF's Venture Fund, (b) deployed in real Kenyan girls' schools, (c) handling minors' health data under Kenya's Data Protection Act 2019, and (d) pitched to investors — all within 8 weeks. Production-ready means secure, tested, offline-tolerant, documented, and deployable. No demo shortcuts.

## PRODUCT CONTEXT

SISI Health addresses the most ignored segment of African femtech: chronic gynecological conditions (endometriosis, PCOS, uterine fibroids, chronic pelvic pain) in girls and women — not pregnancy. Three user-facing layers:

- LAYER 1 — Private symptom tracker + AI diagnostic triage (consumer app)
- LAYER 2 — "Period-Friendly School" program (B2B: USSD/WhatsApp self-assessment, school nurse escalation, parent education, M-Pesa-linked product access)
- LAYER 3 — Specialist corridor (telehealth triage → gynecologist consults → facility/surgery referral navigation)

CRITICAL ENVIRONMENT CONSTRAINTS:

- Users: Kenyan girls 13–19 and women 20–45; many on entry-level Android (2GB RAM), intermittent 2G/3G, pay-per-MB data. Offline-first is non-negotiable.
- School channel: users without smartphones reach the system via USSD and WhatsApp on shared/borrowed phones. Flows must be private (no condition names on screen or in SMS history), resumable, and timeout-tolerant.
- Minors are users: parental/guardian consent flows are a legal requirement, and child safeguarding is a design constraint on EVERY feature.

## 1. NON-NEGOTIABLES [ADDED]

1. The deterministic rules engine assigns every risk band and every condition indicator. The LLM never assigns, changes, or contradicts a band. It only explains what the rules engine decided. Replacing rules with LLM triage is forbidden.
2. No real patient data anywhere in the repo, tests, fixtures, logs, or CI. Synthetic only.
3. Every triage rule, red-flag script, and education chunk ships with clinically_validated: false and empty sign-off fields (reviewer_name, reviewer_registration_no, signed_at) until a licensed Kenyan clinician signs off. The app must refuse to enable unvalidated rules for real users; a build flag allows them only in dev and demo.
4. Nothing condition-identifying ever appears in notifications, SMS, USSD screens, app switcher previews, filenames, or crash reports.
5. Minors' raw symptom data is never visible to staff outside the clinical corridor (nurse-reviewed referral, consented gynecologist consult). School staff see severity bands and actions only.
6. All timestamps in UTC in storage, Africa/Nairobi in display. All IDs are UUIDv7. No auto-increment IDs exposed.
7. Secrets never in the repo. .env.example only, with a secrets-scanning step in CI.
8. Every phase adds tests before it is declared done. A failing red-flag or band test blocks the merge.
9. Anything not specified here and affecting safety, privacy, cost, or the database is a question for me, not a guess.

## 2. TECHNICAL DECISIONS [ADDED]

Defaults below are decided so you do not invent inconsistent ones. Change one only after asking me.

| Area | Decision |
|---|---|
| Database | PostgreSQL 16 with pgvector. Separate schemas: core, diary (separately encrypted), audit (append-only), school, corridor. |
| Migrations | Alembic, forward-only, every migration reviewed with a rollback note. |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Ruff, mypy strict on the rules and consent packages. |
| Jobs / queue | Redis + arq workers (sync, SMS, PDF, reconciliation). |
| Auth (users) | Phone-number OTP via SMS, short-lived JWT plus rotating refresh tokens, device binding. |
| Auth (staff) | Email + password + mandatory TOTP, RBAC on every endpoint, 15-minute idle timeout. |
| Key management | Envelope encryption: per-record data keys wrapped by a master key behind a KeyProvider interface (dev: local file; pilot: self-hosted Vault or cloud KMS). Key rotation procedure documented. |
| Audit trail | Hash-chained append-only table. Each row stores the hash of the previous row. A nightly job verifies the chain and alerts on a break. |
| Mobile | Kotlin, Compose, Room with SQLCipher, Hilt, WorkManager, Retrofit. Android Keystore for keys. Release builds set FLAG_SECURE by default and hide the app switcher preview. |
| Offline sync | Client-generated UUIDv7 per diary entry. Entries are append-only events; edits create a new version. Conflict rule: highest version wins per field, server timestamp breaks ties. Every sync call carries an idempotency key. Property-based tests for sync merge. |
| Web | React + TypeScript, Vite, TanStack Query, Playwright e2e. |
| USSD / SMS | Africa's Talking (sandbox first). Session state in Redis with a 5-minute resume window keyed by phone hash. |
| WhatsApp | Turn.io or WhatsApp Business API behind a MessagingProvider interface. |
| Telehealth | Self-hosted Jitsi with JWT-gated rooms. No recording by default. |
| Embeddings / RAG | Multilingual embedding model (bge-m3 or multilingual-e5) into pgvector. Answers must cite chunk IDs or are refused. |
| LLM | LLMProvider interface. Pilot: hosted API with strict system prompt and no patient identifiers in prompts. Open-weight path (Llama 3.x or Qwen served by vLLM on a separate GPU host) implemented and eval-compared before pilot. |
| Deploy | Docker Compose on one VPS, Caddy for TLS 1.3, separate staging and prod stacks, nightly encrypted backups with a tested restore. |
| Observability | Structured JSON logs with PII scrubbing, OpenTelemetry, Prometheus + Grafana. Logs never contain diary content, phone numbers, or names. |
| Open-source | MIT for code, CC-BY 4.0 for /ontology and content. |

## 3. DESIGN DECISIONS THAT RESOLVE SPEC CONFLICTS [ADDED]

### 3.1 Nurse re-identification

School nurses see anonymized IDs by default. A nurse may re-identify a student only when (a) the student's band is ORANGE or RED, or (b) the student asked to be contacted. Re-identification requires a typed reason and writes an audit entry. The pseudonym-to-person mapping lives in an encrypted table that only the re-identify endpoint can read. The privacy notice shown at assessment tells the student a nurse may contact her if her result needs follow-up.

### 3.2 Minors, discreet features, and guardians

- Users under 13 are blocked at the age check.
- Discreet name/icon, decoy mode, and quick-exit are available to all users including minors. They protect the girl from stigma and are never disabled by a guardian.
- Guardians never read a minor's diary or assessment answers.
- Consent for 13–17: guardian consent plus the minor's own assent, both recorded. Counsel must confirm whether any age within 13–17 may self-consent to health services; make that threshold a config value, not hard-coded.

### 3.3 Guardian alerts and safeguarding override

- Guardians are alerted only for RED-band events. The message is generic ("Please contact the school nurse or take her to a clinic soon") with no symptoms or condition names.
- Safeguarding override: if any input suggests abuse, sexual violence, pregnancy concerns in a minor, self-harm, or that the guardian may be the source of risk, the system does not alert the guardian. It routes to the designated safeguarding lead, shows the child helpline 116 and the GBV helpline 1195, and logs the escalation. Verify all hotline numbers before launch and keep them in config.
- Red-flag text (severe acute pain, heavy bleeding with dizziness, self-harm) always shows the urgent-care script first, regardless of any other state.

### 3.4 k-anonymity at small scale

- Any cell with fewer than 5 is suppressed, with complementary suppression so subtraction cannot reveal it.
- A school reports nothing until at least 20 students have completed assessments in the term.
- Below threshold the dashboard shows "Not enough data yet", never a zero.
- Enforcement lives in one shared query module with property-based tests against differencing attacks.

### 3.5 Channel limits

SMS and USSD run over unencrypted carrier networks. Therefore: no names, no conditions, no scores in them. SMS summaries say only "Your health check results are ready. Visit your school nurse or open the app." Detailed guidance is delivered in-session and never stored in SMS history.

## 4. HUMAN-OWNED TASKS [ADDED]

The agent cannot do these. Stub them cleanly, document each in /docs/human-tasks.md, and never fake credentials.

- Play Console account, upload key, and app signing
- Africa's Talking production USSD shortcode approval and sender ID
- Safaricom Daraja production go-live and credentials
- WhatsApp Business verification and message-template approval
- ODPC (Office of the Data Protection Commissioner) registration and completed DPIA sign-off
- Legal review of consent age thresholds, minors' health data rules, and whether the triage software falls under Kenyan health-software or medical-device regulation
- Clinician review and sign-off of all rules, content, and red-flag scripts (Section 7)
- Third-party penetration test before any real pilot data
- Hotline number verification and partner-hospital pricing
- UNICEF application narrative, budget, and theory of change

## 5. SYSTEM ARCHITECTURE (build all components)

### 5.1 Consumer Mobile App (offline-first Android, min SDK 26, target 34)

- Kotlin + Jetpack Compose, Room DB, WorkManager sync
- Private symptom diary: daily logging of pain (validated 0–10 NRS), bleeding (volume + pattern), cycle dates, GI/urinary symptoms, fatigue, mood; takes <60 seconds/day; works fully offline, syncs when connected
- Pattern engine: deterministic, versioned rules (clinician-authored, JSON-config) that analyze 60–90 days of diary data and flag risk patterns:
  - Endometriosis indicators (cyclical pain, dyschezia, dyspareunia for adults)
  - PCOS indicators (cycle irregularity + androgenic symptoms)
  - Fibroid indicators (heavy bleeding patterns, bulk symptoms)
  - Anemia risk flag (bleeding volume + fatigue)
- Output: plain-language Kiswahili/English explanation ("your pattern suggests X is possible — here's what to do next"), NEVER a diagnosis; severity banding (self-care / see a nurse / see a doctor soon / urgent); auto-generated 1-page summary PDF the user can take to a clinic
- Privacy vault: PIN/biometric lock, discreet app name/icon option, decoy mode, quick-exit gesture; nothing condition-identifying in notifications (notifications say "Time for your daily check-in")
- Localization: all strings externalized; ship Kiswahili + English, stub files for Luo, Kalenjin, Somali
- [ADDED] Dyspareunia and sexual-health questions are shown only to users 18+; minors never see them. Rules must be age-gated in the JSON schema (min_age).
- [ADDED] The pattern engine runs identically on-device (Kotlin) and on the server (Python), driven by the same JSON rules. A shared golden-test file in /ontology proves both produce identical bands on every test case.
- [ADDED] Insufficient data (fewer than 14 diary days) returns "not enough data yet" with guidance, never a band.
- [ADDED] App must stay usable on 2GB RAM: cold start under 3 seconds on a low-end reference device, APK under 25 MB, diary sync payloads compressed and batched.
- [ADDED] Accessibility: TalkBack labels, large-text support, low-literacy mode with icons and audio prompts.

### 5.2 AI Triage & Conversation Layer (backend service)

- FastAPI (Python) service exposing:
  - a) LLM endpoint (open-weight model — Llama 3.x/Qwen — fine-tuned OR hosted API with strict system prompt) for symptom explanation, education Q&A, and next-step guidance in Kiswahili/Sheng, handling code-switching
  - b) RULES endpoint: deterministic triage ONLY — the LLM must never assign risk levels or diagnoses; it only explains what the rules engine decided
- Guardrails (hard requirements, evaluated in CI): refuses diagnosis, refuses medication prescribing, detects red-flag text (severe acute pain, heavy bleeding + dizziness, self-harm) and routes to urgent-care script + hotlines, stays on women's-health topics, age-appropriate language for minors
- Retrieval layer over a curated, clinician-reviewed content library (endo/PCOS/fibroids/period health, Kiswahili + English), CC-BY 4.0 licensed, served via vector search; every LLM answer cites source chunks
- Open-source symptom ontology: publish the condition-symptom mapping, triage rules JSON, and content schema in /ontology as the project's flagship open-source artifact (this is a grant requirement and a scientific asset)
- [ADDED] Red-flag detection runs BEFORE the LLM, as deterministic keyword/pattern matching in English, Kiswahili, and Sheng, with the LLM never in the loop for the urgent script. Maintain the pattern list in /ontology with test cases.
- [ADDED] The LLM receives only the rules-engine output (band, indicator names, content chunks), never raw identifiers. Output is checked by a post-filter that rejects any answer containing a diagnosis claim, a drug name with dose, or a band different from the engine's.
- [ADDED] Provide an eval harness comparing the hosted model and the open-weight model on the same suite, reporting guardrail pass rate, Kiswahili/Sheng quality (human-rated sample), latency, and cost per 1,000 conversations.
- [ADDED] Prompt-injection tests included: users trying to make the model diagnose, prescribe, reveal the system prompt, or discuss other users.

### 5.3 School Program Module (B2B2C)

- USSD flow (*XXX#): language select → age check → privacy notice → 10-question symptom self-assessment (pain, bleeding, school-days-missed) → immediate guidance + SMS summary (generic wording: "Your health check results")
- WhatsApp bot (via WhatsApp Business API / Turn.io): same assessment + diary lite + nurse contact card
- School nurse console (web): flag queue (anonymized IDs only), severity bands, action tracking (spoke to student / referred to clinic / escalated), NEVER raw symptom narratives for minors
- Parent/guardian module: consent flow (plain-language Kiswahili, recorded consent option for low-literacy), education content ("understanding your daughter's period pain"), alert only for RED-band events
- M-Pesa integration (Safaricom Daraja API): voucher issuance for sanitary products + pain relief at partner pharmacies; admin wallet + reconciliation report; stub for employer-funded wallets later
- School dashboard (B2B): aggregate-only metrics (assessments completed, RED flags, school-days-missed trend, product vouchers redeemed) — k-anonymity ≥5 enforced at query level; exportable term reports (this is what schools pay for)
- [ADDED] USSD screens are max 160 characters, no condition names, a "0" back option and "00" exit on every screen. Sessions resume within 5 minutes; after timeout the user restarts with no residual data shown.
- [ADDED] Shared-phone safety: no history of results on the handset, and a first-screen note that says to clear the call log if privacy is needed.
- [ADDED] Vouchers: single-use, expiring codes, redeemable only at registered pharmacies, capped per student per term, with no medicine name on the voucher. Pain-relief vouchers are limited to a clinician-approved OTC list in config. Daraja callbacks are verified and idempotent; reconciliation report flags mismatches.
- [ADDED] Parent consent can be captured by SMS link, in-person form scanned by a nurse, or recorded voice consent; every path stores who, when, how, and version of the text consented to.

### 5.4 Specialist Corridor

- Telehealth booking: patient-initiated consult requests → nurse review queue → gynecologist video/audio consult (Jitsi Meet self-hosted or provider API)
- Referral engine: directory of gynecologists/facilities (county, level, cost, languages), catchment mapping, referral letter auto-generated from diary summary + triage output
- Surgery navigation: track referred cases through diagnostic → surgical evaluation → surgery → follow-up; partner-hospital pricing stubs; outcome log
- Nurse review queue: structured case view (diary trends + triage bands), not raw LLM transcripts
- [ADDED] Minors' consults require recorded guardian consent (or the lawful alternative confirmed by counsel) and a chaperone option. Consult rooms are one-time, JWT-gated, and unrecorded.
- [ADDED] Referral letters contain only what the patient approves to share, shown to her before sending. She can revoke sharing.
- [ADDED] Surgery tracking is for navigation and follow-up only. No clinical decisions or prices are presented as medical advice; pricing is marked as indicative and sourced.

### 5.4.1 Cervical Screening and Navigation Module [ADDED]

Purpose: prevention, referral, and follow-up. This module does NOT detect or diagnose cervical cancer, and it never tells a woman she is low risk or cancer-free. Early cervical cancer often has no symptoms, so screening needs a clinical test (for example HPV testing, VIA, or a Pap smear, as offered under current national guidance).

- Red-flag rules: deterministic, versioned rules in /ontology for bleeding after sex, bleeding between periods, bleeding after menopause, and persistent unusual or foul-smelling discharge. Minimum output band is "see a doctor soon"; combined with heavy bleeding and dizziness the existing urgent rules apply. All rules ship clinically_validated: false until a gynecologist signs off.
- Age and safeguarding gating: sexual-activity questions are shown only to users 18+. For a minor, post-coital bleeding is also a safeguarding signal: show generic nurse-referral wording, trigger the safeguarding check in Section 3.3, and never alert the guardian with symptom detail.
- Screening reminders: age-based prompts driven by a config file populated from the current Ministry of Health screening guideline (never hard-coded). Notifications use generic wording ("Time for your health check-in") with nothing condition-identifying.
- Education content: Kiswahili and English, clinician-reviewed, source-cited, explaining why screening matters even without symptoms and which screening options are available locally. Every screening message includes: "A normal symptom check does not replace screening."
- HPV vaccination awareness: guardian-facing education in the school module, with the schedule taken from Ministry of Health config.
- Facility directory: extend the referral engine with screening fields (test types offered, cost, county, level, languages, opening hours, last-verified date). Entries not verified in 90 days are flagged as stale and shown with a warning.
- Follow-up tracker: states are referred, screened, result received, further assessment, treatment, follow-up. Configurable reminder intervals, patient-consented sharing, a loss-to-follow-up flag for nurses (status only, no results detail), and aggregate-only reporting through the k-anonymity module.
- Hard limits: no AI analysis of cervical images (that would be a regulated medical device and a separate project); no risk scoring from symptoms alone; no output that says low risk; the LLM may only explain what the rules engine decided and must refuse "do I have cancer" style questions with a referral script.
- Tests required: at least 25 red-flag rule cases including thresholds and age gating; a test that no band is ever lowered when a red flag is present; at least 20 guardrail eval cases on cervical topics in English, Kiswahili, and Sheng; tracker state-machine tests; facility staleness tests; a lint that no notification or SMS string names a condition.
- Human-owned: clinician sign-off of rules and content; confirmation of the national screening schedule and vaccination schedule; screening-facility partner data; clinical or legal review before any future image-based feature.

### 5.5 Admin, Analytics & B2B Dashboards (web — React + TypeScript)

- Roles: super admin, school admin, employer admin (future), nurse, gynecologist, MoH/aggregate viewer
- B2B dashboards: per-school/per-employer aggregates, engagement, outcomes (school-days-missed delta, referrals completed, consults done)
- Ops console: content management (CMS for education library), rules-editor UI (clinicians edit triage rules without code — versioned + approval workflow), USSD flow editor, voucher budgets, audit logs
- OpenAPI-documented REST API; every endpoint behind RBAC
- [ADDED] Rules editor enforces two-person approval (author and clinician approver must differ), shows a diff against the active version, runs the full rules test suite before activation, and supports instant rollback. Activating a rule version writes an audit entry.
- [ADDED] Role matrix document in /docs listing, per role, every endpoint and data class it may read or write. RBAC tests assert every endpoint denies unauthorized roles.

## 6. SAFETY, PRIVACY, CHILD SAFEGUARDING & COMPLIANCE (first-class, audited)

- Kenya DPA 2019 full compliance: lawful basis mapping, recorded consent, guardian consent for <18 (with assent from the minor), purpose limitation, right-to-erasure pipeline, data-processing agreements template
- Child safeguarding: content safety review for all minor-facing text, mandatory-reporting escalation path embedded (Kenya's child protection helpline 116), staff-access logging for any minor's record, no targeted advertising, no third-party trackers in the app
- Data minimization + pseudonymization; AES-256 at rest, TLS 1.3 in transit; separate encrypted store for diary data; field-level encryption keys documented
- Clinical safety: hazard log, clinical safety case document template, every triage rule versioned with clinician sign-off metadata
- Immutable audit trail: every record access, rule change, consent event, and escalation is logged
- In-app disclaimers in both languages: "SISI supports you and your doctor — it does not diagnose"
- [ADDED] Consent revocation: withdrawing consent stops processing within 24 hours, triggers the erasure pipeline within the legal window, and notifies downstream processors. Erasure keeps only the audit-trail hash with no personal content, and the design documents why that is lawful.
- [ADDED] Data subject rights endpoints: access, correction, portability (JSON export), erasure, objection. Each request is tracked with a deadline.
- [ADDED] Breach response runbook with 72-hour ODPC notification steps and a tested tabletop scenario.
- [ADDED] Data residency and cross-border transfer register: every processor (SMS, WhatsApp, hosting, LLM API) listed with location and safeguard. No diary content is sent to any processor outside Kenya without recorded lawful basis, and the LLM API never receives diary content.
- [ADDED] Retention schedule: diary data, assessment data, audit logs, and vouchers each with a stated retention period and automated purge.
- [ADDED] Staff vetting and training: no staff account is issued until the safeguarding policy is acknowledged in-app. Access to any minor's record is logged and reviewed monthly.
- [ADDED] Hazard log seeded with at least these hazards: missed red flag, false reassurance, false alarm, guardian alert harming the child, re-identification misuse, shared-phone exposure, LLM diagnosis leakage, rule-version error, sync data loss, voucher fraud. Each has cause, control, test, and owner.

[ADDED] Cervical module hazards to seed in the hazard log: false reassurance leading a woman to skip screening, missed red-flag bleeding, lost follow-up after a positive result, stale facility data, and a minor's post-coital bleeding reaching a guardian without safeguarding review. Each needs cause, control, test, and owner.

## 7. CLINICAL VALIDATION PROTOCOL [ADDED]

- You are not a clinician. Draft rules from published guidance and cite each source in the rule's evidence field. Never present drafts as validated.
- Rule schema fields: id, version, condition, inputs, logic, output_band, min_age, evidence[], clinically_validated, reviewer_name, reviewer_registration_no, signed_at, changelog.
- Build a clinician review packet generator: one command exports every rule, its evidence, and its test cases to a readable PDF for a gynecologist to review and sign.
- Test-case set for rules: at least 25 cases per condition indicator plus boundary cases at every threshold, plus a case set written by clinicians (blank file ready to receive them).
- Safety asymmetry: where uncertain, the rule resolves to the higher-urgency band. Tests assert that no input combination lowers a band when a red-flag symptom is present.
- Plan a pilot validation study stub in /docs: sensitivity and specificity measurement against clinician assessment, with ethics approval noted as a human task.

## 8. DELIVERABLES

1. Monorepo: /mobile (Android), /backend (API + rules engine), /ai (LLM service, RAG, eval harness), /ussd-whatsapp (gateway), /web (all dashboards + nurse + clinician consoles), /ontology (open-source artifacts), /docs
2. Docker + docker-compose dev environment; GitHub Actions CI: lint, unit tests, rules-engine test coverage ≥80% (this assigns risk bands — it must be right), LLM guardrail eval suite (≥150 adversarial + Swahili/Sheng + minor-language test cases), e2e USSD flow tests, dependency security scan
3. Licenses: MIT (code), CC-BY 4.0 (content + ontology), LICENSE file + IP policy README (grant requirement)
4. Deployment: one-command deploy to single VPS (pilot) with staging + prod; signed APK/AAB ready for Play Console closed testing; USSD on Africa's Talking sandbox; M-Pesa Daraja sandbox with production checklist
5. Seed data: 2 demo schools, 3 demo nurses, 2 demo gynecologists, 40 synthetic users across age bands with 90-day synthetic diaries (NEVER real patient data); 1 demo employer account
6. Documentation: OpenAPI spec, architecture diagram (Mermaid), runbook, data-flow map, DPIA template, child-safeguarding policy template, clinical safety case template, rule-change SOP, UNICEF-style open-source README
7. [ADDED] Coverage target: 100% on band-assignment and red-flag code paths, ≥80% on the rules package overall, ≥70% elsewhere, with mutation testing on the rules engine.
8. [ADDED] Security checklist: OWASP ASVS L2 items mapped to code, security scan, SBOM, dependency pinning, rate limiting and OTP brute-force lockout, and the pen-test checklist (Section 9, phase 8).
9. [ADDED] Cost model: monthly pilot running cost (VPS, SMS, USSD sessions, WhatsApp messages, LLM per 1,000 conversations) as a spreadsheet-ready CSV, with per-student cost at 1,000 and 10,000 students.
10. [ADDED] Grant package: impact-metrics definition (school-days-missed delta, time-to-first-clinical-contact), data dictionary, open-source contribution guide, and a one-page technical summary for reviewers.
11. [ADDED] Human-tasks tracker at /docs/human-tasks.md reflecting Section 4, with status per item.

## 9. BUILD ORDER (strict sequence)

1. Backend core + deterministic rules engine + audit trail + consent/consent-revocation system (legal foundation first)
2. Consumer Android app (diary + pattern engine + privacy vault) with offline sync
3. USSD + WhatsApp assessment flows
4. School nurse console + school dashboards + M-Pesa voucher module
5. Specialist corridor (booking, referral letters, surgery tracking)
6. AI conversation layer with RAG + guardrails + eval harness
7. Employer admin (future revenue) — minimal: wallet + aggregate dashboard
8. Hardening: penetration-test checklist pass, load test (1k concurrent USSD sessions), full docs, seed data, deploy scripts

### Definition of Done per phase [ADDED]

| Phase | Must pass before moving on |
|---|---|
| 1 Backend core | Schema + OpenAPI frozen; rules engine band tests incl. red-flag asymmetry; audit chain verifier; consent grant/revoke/erasure e2e test; RBAC denial tests; make demo-phase1 runs. |
| 2 Android | Offline diary 7-day scenario test; sync conflict property tests; on-device vs server band parity on golden file; privacy vault tests (notifications, screenshots, decoy); APK size and cold-start budget met. |
| 3 USSD + WhatsApp | e2e flows in sandbox for all languages; timeout/resume tests; 160-char screen lint; no condition names in any string; age-gate and consent path tests. |
| 4 School | Nurse console shows no raw narratives for minors; re-identification flow audited; k-anonymity and differencing tests; Daraja sandbox voucher + reconciliation idempotency tests. |
| 5 Corridor | Booking → review → consult → referral letter flow e2e; patient-approval of shared data enforced; surgery tracker state-machine tests. |
| 6 AI layer | ≥150-case guardrail suite passes (adversarial, Kiswahili/Sheng, minor-language, prompt injection); 100% red-flag routing; every answer cites chunks; hosted vs open-weight comparison report. |
| 7 Employer | Wallet ledger invariants tested; aggregate-only dashboard with the same k-anonymity module. |
| 8 Hardening | Pen-test checklist complete; 1,000 concurrent USSD sessions load test report; backup restore drill; all docs and seed data present; one-command deploy to staging and prod. |

[ADDED] Phase 5 also requires: the cervical red-flag rule tests, the screening follow-up tracker state-machine tests, and the facility directory staleness checks from Section 5.4.1.

## 10. PHASE REPORTS AND DECISION GATES

At the end of each phase output: what was built, test results, risks, next phase. Ask me before any irreversible decision (changing DB, dropping USSD, swapping the open-source LLM for a closed-only model, or removing the deterministic rules layer in favor of pure LLM triage — that one is forbidden).

[ADDED] Phase report format:

1. Files created or changed (paths)
2. Commands to run and their actual output
3. Test results with counts and coverage numbers
4. Open risks, mapped to hazard-log IDs
5. Assumptions made (copied to /docs/assumptions.md)
6. Human tasks now unblocked or required
7. Questions needing my decision before the next phase

## 11. START INSTRUCTION [ADDED]

Begin with Phase 1 only. First reply with: (1) the repo tree you will create, (2) the database schema outline, (3) the list of endpoints with roles, (4) the rule JSON schema, and (5) any questions. Wait for my approval, then deliver the files one by one.
