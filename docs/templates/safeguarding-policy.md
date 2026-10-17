# Child Safeguarding Policy — TEMPLATE

> **Status: TEMPLATE — adopt and sign before any real pupil uses SISI.**
> Pre-seeded with the rules the software actually enforces (SPEC §3.3, §6), so
> that the adopting school or organisation only has to name people, fill local
> contacts, and sign. Placeholders are in `[SQUARE BRACKETS]`. Hotline numbers
> **116 (child helpline)** and **1195 (GBV)** are carried in configuration
> marked `UNVERIFIED` (assumption A4) — they must be verified by a human before
> launch (human task **H9**).

| Field | Value |
|---|---|
| Organisation | `[SCHOOL / ORGANISATION NAME]` |
| Policy version | 0.1 draft template |
| Owner | `[DESIGNATED SAFEGUARDING LEAD — name, role, phone]` |
| Deputy | `[NAME, ROLE, PHONE]` |
| Applies to | all staff with a SISI staff account, all pupils using the SISI USSD/WhatsApp/app channel, and all contractors |
| Review cycle | annually, and after any safeguarding incident or system change |
| Related documents | `/docs/hazard-log.md` (HZ-04, HZ-05, HZ-06, C5), `/docs/breach-runbook.md`, `/docs/templates/clinical-safety-case.md` |

## 1. Principles

1. **The child's safety comes before the guardian's right to know.** Where the
   guardian may be the source of risk, the guardian is not told.
2. **No symptom detail ever reaches a guardian.** Guardian messages are generic
   by design and by test (SPEC §3.3).
3. **A pupil's private data is hers.** Staff see a pseudonym and a severity
   band. They never see diary content or assessment answers.
4. **Uncertainty escalates upward.** The rules engine resolves uncertain
   red-flag inputs to *matched*; a minor reporting post-coital bleeding is
   floored at ORANGE and flagged as safeguarding.
5. **The software supports adults; it does not replace them.** No alert is a
   substitute for a person who knows the child.

## 2. What the system enforces (implemented and tested)

| Rule | Where it lives | Test / evidence |
|---|---|---|
| Users under 13 are blocked at the age check | app age gate; USSD `age_blocked` screen; `RuleEngine` raises for `age < 13` | `backend/tests/test_rules_engine.py`, gateway age-gate tests |
| Guardian alerts are **RED band only**, and always generic | `backend/app/school/service.py` `guardian_alerts()`, `GUARDIAN_ALERT_TEXT` | school guardian-alert tests |
| Safeguarding override: flagged assessments **never** alert a guardian; the skip is recorded as `skipped_safeguarding` | `guardian_alerts()` reads the decrypted payload's `safeguarding` flag; `school.guardian_alerts.status` | `backend/tests/test_school_*.py`; hazard HZ-04 |
| Safeguarding categories | `backend/app/rules/redflags.py` `SAFEGUARDING_CATEGORIES` = `self_harm`, `abuse_signal`, `pregnancy_concern_minor`, `guardian_risk`, matched from `ontology/redflags/*.json` in en/sw/sheng | `backend/tests/test_redflag_patterns.py` |
| Urgent-care script first | text red flags are matched **before any LLM**; the urgent script with hotlines is generated deterministically | `ai_service/tests/test_service.py` (helplines present), `scripts/eval_guardrails.py --ci` |
| Nurses see pseudonyms + bands only; re-identification needs ORANGE/RED or a contact request, a typed reason, and writes an audit entry | `backend/app/school/service.py` `queue()` / `reidentify()` | school tests; `student_reidentified` audit event |
| Minors' consults require recorded guardian consent + the minor's own assent; a chaperone is confirmed before a session starts if requested | `backend/app/corridor/consult.py` `_require_minor_consents()`, `_require_chaperone()` | corridor consult tests |
| A minor's post-coital bleeding is a safeguarding signal and can never produce self-care guidance | `RuleEngine._evaluate_common()` (band floored at ORANGE, `safeguarding=True`) | golden cases; cervical rule tests; hazard C5 |
| Consultation rooms are one-time and unrecorded | `corridor.consult_sessions` (`recorded IS FALSE` CHECK) + JWT room claims `features.recording = false` | corridor session tests |
| Nothing condition-identifying in notifications, SMS, USSD screens, filenames, or the app-switcher preview | channel string lints + discreet launcher alias | Phase 3/4 string lints; `StringsPrivacyTest` |

## 3. Roles and responsibilities

| Role | Responsibility | Named person |
|---|---|---|
| Designated Safeguarding Lead (DSL) | receives safeguarding escalations, decides on statutory reporting, owns this policy | `[NAME]` |
| Deputy DSL | covers absence of the DSL | `[NAME]` |
| School nurse | reviews the flagged queue, records actions, re-identifies only within the rules, runs the guardian-consent path | `[NAME]` |
| School admin | manages school staff accounts, reviews the monthly access log | `[NAME]` |
| Clinical lead (gynecologist) | clinical oversight, signs off rules and content | `[NAME]` |
| Platform operator (Kairon) | keeps the technical controls working, reports breaches, runs audits | `[NAME]` |

## 4. Escalation procedure

1. **System signal.** An assessment or conversation raises `safeguarding`
   (self-harm, abuse, pregnancy concern in a minor, or guardian risk). The
   system suppresses the guardian alert and records `skipped_safeguarding`.
2. **Same-day human review.** The nurse on duty opens the flagged case in the
   console and notifies the DSL **the same working day** — by phone if the
   signal is `abuse_signal`, `pregnancy_concern_minor`, `guardian_risk`, or
   `self_harm`.
3. **Immediate risk.** For self-harm or disclosed abuse: do not leave the pupil
   alone; contact the DSL immediately; if there is immediate danger contact
   `[LOCAL EMERGENCY NUMBER — 999 or 112, confirm]` and the child helpline
   **116** *(UNVERIFIED — verify before launch, H9)*.
4. **GBV.** Where sexual violence is disclosed or suspected: the GBV helpline
   **1195** *(UNVERIFIED)*, and the facility/GBV recovery centre path
   `[COUNTY PATHWAY]`.
5. **Do not alert the guardian** where the guardian may be the source of risk.
   The DSL decides who else (if anyone) is told; the decision and its reason
   are recorded in the school's safeguarding register.
6. **Do not interview the child for evidence.** Record what was said, when, and
   by whom, in the child's own words, and hand it to the DSL.
7. **Statutory reporting.** `[CONFIRM the mandatory-reporting pathway and
   timelines with counsel and the county children's officer — this is not
   specified by the software and must not be guessed.]`

## 5. Helplines and contacts (verify before launch — H9)

| Purpose | Number | Status |
|---|---|---|
| Child helpline (Kenya) | **116** | UNVERIFIED — config `SISI_HELPLINE_CHILD` |
| GBV helpline (Kenya) | **1195** | UNVERIFIED — config `SISI_HELPLINE_GBV` |
| Emergency services | `[999 / 112 — confirm]` | to confirm |
| DSL | `[NAME, PHONE, EMAIL]` | to fill |
| Deputy DSL | `[NAME, PHONE, EMAIL]` | to fill |
| County children's officer | `[NAME, PHONE]` | to fill |
| Nearest GBV recovery centre | `[NAME, LOCATION, PHONE]` | to fill |
| Platform operator incident line | `[PHONE]` | to fill |

These values are configuration, never hard-coded: change them in the deployed
`SISI_HELPLINE_*` environment values and the urgent-care scripts pick them up
(the AI service reads them from the backend settings, and tests assert both
appear in the urgent script).

## 6. Staff vetting, accounts, and access

| Requirement | Status |
|---|---|
| Every staff member with a SISI account has a valid background/police clearance check on file | `[PROCESS TO RUN]` |
| Every staff member signs this policy and the confidentiality undertaking before an account is created | `[PROCESS TO RUN]` — **note: the software does not yet enforce an in-app policy acknowledgement; this is a manual gate at account creation until implemented** |
| Staff accounts are individual (no shared logins), email + password + TOTP, 15-minute idle timeout | implemented |
| RBAC: each role sees only the data classes in `/docs/role-matrix.md` | implemented; RBAC denial tests |
| Access to any minor's record is logged and reviewed monthly | audit events exist (`corridor_case_viewed`, `student_reidentified`, `assessment_action`); `[SET UP THE MONTHLY REVIEW]` |
| A staff member who leaves has their account disabled the same day | `[PROCESS TO RUN]` |

## 7. Data handling rules for staff

- Never photograph, screenshot, or copy anything from the console.
- Never discuss a pupil's band or status in a public area or on a personal
  phone; never name a condition.
- Never write symptom details into SMS, WhatsApp, email, or the school's paper
  records.
- Re-identify only when the rules allow it, and only with a typed reason.
- Report a suspected exposure (lost phone, shared screen, wrong recipient) the
  same day, following `/docs/breach-runbook.md`.

## 8. Complaints

A pupil, guardian, or staff member may complain about the use of SISI data to
`[DESIGNATED CONTACT]`, and to the Office of the Data Protection Commissioner
(ODPC) `[CONFIRM CURRENT CONTACT DETAILS]`. Complaints are logged in
`[REGISTER]` and reviewed by the DSL.

## 9. Adoption and sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Head teacher / organisation lead | | | |
| Designated Safeguarding Lead | | | |
| School nurse | | | |
| Clinical lead | | | |
| Platform operator (Kairon Technologies Ltd) | | | |

**This template does not by itself make the deployment compliant.** Adoption,
staff training completion, and hotline verification (H9) must be recorded here
before SISI is enabled for real pupils.
