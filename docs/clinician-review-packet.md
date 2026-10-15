# SISI Health — Clinician Review Packet (DRAFT RULES, NOT VALIDATED)

Every rule below ships `clinically_validated: false` and must be signed off
by a licensed Kenyan clinician before the app enables it for real users
(non-negotiable 3). Review each rule, its evidence, and its test cases.

Generated: 2026-10-15T11:41:35.860937

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

## Rule: redflag-intermenstrual-bleeding v1.0.0

- Condition indicator: `intermenstrual_bleeding`
- Minimum age: 13
- Red flag: True
- Output band when matched: `ORANGE`
- Inputs: intermenstrual_bleeding_signal
- Logic: `{"op": "eq", "input": "intermenstrual_bleeding_signal", "value": true}`

### Evidence

- [clinical_guideline] Comprehensive Cervical Cancer Control: A Guide to Essential Practice — WHO (2014) https://www.who.int/publications/i/item/9789241548953
  - Note: Bleeding between periods is a symptom that warrants clinical evaluation. Cervical screening module (spec 5.4.1): minimum band 'see a doctor soon'. DRAFT pending Kenyan clinician sign-off.
- [health_authority] National Cancer Screening Guidelines — Kenya Ministry of Health (no URL — verify at review)
  - Note: Abnormal vaginal bleeding is among the symptoms prompting referral under the national screening guideline. DRAFT pending Kenyan clinician sign-off and MoH confirmation.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-persistent-discharge v1.0.0

- Condition indicator: `persistent_discharge`
- Minimum age: 13
- Red flag: True
- Output band when matched: `ORANGE`
- Inputs: unusual_discharge_days_90d
- Logic: `{"op": "gte", "input": "unusual_discharge_days_90d", "value": 5}`

### Evidence

- [clinical_guideline] Guidelines for the management of symptomatic sexually transmitted infections — WHO (2021) https://www.who.int/publications/i/item/9789240024168
  - Note: Persistent abnormal vaginal discharge warrants clinical evaluation. The 5-days-in-90 persistence threshold is a DRAFT pending Kenyan clinician sign-off.
- [health_authority] National Guidelines on Syndromic Management of Sexually Transmitted Infections — Kenya Ministry of Health (no URL — verify at review)
  - Note: Abnormal vaginal discharge is managed under the national syndromic STI guideline. DRAFT pending Kenyan clinician sign-off and MoH confirmation.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-postcoital-bleeding v1.0.0

- Condition indicator: `postcoital_bleeding`
- Minimum age: 18
- Red flag: True
- Output band when matched: `ORANGE`
- Inputs: postcoital_bleeding_signal
- Logic: `{"op": "eq", "input": "postcoital_bleeding_signal", "value": true}`

### Evidence

- [clinical_guideline] Comprehensive Cervical Cancer Control: A Guide to Essential Practice — WHO (2014) https://www.who.int/publications/i/item/9789241548953
  - Note: Post-coital bleeding is a symptom that warrants clinical evaluation. Cervical screening module (spec 5.4.1): minimum band 'see a doctor soon'. DRAFT pending Kenyan clinician sign-off.
- [clinical_guideline] Suspected cancer: recognition and referral (NG12) — NICE (2015) https://www.nice.org.uk/guidance/ng12
  - Note: Unexplained post-coital bleeding in women warrants referral consideration. Threshold and band are a DRAFT pending Kenyan clinician sign-off.

### Changelog

- 1.0.0: Initial draft from published guidance. clinically_validated=false pending Kenyan clinician sign-off.

### Sign-off

Reviewer name: ______________________________
KMPDC registration no: ______________________
Signature: ______________  Date: ____________

## Rule: redflag-postmenopausal-bleeding v1.0.0

- Condition indicator: `postmenopausal_bleeding`
- Minimum age: 45
- Red flag: True
- Output band when matched: `ORANGE`
- Inputs: postmenopausal_bleeding_signal
- Logic: `{"op": "eq", "input": "postmenopausal_bleeding_signal", "value": true}`

### Evidence

- [clinical_guideline] Suspected cancer: recognition and referral (NG12) — NICE (2015) https://www.nice.org.uk/guidance/ng12
  - Note: Post-menopausal bleeding warrants referral consideration. The 45+ age threshold is a DRAFT pending Kenyan clinician sign-off.
- [clinical_guideline] Comprehensive Cervical Cancer Control: A Guide to Essential Practice — WHO (2014) https://www.who.int/publications/i/item/9789241548953
  - Note: Bleeding after menopause warrants clinical evaluation. DRAFT pending Kenyan clinician sign-off.

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
- `gc-13-postcoital-boundary-18` — age 18, 60 diary days → band `ORANGE`, indicators ['redflag-postcoital-bleeding']
- `gc-14-postcoital-adult` — age 25, 60 diary days → band `ORANGE`, indicators ['redflag-postcoital-bleeding']
- `gc-15-minor-postcoital-floor` — age 17, 60 diary days → band `ORANGE`, indicators []
- `gc-16-minor-postcoital-severe-pain` — age 15, 60 diary days → band `RED`, indicators ['redflag-severe-acute-pain']
- `gc-17-intermenstrual-adult` — age 24, 60 diary days → band `ORANGE`, indicators ['redflag-intermenstrual-bleeding']
- `gc-18-intermenstrual-boundary-13` — age 13, 60 diary days → band `ORANGE`, indicators ['redflag-intermenstrual-bleeding']
- `gc-19-postmenopausal-boundary-45` — age 45, 60 diary days → band `ORANGE`, indicators ['redflag-postmenopausal-bleeding']
- `gc-20-postmenopausal-gated-at-44` — age 44, 60 diary days → band `GREEN`, indicators []
- `gc-21-postmenopausal-adult` — age 60, 60 diary days → band `ORANGE`, indicators ['redflag-postmenopausal-bleeding']
- `gc-22-discharge-boundary-5` — age 24, 60 diary days → band `ORANGE`, indicators ['redflag-persistent-discharge']
- `gc-23-discharge-below-threshold` — age 24, 60 diary days → band `GREEN`, indicators []
- `gc-24-discharge-persistent` — age 24, 60 diary days → band `ORANGE`, indicators ['redflag-persistent-discharge']
- `gc-25-postcoital-plus-urgent` — age 25, 60 diary days → band `RED`, indicators ['redflag-heavy-bleeding-dizziness', 'redflag-postcoital-bleeding']
- `gc-26-all-four-signals` — age 50, 60 diary days → band `ORANGE`, indicators ['redflag-intermenstrual-bleeding', 'redflag-persistent-discharge', 'redflag-postcoital-bleeding', 'redflag-postmenopausal-bleeding']
- `gc-27-minor-control` — age 17, 60 diary days → band `GREEN`, indicators []
- `gc-28-minor-intermenstrual-discharge` — age 13, 60 diary days → band `ORANGE`, indicators ['redflag-intermenstrual-bleeding', 'redflag-persistent-discharge']
- `gc-29-postcoital-missing-input` — age 25, 60 diary days → band `ORANGE`, indicators ['redflag-postcoital-bleeding']
- `gc-30-discharge-missing-input` — age 25, 60 diary days → band `ORANGE`, indicators ['redflag-persistent-discharge']
- `gc-31-postcoital-wrong-type` — age 25, 60 diary days → band `ORANGE`, indicators ['redflag-postcoital-bleeding']
- `gc-32-minor-postcoital-self-harm` — age 17, 60 diary days → band `RED`, indicators ['redflag-self-harm']
- `gc-33-discharge-3-control` — age 18, 60 diary days → band `GREEN`, indicators []
- `gc-34-postcoital-plus-postmenopausal` — age 45, 60 diary days → band `ORANGE`, indicators ['redflag-postcoital-bleeding', 'redflag-postmenopausal-bleeding']
- `gc-35-intermenstrual-plus-anemia` — age 30, 60 diary days → band `ORANGE`, indicators ['anemia-risk-flag', 'redflag-intermenstrual-bleeding']
- `gc-36-minor-discharge-only` — age 16, 60 diary days → band `ORANGE`, indicators ['redflag-persistent-discharge']
- `gc-37-minor-postcoital-endo` — age 17, 75 diary days → band `ORANGE`, indicators ['endo-indicator']
