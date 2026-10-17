# Impact Metrics — definitions and measurement plan

> **Audience:** grant reviewers (UNICEF Venture Fund), the monitoring &
> evaluation (M&E) owner, and the school/employer partners who receive aggregate
> reporting.
>
> **Status:** definitions and plan are final drafts; **no measured values exist
> and none may be invented.** Every number in the repository today is synthetic.
> Baseline collection starts with the first real pilot term (human tasks H5
> DPIA, H8 pentest, H7 clinician sign-off, H11 ethics approval for the separate
> validation study all precede it).
>
> **Measurement principle:** SISI reports **aggregates only**. No metric below
> is ever reported per person, per pupil, or per band cell smaller than the
> k-anonymity floor. Every aggregate is computed through the single shared
> module `backend/app/k_anon.py` (cells < 5 suppressed with complementary
> suppression; a school or employer publishes nothing until 20 subjects exist —
> below that the answer is `not_enough_data`, never a zero).

## 1. Metric definitions

### M1 — School-days-missed delta

**Definition.** The change in self-reported school days missed because of
symptoms, for a cohort of students in a school term, between a baseline
measurement and a follow-up measurement.

**Instrument.** Question 4 of the USSD/WhatsApp assessment
(`ussd-whatsapp/gateway/flows/assessment.py`, key `days_missed`):
*"How many school days have you missed this term because of how you feel?"*
(integer 0–60; Kiswahili wording in `gateway/flows/screens.py`). The answer is
stored inside the envelope-encrypted assessment payload — there is no plaintext
column for it.

**Formula (per school, per term t):**

```
mean_missed(t)   = Σ days_missed_i / n_t        for all eligible assessments i in term t
delta(t)         = mean_missed(t) − mean_missed(baseline)
delta_pct(t)     = 100 × delta(t) / mean_missed(baseline)      (only if baseline ≥ 20 assessments)
```

Reported alongside: `n_t` (assessments), the number of distinct students
(pseudonyms) contributing, and the band distribution of the same cohort
(k-anonymised).

**Measurement plan.**

| Step | Cadence | Owner | Notes |
|---|---|---|---|
| Baseline sweep: every enrolled student completes an assessment in the first two weeks of the pilot term | once, term 1 | School nurse + M&E | baseline = that term's mean |
| Follow-up sweep: the same cohort re-assessed near term end | termly | School nurse + M&E | the same question, the same channel where possible |
| Compute `mean_missed` and `delta` through an aggregation job that decrypts the payload field in-process and publishes only k-anonymised cells | termly | Platform operator | the job does not exist yet — see §3 |
| Publish to the school dashboard as a term report | termly | School admin | suppressed cells render as "—"; below 20 assessments: "Not enough data yet" |

**Confounders that must be recorded with the number** (otherwise the delta is
not interpretable): term length and exam periods; school closures and strikes;
seasonal illness; the school feeding programme; whether the pupil received a
voucher; self-report and recall bias (the question asks about the current
term); and the fact that a pupil may complete an assessment more than once, in
which case the *latest* assessment per pseudonym in the term counts.

**What this metric does not claim.** A change in school-days-missed does not
demonstrate clinical benefit, and SISI does not present it as one. It is an
access-and-burden indicator.

### M2 — Time to first clinical contact (TTFCC)

**Definition.** The elapsed time between the moment a person's triage result
first indicates that a clinician should see her, and the moment a recorded
clinical contact occurs.

**Clock start (per channel).**

| Channel | Start timestamp | Source |
|---|---|---|
| School (USSD / WhatsApp) | assessment completion — `diary.school_assessments.created_at` (the band is inside the encrypted payload) | assessment row |
| App / diary | the first rules evaluation whose band is YELLOW or above — `diary.rule_evaluations.created_at` (band inside the encrypted payload) | evaluation row |
| Corridor booking | consult request creation — `corridor.consult_requests.created_at` | request row |

**Clock stop — first of any recorded clinical contact:**

| Contact | Timestamp | Source |
|---|---|---|
| Nurse action on the assessment (`spoke_to`, `contacted`, `referred`, `escalated`) | `school.assessment_actions.created_at` | action row |
| Consult reviewed/approved by a nurse or gynecologist | `corridor.consult_events.created_at` for the status change | consult event |
| Telehealth session started | `corridor.consult_sessions.started_at` | session row |
| Referral sent to a facility (patient-approved) | `corridor.referrals.sent_at` | referral row |
| Follow-up tracker opened | `corridor.follow_up_tracker.created_at` | tracker row |

**Formula.**

```
TTFCC_i = min(stop timestamps_i) − start timestamp_i        (hours)
Report: median, p75, and the share contacted within 24 h / 72 h / 7 days,
stratified by band (YELLOW / ORANGE / RED) and by age band (13–17 / 18+).
```

**Exclusions (recorded in the report):** rows belonging to a user whose consent
was revoked or who was erased mid-window; duplicate actions by the same actor
in the same hour; synthetic/demo seed rows (`*@sisi.demo`, fixed demo UUIDs).

**Targets.** No target is asserted here. The pilot's first term establishes the
observed baseline; a target (for example "median < 48 h for RED") is set with
the clinical lead and the school partners after baseline, and recorded as an
amendment to this document.

### M3 — Secondary indicators (spec §5.5 outcomes)

| Indicator | Definition | Source |
|---|---|---|
| Assessments completed | count of `diary.school_assessments` in period, by channel | assessment rows (counts only) |
| Red-flag coverage | share of RED-band assessments with a recorded nurse action | assessments × actions |
| Referrals completed | count of `corridor.referrals` reaching `sent` (patient-approved) | referral rows |
| Consults delivered | count of `corridor.consult_sessions` reaching `completed` | session rows |
| Screening follow-up retention | share of `corridor.follow_up_tracker` rows not `lost_to_follow_up` | already published k-anonymised by `tracking.aggregates()` |
| Voucher redemption | redeemed / issued, by term | `school.vouchers`, `school.voucher_redemptions` |
| Engagement | distinct pupils completing ≥ 4 diary days in a 30-day window | encrypted diary rows (counts only) |

## 2. Privacy and ethics constraints on measurement

1. **Aggregates only**, through `app/k_anon.py`. A metric cell below 5 is
   suppressed; complementary suppression prevents subtraction; a school with
   fewer than 20 assessments reports nothing.
2. **No identifier joins in reporting.** Metrics are computed from pseudonyms
   and IDs inside the aggregation job; the published output has no per-person
   key, and the exported report has no re-identifying column.
3. **Minors.** A minor's metric contribution is included only in aggregate.
   Guardians are never given symptom-level reporting. Any per-pupil follow-up
   decision is made by school clinical staff from the console, not from a
   report.
4. **Separate research ethics.** Any measurement intended for publication —
   including the sensitivity/specificity validation study against clinician
   assessment (human task **H11**) — requires its own ethics approval and
   participant consent wording, and is out of scope for operational reporting.
5. **Consent basis.** Operational M&E runs on the same consent recorded at
   assessment; an amendment to the DPIA (`/docs/templates/dpia-template.md`,
   §4) and to the consent text is required before any new metric is collected.

## 3. Instrumentation status (what exists, what is missing)

| Capability | Status |
|---|---|
| Assessment capture with `days_missed` in the encrypted payload | implemented (gateway flow) |
| Nurse action recording with timestamps | implemented (`school.assessment_actions`) |
| Consult/session/referral timestamps | implemented (`corridor` schema) |
| k-anonymity module + property tests | implemented (`app/k_anon.py`) |
| Follow-up tracker aggregate (status counts, suppressed cells) | implemented (`corridor.tracking.aggregates`) |
| Assessment / school dashboard aggregates (bands, totals) | implemented (school + employer dashboards) |
| Band distribution per school reaching 20+ assessments | implemented (school dashboard) |
| **M1 aggregation job** (decrypt `days_missed`, compute per-term mean/delta, publish k-anonymised) | **to build** — Phase 9 / pilot-prep work; must reuse `app/k_anon.py` |
| **M2 TTFCC job** (join start/stop timestamps, compute median/p75, stratify) | **to build** — same constraint |
| Funder-facing report template | **to write** — quarterly, aggregate-only |

Both missing jobs are read-only aggregations over encrypted payloads. Each
requires: a reviewed query that decrypts in-process, a property test proving no
cell below the floor is published, an audit event per run with counts only, and
a privacy sign-off before it is enabled for real data.

## 4. Reporting cadence and template

| Audience | Cadence | Contents |
|---|---|---|
| School partner | termly | assessments completed, band distribution (k-anon), school-days-missed delta, referrals, vouchers, "not enough data" where applicable |
| Employer partner | quarterly | linked-employee engagement and band cells (k-anon, employer admin only) |
| MoH / aggregate viewer | quarterly | corridor aggregates, follow-up retention, screening funnel — k-anonymised only |
| Funders / public | semi-annual | pilot reach, TTFCC, screening funnel, safety indicators (hazard-log events, overrides used), plus a limitations statement |

Every published report carries: the reporting period, `n` per cell, the
suppression rule applied, the confounders listed in §1, and the standing
limitation that **SISI supports a clinician's judgement and does not diagnose**.
