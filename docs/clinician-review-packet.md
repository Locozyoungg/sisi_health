# SISI Health — Clinician Review Packet (DRAFT RULES, NOT VALIDATED)

Every rule below ships `clinically_validated: false` and must be signed off
by a licensed Kenyan clinician before the app enables it for real users
(non-negotiable 3). Review each rule, its evidence, and its test cases.

Generated: 2026-10-14T16:27:04.096575

## Rule: anemia-risk-flag v1.0.0

- Condition indicator: `anemia_risk`
- Minimum age: 13
- Red flag: False
- Output band when matched: `ORANGE`
- Inputs: avg_bleeding_volume_90d, fatigue_ratio_30d
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "avg_bleeding_volume_90d", "value": 3}, {"op": "gte", "input": "fatigue_ratio_30d", "value": 0.5}]}`

### Evidence

- [health_authority] Anaemia fact sheet — WHO https://www.who.int/news-room/fact-sheets/detail/anaemia
  - Note: Heavy menstrual bleeding plus fatigue suggests possible anaemia. Draft thresholds pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: endo-indicator-adult v1.0.0

- Condition indicator: `endometriosis_indicator`
- Minimum age: 18
- Red flag: False
- Output band when matched: `ORANGE`
- Inputs: cyclical_pain_ratio_90d, dyspareunia
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "cyclical_pain_ratio_90d", "value": 0.6}, {"op": "eq", "input": "dyspareunia", "value": true}]}`

### Evidence

- [clinical_guideline] Endometriosis: diagnosis and management (NG73) — NICE (2017) https://www.nice.org.uk/guidance/ng73
  - Note: Cyclical pain with dyspareunia is a recognised endometriosis indicator. Age-gated to 18+ per spec 5.1: minors never see sexual-health questions. Draft thresholds pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: endo-indicator v1.0.0

- Condition indicator: `endometriosis_indicator`
- Minimum age: 13
- Red flag: False
- Output band when matched: `ORANGE`
- Inputs: cyclical_pain_ratio_90d, dyschezia
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "cyclical_pain_ratio_90d", "value": 0.6}, {"op": "eq", "input": "dyschezia", "value": true}]}`

### Evidence

- [clinical_guideline] Endometriosis: diagnosis and management (NG73) — NICE (2017) https://www.nice.org.uk/guidance/ng73
  - Note: Cyclical pain with dyschezia is a recognised endometriosis indicator (all ages 13+). Draft thresholds pending Kenyan clinician sign-off. Dyspareunia is handled by endo-indicator-adult (min_age 18).

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: fibroid-indicator v1.0.0

- Condition indicator: `fibroid_indicator`
- Minimum age: 13
- Red flag: False
- Output band when matched: `ORANGE`
- Inputs: avg_bleeding_volume_90d, pelvic_pressure, urinary_frequency
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "avg_bleeding_volume_90d", "value": 3}, {"op": "or", "operands": [{"op": "eq", "input": "pelvic_pressure", "value": true}, {"op": "eq", "input": "urinary_frequency", "value": true}]}]}`

### Evidence

- [clinical_guideline] Diagnosis of Abnormal Uterine Bleeding in Reproductive-Aged Women (Practice Bulletin No. 128) — ACOG (2012) https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2012/07/diagnosis-of-abnormal-uterine-bleeding-in-reproductive-aged-women
  - Note: Heavy bleeding with bulk symptoms (pressure, urinary frequency) warrants structural evaluation. Draft thresholds pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: pcos-indicator v1.0.0

- Condition indicator: `pcos_indicator`
- Minimum age: 13
- Red flag: False
- Output band when matched: `ORANGE`
- Inputs: cycle_irregularity_90d, androgenic_symptoms
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "cycle_irregularity_90d", "value": 7}, {"op": "eq", "input": "androgenic_symptoms", "value": true}]}`

### Evidence

- [clinical_guideline] Polycystic Ovary Syndrome (Practice Bulletin No. 194) — ACOG (2018) https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2018/06/polycystic-ovary-syndrome
  - Note: Cycle irregularity plus androgenic symptoms reflects part of the Rotterdam criteria. Draft thresholds pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-heavy-bleeding-dizziness v1.0.0

- Condition indicator: `heavy_bleeding_dizziness`
- Minimum age: 13
- Red flag: True
- Output band when matched: `RED`
- Inputs: avg_bleeding_volume_90d, dizziness_signal
- Logic: `{"op": "and", "operands": [{"op": "gte", "input": "avg_bleeding_volume_90d", "value": 3}, {"op": "eq", "input": "dizziness_signal", "value": true}]}`

### Evidence

- [clinical_guideline] Heavy menstrual bleeding: assessment and management (NG88) — NICE (2018) https://www.nice.org.uk/guidance/ng88
  - Note: Draft: heavy bleeding with dizziness is an urgent-care signal. Threshold is a DRAFT pending Kenyan clinician sign-off.
- [health_authority] Anaemia fact sheet — WHO https://www.who.int/news-room/fact-sheets/detail/anaemia
  - Note: Heavy menstrual bleeding is a common cause of iron-deficiency anaemia; dizziness may indicate significant blood loss.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-self-harm v1.0.0

- Condition indicator: `self_harm`
- Minimum age: 13
- Red flag: True
- Output band when matched: `RED`
- Inputs: self_harm_signal
- Logic: `{"op": "eq", "input": "self_harm_signal", "value": true}`

### Evidence

- [health_authority] Suicide fact sheet — WHO https://www.who.int/news-room/fact-sheets/detail/suicide
  - Note: Self-harm signals require urgent care and, for minors, safeguarding routing (spec 3.3) — never a guardian alert with symptom detail.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-severe-acute-pain v1.0.0

- Condition indicator: `severe_acute_pain`
- Minimum age: 13
- Red flag: True
- Output band when matched: `RED`
- Inputs: max_pain_90d
- Logic: `{"op": "gte", "input": "max_pain_90d", "value": 9}`

### Evidence

- [clinical_guideline] Endometriosis: diagnosis and management (NG73) — NICE (2017) https://www.nice.org.uk/guidance/ng73
  - Note: Draft threshold: NRS 9+ as a marker of severe acute pain warranting urgent assessment. Threshold is a DRAFT pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

# Golden test cases (the engine MUST pass every one)

- `gc-01-normal` — age 24, 60 diary days → band `GREEN`, indicators []
- `gc-02-anemia` — age 24, 60 diary days → band `ORANGE`, indicators ['anemia-risk-flag']
- `gc-03-heavy-bleeding-dizziness` — age 24, 60 diary days → band `RED`, indicators ['redflag-heavy-bleeding-dizziness', 'anemia-risk-flag']
- `gc-04-severe-pain` — age 24, 30 diary days → band `RED`, indicators ['redflag-severe-acute-pain']
- `gc-05-self-harm` — age 15, 45 diary days → band `RED`, indicators ['redflag-self-harm']
- `gc-06-pcos` — age 20, 90 diary days → band `ORANGE`, indicators ['pcos-indicator']
- `gc-07-endo-minor` — age 15, 75 diary days → band `ORANGE`, indicators ['endo-indicator']
- `gc-08-endo-adult` — age 25, 75 diary days → band `ORANGE`, indicators ['endo-indicator', 'endo-indicator-adult']
- `gc-09-fibroid` — age 38, 80 diary days → band `ORANGE`, indicators ['fibroid-indicator']
- `gc-10-insufficient-data` — age 24, 13 diary days → band `NOT_ENOUGH_DATA`, indicators []
- `gc-11-boundary-14-days` — age 24, 14 diary days → band `GREEN`, indicators []
- `gc-12-red-flag-asymmetry` — age 24, 50 diary days → band `RED`, indicators ['redflag-severe-acute-pain']
