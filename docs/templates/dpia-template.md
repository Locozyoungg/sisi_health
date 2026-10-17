# Data Protection Impact Assessment (DPIA) — TEMPLATE

> **Status: NOT COMPLETED — this is a template.** It is pre-filled with the
> SISI Health processing reality as implemented, so that a Data Protection
> Officer and Kenyan counsel can finish it quickly. No section here is legal
> advice, and no sign-off exists yet. Completing and signing this DPIA is human
> task **H5** (see `/docs/human-tasks.md`); it is a precondition for any real
> pilot data (non-negotiable 2 keeps all repository data synthetic until then).
>
> Lawful-basis wording, statutory references, and retention periods are
> deliberately left as `TO CONFIRM WITH COUNSEL` placeholders — the project
> never invents legal positions (SPEC §0, assumption A1–A7).

| Field | Value |
|---|---|
| Processing operation | SISI Health — women's chronic gynecological health platform (Kenya) |
| Controller | `TO CONFIRM` (school / employer / SISI entity — the pilot agreement defines this) |
| Processor / operator | Kairon Technologies Limited |
| DPO / contact | `TO CONFIRM` |
| Assessor | `TO CONFIRM` |
| Version / date | 0.1 draft template, `2026-10-17` |
| Review trigger | any new data class, new processor, new country of transfer, or new user group |

## 1. Purpose and necessity

SISI Health processes menstrual and gynecological symptom data to:

1. let a girl or woman keep a private encrypted symptom diary (Layer 1);
2. run a **deterministic rules engine** that assigns a severity band and
   condition *indicators* (never a diagnosis) and returns plain-language next
   steps (Layer 1/3);
3. support a school program in which a student without a smartphone completes a
   10-question assessment over USSD/WhatsApp and a school nurse — seeing only a
   pseudonym and a severity band — can act (Layer 2);
4. route consented cases into a specialist corridor (nurse review → gynecologist
   telehealth → facility referral → follow-up) (Layer 3);
5. answer education questions through an LLM layer that only *explains* the
   rules engine's output and must cite reviewed content.

Necessity: the alternatives (no symptom capture; school staff reading raw
symptom narratives) are either clinically useless or are a greater privacy harm
to minors. Data minimisation is implemented structurally — see §3.

## 2. Data subjects and scale

| Data subject group | Approx. scale (pilot target) | Notes |
|---|---|---|
| Students, ages 13–17 | 1,000–10,000 | minors; guardian consent + minor assent (assumption A1: self-consent age 18 until counsel confirms otherwise) |
| Adult users, 18–45 | 1,000–10,000 | self-consent |
| Under-13s | **blocked** | rejected at the age check in the app, USSD flow, and the rules engine (`age < 13`) |
| School nurses / school admins | tens | pseudonyms and bands only; re-identification restricted (SPEC §3.1) |
| Gynecologists / corridor staff | tens | computed-feature snapshots only, inside the clinical corridor |
| Employer admins / MoH viewers | few | k-anonymised aggregates only (cells < 5 suppressed) |

## 3. Data inventory (as implemented)

Retention values below are the shipped config defaults (`SISI_RETENTION_*`),
recorded in assumption A3 and **pending legal confirmation**.

| # | Data class | Where it lives | Encrypted / minimised how | Retention | Who can read it |
|---|---|---|---|---|---|
| D1 | Phone number | `core.users.phone_encrypted` (+ `phone_hash` for lookup) | envelope-encrypted (AES-GCM, per-record data key wrapped by the master key); only the hash is used for lookup | until erasure | the user; OTP path |
| D2 | Date of birth | `core.users.birth_date_encrypted` | envelope-encrypted; used only to compute age | until erasure | the user; consent/age gates |
| D3 | Diary entries + every edit version | `diary` schema, append-only versions | **separately encrypted** payload ciphertext per entry-version; no plaintext symptom column exists | 2555 days (7 y) default → `TO CONFIRM` | the user only. No staff role ever decrypts raw diary |
| D4 | Rule evaluations (band + indicators) | `diary.rule_evaluations` | band/indicator names only, no narrative | as D3 | the user; corridor sees the snapshot, not the rows |
| D5 | USSD/WhatsApp assessment | `diary.school_assessments` | answers + band sealed per assessment (`owner_type='assessment'`); plaintext limited to `phone_hash`, `age_band`, `consent_state`, `language`, timestamps | as D3 | school nurse sees band + pseudonym only |
| D6 | Student identity mapping | `core.student_contact_map` (encrypted name/phone) | envelope-encrypted; readable **only** by the re-identify path, which requires ORANGE/RED band or a contact request and a typed reason, and writes an audit entry | until erasure | re-identify endpoint (audited) |
| D7 | Guardian record | `core.guardians` (encrypted contact) | envelope-encrypted; guardians never read a minor's diary or answers | until erasure | nurse flow (alerts: RED only) |
| D8 | Consent events, consent text versions | consent tables (`core`) | who / when / how / which text version; text body hashed | retained until erasure; the audit trail keeps pseudonymous evidence | super admin (audit), user |
| D9 | Corridor case data | `corridor` schema | consult requests carry a **computed-feature snapshot** and an optional patient note, both envelope-encrypted; **raw diary ciphertext is never opened by corridor code** (assumption A30) | as D3 | nurse/gynecologist inside the corridor; every case view is audited (`corridor_case_viewed`) |
| D10 | Referral letters | `corridor.referrals` | envelope-encrypted; only patient-approved sections are rendered/sent; revocable | as D3 | patient previews the full letter before approving |
| D11 | Telehealth sessions | `corridor.consult_sessions` | one-time JWT-gated rooms; `recorded IS FALSE` enforced by a DB CHECK; no recording endpoints exposed | case lifetime | corridor staff |
| D12 | Vouchers / wallet ledger | `school` schema | no medicine name on the voucher; append-only ledger; reconciliation flags mismatches | 730 days (vouchers) → `TO CONFIRM` | school admin, pharmacy, finance (super admin) |
| D13 | Audit trail | `audit` schema, hash-chained append-only | pseudonymous UUIDs + sanitised payloads; **no diary content, no phone numbers, no names** (PII scrubber) | **retained indefinitely today** — `SISI_RETENTION_AUDIT_DAYS` (3650) has no automated effect because deleting rows would break the append-only chain; the schedule-vs-chain conflict is an open maintainer decision (assumption A3, contract note CC-6) | super admin (read), nightly verifier |
| D14 | AI conversation input | `/v1/ai/*` request body | the AI service schema **physically lacks** id/phone/name fields (A36); the LLM receives the engine's band + indicator names + retrieved chunks, never identifiers, never diary content | not stored by the AI service | not readable by staff |
| D15 | Aggregates (school / employer / MoH) | computed on demand through one shared k-anonymity module | cells < 5 suppressed with complementary suppression; below 20 assessments the answer is `not_enough_data`, never a zero | n/a (computed) | school admin, employer admin, MoH viewer |

Not collected, by design: location/GPS, contacts, photos, advertising IDs,
third-party trackers, raw LLM transcripts of minors, cervical images.

## 4. Lawful bases

The project records consent as data, not as an assertion in prose. Fill the
basis column with counsel.

| Processing | Data category | Proposed lawful basis | Evidence in the system | Confirm |
|---|---|---|---|---|
| Diary, assessment, triage | health (sensitive) | explicit consent; guardian consent + minor assent for 13–17 | versioned `consent_texts` + `consent_events` with method (`digital`/`sms_link`/`paper`/`voice`), who, when | `TO CONFIRM WITH COUNSEL` (DPA 2019 s. `__`) |
| Staff access to a minor's record | health (sensitive) | safeguarding / clinical care within the corridor | RBAC matrix + audit entries on every case view | `TO CONFIRM` |
| Guardian alert | minimal health signal (band RED) | consent for alert delivery; **overridden** where the guardian may be the risk | `guardian_alerts.status = skipped_safeguarding` | `TO CONFIRM` |
| Audit trail retention after erasure | pseudonymous | legal/accountability obligation | `erasure_completed` record; A7 documents why this is lawful | `TO CONFIRM` |
| Aggregate reporting to schools/employers | de-identified | consent + k-anonymity | `app/k_anon.py` + property tests | `TO CONFIRM` |

## 5. DPIA questions (answer each; SISI-specific answers pre-filled)

| # | Question | Pre-filled answer | Status |
|---|---|---|---|
| Q1 | Is the processing necessary and proportionate? | Yes: each field maps to a rule input or a channel requirement; see §3 and the data dictionary | review |
| Q2 | Are minors affected? | Yes — 13–17 with guardian consent + assent; under-13 blocked; discreet mode and quick-exit are never disabled by a guardian (SPEC §3.2) | confirm with counsel |
| Q3 | Is sensitive/special-category data processed? | Yes — menstrual, gynecological, and mental-health signals | confirm the DPA 2019 basis |
| Q4 | Are data subjects' rights operable? | Yes — access/correction/portability/erasure/objection endpoints with a tracked deadline (`SISI_DSR_DEADLINE_DAYS`, default 30 — A2); revocation stops processing and schedules erasure | verify against the statute |
| Q5 | Is there automated decision-making? | Deterministic rule-based banding with human escalation paths; **no LLM assigns a band** (non-negotiable 1). Whether the triage software falls under health-software / medical-device regulation is human task **H6** | counsel |
| Q6 | Are transfers outside Kenya involved? | Depends on the deploy: the DB/VPS host, the SMS/WhatsApp provider, and (only if enabled) the hosted LLM API. The LLM never receives diary content or identifiers | fill the register, §7 |
| Q7 | How is the child's best interest served? | Safeguarding override routes abuse/self-harm/pregnancy signals away from the guardian to the designated lead, shows helplines 116/1195 (UNVERIFIED until H9), and always shows the urgent-care script first for red-flag text | confirm process owner |
| Q8 | What could go wrong, and what stops it? | §6 | complete |
| Q9 | Is a DPIA required at all? | `TO CONFIRM WITH COUNSEL` — the project assumes yes (systematic, sensitive, minors at scale) | counsel |
| Q10 | Who approves this DPIA and when is it reviewed? | §8 sign-off; review on any material change | open |

## 6. Risks and controls

Seeded from `/docs/hazard-log.md` and the assumptions register.

| Risk | Impact | Control (in code) | Test / evidence | Residual |
|---|---|---|---|---|
| R1 A minor's raw symptom data reaches school staff | severe (stigma, harm) | nurses see pseudonym + band + actions only; corridor decrypts only the computed-feature snapshot; re-identification gated and audited | RBAC denial tests; `corridor_case_viewed` audit; role matrix | low |
| R2 Shared-phone exposure of results | high | no results history on the handset; generic SMS wording; "clear the call log" first-screen note; USSD/SMS string lints | Phase 3/4 string lints; hazard HZ-06 | medium (carrier log) |
| R3 Guardian becomes the source of risk | severe | RED-only generic alerts; safeguarding override skips the guardian and records `skipped_safeguarding` | `guardian_alerts` tests; HZ-04 | low |
| R4 Re-identification misuse | high | ORANGE/RED or contact request only; typed reason; encrypted mapping; audit entry | re-identify tests; HZ-05 | low |
| R5 LLM leaks a diagnosis or contradicts the engine | severe | red flags route before the LLM; post-filter rejects diagnosis claims, drug+dose, band mismatch; answers must cite chunks | 170-case guardrail suite; HZ-07 | low |
| R6 Data loss / silent corruption | high | append-only event versions, idempotency keys, hash-chained audit, encrypted nightly backups with a restore drill | sync property tests; chain verifier; backup/restore drill | low |
| R7 Excess retention | medium | configurable retention + purge job (A3) | purge tests | medium until counsel confirms periods |
| R8 Unlawful transfer / processor without safeguards | high | processors listed here; no diary content to the LLM API; `TO CONFIRM` for host/region | §7 register | open |
| R9 Breach (exfiltration of the encrypted diary store) | severe | per-record envelope encryption; keys are not in the DB; documented breach runbook with a tabletop drill | `/docs/breach-runbook.md`; drill to be executed at the final gate | medium |
| R10 Voucher fraud / mis-issued product | medium | single-use expiring codes, registered pharmacy, per-student term cap, no medicine name, idempotent verified callbacks | voucher + reconciliation tests; HZ-10 | low |

## 7. Cross-border transfer and processor register

| Processor | Purpose | Data received | Location | Safeguard | Status |
|---|---|---|---|---|---|
| VPS / hosting provider | application + database + encrypted backups | all D1–D13 (encrypted at rest) | `TO CONFIRM` (prefer Kenyan region) | DPAs, TLS 1.3, envelope encryption | open |
| Africa's Talking | USSD + SMS transport | phone number, session input; **no names, no conditions, no scores** (SPEC §3.5) | `TO CONFIRM` | contract + channel limits | H2 |
| WhatsApp Business / Turn.io | WhatsApp assessment channel | phone number, answers in transit; generic outbound wording only | `TO CONFIRM` | contract + channel limits | H4 |
| Safaricom Daraja (M-Pesa) | voucher payments | payment reference, phone hash — no clinical data | Kenya | contract | H3 |
| Jitsi host (if external) | telehealth rooms | audio/video in session; **no recording** | `TO CONFIRM` | JWT-gated one-time rooms | H12 |
| Hosted LLM API (if enabled) | education answers | engine band, indicator names, retrieved public chunks — **never identifiers or diary content** (A36) | `TO CONFIRM` | contract + no-identifiers design | H15 |
| bge-m3 embedding server (if enabled) | RAG indexing/search | public content-library chunks only | `TO CONFIRM` | n/a (public content) | H15 |

## 8. Sign-off

Nothing is approved by writing in this file alone; attach the DPO's and
counsel's written opinion.

| Role | Name | Registration / reference | Date | Signature |
|---|---|---|---|---|
| Data Protection Officer | | | | |
| Legal counsel (Kenya) | | | | |
| Maintainer (Kairon Technologies Ltd) | | | | |
| Clinical safety officer | | | | |

## 9. Outcome

- [ ] Approved
- [ ] Approved with conditions (list)
- [ ] Not approved
- [ ] Re-submit after: `<change>`

Conditions / notes:
