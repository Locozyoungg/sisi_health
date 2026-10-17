# Clinical Safety Case — TEMPLATE

> **Status: TEMPLATE — unsigned. The system must not be used for real patients
> until a named clinical safety officer signs this case.**
> The hazard table is pre-filled from `/docs/hazard-log.md` (spec §6) with the
> controls and tests that exist in the repository today. Columns
> **Residual risk** and the sign-off block are deliberately empty: a clinician
> fills them.
>
> Nothing in this document presents draft rules as validated. Every triage rule,
> red-flag script, and education chunk ships with `clinically_validated: false`
> and empty `reviewer_name` / `reviewer_registration_no` / `signed_at`; the
> engine refuses to serve unvalidated rules to real users (non-negotiable 3,
> assumption A10). Clinician sign-off is human task **H7**.

| Field | Value |
|---|---|
| System | SISI Health — symptom diary, deterministic triage, school program, specialist corridor, education layer |
| Version assessed | repo HEAD at time of signing: `[COMMIT]`, rule set version `ontology-1.1` |
| Clinical safety officer | `[NAME, REGISTRATION NO]` |
| Assessor | `[NAME]` |
| Date | `[YYYY-MM-DD]` |
| Scope | Kenya pilot: users 13–45, school and community channels, USSD/WhatsApp, Android app, staff consoles |

## 1. Clinical claims

| # | Claim | Argument |
|---|---|---|
| CL-1 | The system never diagnoses and never presents a band as a diagnosis | Every band and indicator is assigned by the deterministic rules engine (non-negotiable 1). The LLM layer only explains the engine's output, must cite reviewed chunks, and is filtered for diagnosis claims, drug + dose, and band mismatch |
| CL-2 | Where uncertainty exists, the system errs toward urgency | A missing or invalid red-flag input counts as *matched* (safety asymmetry); band selection is the maximum of matched rules; a minor with post-coital bleeding is floored at ORANGE |
| CL-3 | A red-flag presentation always gets the urgent script | Red-flag text detection is deterministic pattern matching (en/sw/sheng) executed **before** any model call; the LLM is never in the loop for the urgent script, which carries the helplines from config |
| CL-4 | Insufficient data is never reassurance | Fewer than 14 diary days returns `NOT_ENOUGH_DATA` with guidance, never a band |
| CL-5 | Symptoms alone never produce a "low risk" or screening-skipping message | No risk scoring from symptoms alone; no low-risk output anywhere; every screening message carries "a normal symptom check does not replace screening" |
| CL-6 | Safeguarding outranks family notification | Where inputs suggest abuse, sexual violence, pregnancy concern in a minor, self-harm, or guardian risk, the guardian is not alerted; the case is flagged for the designated safeguarding lead |

## 2. System description (what the clinician is signing for)

- **Rules**: 12 JSON rules in `/ontology/rules` (endo ×2, PCOS, fibroid, anaemia,
  4 cervical red flags, 3 general red flags) in a constrained expression-tree
  DSL (assumption A12), versioned, hashed, and activated only by a two-person
  workflow with a golden-suite gate (`backend/app/rules/service.py`).
- **Dual implementation**: the same JSON runs in Python (`backend/app/rules/`)
  and Kotlin (`mobile/`, on-device), proven identical on the shared golden file
  (`ontology/golden/cases.json`, 37 cases).
- **Bands**: GREEN self-care, YELLOW see a nurse, ORANGE see a doctor soon, RED
  urgent (assumption A9), plus the non-band `NOT_ENOUGH_DATA`.
- **Age gating**: under 13 blocked; dyspareunia and sexual-health collection is
  18+; the minor two-step gate governs AI answers (assumption A38).
- **Out of scope**: diagnosis, medication prescribing, image analysis, and any
  claim of cancer detection or exclusion (SPEC §5.4.1 hard limits).

## 3. Hazard analysis and controls

Owner column names the accountable role, not a person. **Residual risk is for
the clinical safety officer to complete after reviewing the evidence.**

| ID | Hazard | Control (as implemented) | Test / evidence | Owner | Residual risk |
|---|---|---|---|---|---|
| HZ-01 | Missed red flag | Red flags evaluated first; missing/invalid red-flag input resolves to *matched*; patterns versioned in `/ontology` | `backend/tests/test_rules_redflags.py`, golden cases | Clinician (H7) | |
| HZ-02 | False reassurance | Asymmetry upward; `NOT_ENOUGH_DATA` always carries guidance and never a band; screening disclaimer on every screening message | band tests; golden cases 11–12; cervical eval cases | Clinician (H7) | |
| HZ-03 | False alarm | All rules `clinically_validated: false` until sign-off; activation is two-person with rollback | validation tests; rollback test | Clinician (H7) | |
| HZ-04 | Guardian alert harms the child | Safeguarding override: flagged assessments skip the guardian (`skipped_safeguarding`) and route to the DSL; generic wording, no symptom detail | `backend/tests/test_school_*.py` | Safeguarding lead | |
| HZ-05 | Re-identification misuse | ORANGE/RED or contact request only; typed reason; encrypted mapping; audit entry | school re-identify tests | School lead | |
| HZ-06 | Shared-phone exposure | No history on the handset; clear-call-log note; nothing condition-identifying in USSD/SMS | 160-char + string lints | School lead | |
| HZ-07 | LLM diagnosis leakage | LLM never assigns bands; post-filter rejects diagnosis claims, drug + dose, band mismatch; answers must cite chunks | `ai_service/tests/test_guardrails.py`, `test_guardrail_data_ai.py`, `test_service.py`, `scripts/eval_guardrails.py --ci` (170 cases) | AI lead | |
| HZ-08 | Rule-version error | Versioned rules with content hash; activation runs the golden suite; instant rollback; on-device/server parity | activation + rollback tests; parity test | Clinician (H7) | |
| HZ-09 | Sync data loss | Append-only event versions; highest-version-wins per field with server-timestamp tiebreak; idempotency keys | `backend/tests/test_diary_sync.py`; property tests | Backend lead | |
| HZ-10 | Voucher fraud | Single-use expiring codes, registered pharmacy only, per-student term cap, idempotent Daraja callbacks, reconciliation flags mismatches | Phase 4 voucher + reconciliation tests | Finance lead | |
| C1 | False reassurance → woman skips screening | No risk scoring from symptoms alone; no "low risk" output; screening disclaimer enforced | `test_corridor_education.py`, `test_guardrail_data.py` | Clinician (H7) | |
| C2 | Missed red-flag bleeding | Deterministic cervical red-flag rules (minimum ORANGE); ≥25 rule cases incl. thresholds and age gating; cervical text patterns route to the urgent script pre-LLM | `test_rules_cervical.py`, golden cases gc-13..gc-37, `test_redflag_patterns.py` | Clinician (H7) | |
| C3 | Lost follow-up after a positive result | Follow-up tracker with states, reminder intervals, and a loss-to-follow-up flag (status only) | `test_corridor_tracking.py`, `test_corridor_reminders.py` | Nurse lead | |
| C4 | Stale facility data | 90-day staleness flag and warning on unverified entries | `test_corridor_facilities.py` (89/90/91-day boundaries) | Ops lead | |
| C5 | Minor's post-coital bleeding reaches a guardian without review | Minor + post-coital bleeding = safeguarding signal; band floored at ORANGE; generic nurse-referral wording; never a guardian alert with symptom detail | `test_rules_cervical.py`, `test_corridor_consult.py`, `test_corridor_strings.py` | Safeguarding lead | |

Additional safety-related items raised by the assumptions register that the
clinician should rule on:

| Ref | Item | Status |
|---|---|---|
| A21 | One-time assessments reuse the same engine without the 14-day gate, so an assessment always returns immediate guidance | draft pending sign-off |
| A27 | Post-menopausal bleeding rule `min_age` 45 (NICE NG12 / WHO cited in `evidence`) | draft |
| A28 | Persistent-discharge threshold (≥5 days in 90), WHO syndromic guidance | draft |
| A29 | Cervical red flags output ORANGE with `red_flag: true`, so `urgent` becomes true for them (conservative upward escalation) | draft |
| A38 | Minor sexual-health two-step: check question → generic guidance or education with a nurse-referral line appended after the post-filter | draft |
| A26 | Screening schedule (start age 25, annual interval) is a placeholder from cited MoH guidance; `verified: false` | pending H13 |

## 4. Evidence pack inventory

| Evidence | Location | Verified by |
|---|---|---|
| Rule definitions + evidence citations | `/ontology/rules/*.json` (`evidence` field) | reviewer reads each rule |
| Golden parity cases (37) | `/ontology/golden/cases.json` | runs on both engines |
| Clinician review packet (printable, one command) | `/docs/clinician-review-packet.md` + packet generator | reviewer signs per rule |
| Red-flag pattern lists (en/sw/sheng) | `/ontology/redflags/*.json` | reviewer reads each pattern |
| Guardrail eval suite (150 + 20 cervical cases) | `/ontology/guardrail/*.json`, `make ai-eval` | CI gate |
| Education content (8 files, en+sw) | `/ontology/content/*.json` | H16 review |
| Hazard log + this safety case | `/docs/hazard-log.md`, this file | clinical safety officer |

## 5. Limitations the clinician must accept or reject

1. Rules are **drafts from published guidance**, not locally validated
   thresholds; sensitivity/specificity against Kenyan clinician assessment is
   unmeasured (ethics approval is human task H11).
2. The pattern engine operates on self-reported diary data; adherence and
   recall bias are unquantified.
3. USSD/WhatsApp assessments deliberately set `self_harm_signal` and cervical
   signals to `False` because those questions are never asked over those
   channels (a *missing* value would trigger the asymmetry and force RED/ORANGE
   for every subscriber). A subscriber with those symptoms is therefore
   detected only if she reaches a staffed channel or the app.
4. Cervical screening messages describe screening options; the facility data is
   unverified partner data until H14.
5. No clinical decision is made by the LLM, and its education answers are
   refused when no chunk can be cited — but citation does not guarantee
   clinical completeness.
6. The AI comparison run (hosted vs open-weight) is still a stub (H15); model
   behaviour on the real provider is unverified.

## 6. Sign-off

| Role | Name | Registration no. | Date | Signature |
|---|---|---|---|---|
| Clinical safety officer (gynecologist) | | | | |
| Safeguarding lead (organisation) | | | | |
| Clinical lead — rules and content (H7) | | | | |
| Maintainer (Kairon Technologies Ltd) | | | | |

Decision:

- [ ] Safety case accepted for pilot with the listed residual risks
- [ ] Accepted with conditions: `<list>`
- [ ] Not accepted — actions required: `<list>`
