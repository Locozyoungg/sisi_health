# Data Flow

The same system as [`architecture.md`](./architecture.md), told as the journey
of the data: what is created, where it is encrypted, who can decrypt it, what
is written to the audit trail, and what destroys it.

**How to read the diagrams.** Every diagram carries two kinds of annotation:

- 🔒 **sealed** — the payload is written as AES-256-GCM ciphertext (12-byte
  random nonce prefix) into a `*_ciphertext` column. Read the accuracy note in
  [`data-dictionary.md`](./data-dictionary.md) first: today the sealing is done
  with the **master key**, and the per-owner `core.data_keys` row recorded by
  `key_id` is not yet the second layer.
- 📝 **audit** — an `audit.audit_events` row is appended (hash-chained by a DB
  trigger). Payloads are sanitised: counts, bands, ids, flags — never content,
  names, or phone numbers.

Columns not marked are plaintext by design (ids, timestamps, bands, status
codes, hashes) — see the data dictionary for the column-by-column view.

## 1. Diary sync — encrypted, append-only, versioned

```mermaid
sequenceDiagram
  participant APP as Android app (offline)
  participant API as Backend :8000
  participant DB as PostgreSQL
  participant AUD as audit schema
  APP->>APP: create entry locally (client UUIDv7, version 1, idempotency key)
  APP->>API: POST /v1/diary/sync (batch of entries, user JWT)
  loop each entry
    API->>DB: idempotency_key already seen?
    alt seen
      API-->>APP: duplicate (skipped)
    else new or higher version
      API->>DB: INSERT diary.diary_entries (client_id, idempotency_key)
      API->>API: seal_json(owner_type=user, owner_id=user.id)
      API->>DB: INSERT diary_entry_versions (payload_ciphertext SEALED, key_id, version, server_ts)
      API-->>APP: accepted (version)
    else stale version
      API-->>APP: stale_version (server has a newer one)
    end
  end
  API->>AUD: audit diary_synced (entry count, accepted count ONLY)
  APP->>API: GET /v1/diary/entries
  API->>DB: read all versions, decrypt in process, merge
  Note over API: merge = highest version wins PER FIELD,<br/>server timestamp breaks ties (nested symptoms merge recursively)
  API-->>APP: merged view (decrypted, user-only)
```

Why it is shaped this way: entries are **append-only events**; an edit is a new
version row, never an update, so a merge can never destroy data (hazard HZ-09).
The idempotency key makes carrier/app retries safe. The audit event records how
many entries arrived and how many were accepted — never what they contained.

**Derived data.** `compute_features()` decrypts the user's merged diary
in-process and derives the rule inputs (`max_pain_90d`, `avg_bleeding_volume_90d`,
`cyclical_pain_ratio_90d`, `fatigue_ratio_30d`, `cycle_irregularity_90d`, and
the boolean symptom signals) with the 90-day / 30-day windows. A missing input
stays `None` — the engine, not the extractor, applies the safety asymmetry.

**Evaluation.** `POST /v1/rules/evaluate` requires active consent, builds the
engine from `/ontology`, evaluates, and writes `diary.rule_evaluations`
(🔒 sealed: band, indicators, flags, rule-set version). No audit row is written
for routine evaluations — the evaluation row itself is the record.

## 2. USSD assessment — from a borrowed phone to a severity band

```mermaid
sequenceDiagram
  participant U as Feature phone
  participant AT as Africa's Talking
  participant GW as Gateway :8001
  participant ST as Redis (or core.ussd_sessions)
  participant E as Rules engine
  participant DB as PostgreSQL
  participant AUD as audit schema
  loop each callback in the 5-minute session
    U->>AT: dial the shortcode / send input
    AT->>GW: POST /ussd/callback (sessionId, phoneNumber, text)
    GW->>GW: phone_hash = HMAC-SHA256(phone, SISI_PHONE_PEPPER)
    GW->>ST: get session by phone hash
    alt no session
      GW->>ST: PUT session {state: welcome} TTL 300s
      GW-->>AT: welcome / language screen
    else live session
      GW->>GW: idempotent replay check (same state + same input => same output)
      Note over GW: age < 13 => blocked screen, NOTHING stored
      alt final question (q10) answered
        GW->>E: evaluate_assessment(age, features_from_answers)
        E-->>GW: band, indicators, urgent, safeguarding
        GW->>DB: INSERT diary.school_assessments<br/>(answers + band SEALED, owner_type=assessment)
        GW->>AUD: audit school_assessment_completed (channel, consent_state ONLY)
        GW->>AT: SMS summary (generic wording, no condition, no score)
        GW-->>AT: result screen (band + next step)
      else more questions
        GW-->>AT: next question screen (q1..q9, then the age-gated q10)
      end
    end
    AT-->>U: renders the screen / SMS arrives
  end
```

Facts that matter for privacy and safety:

- **The phone number is never stored.** Sessions are keyed by phone hash; the
  assessment row keeps `phone_hash`, `age_band`, `consent_state`, `language`,
  `channel`, and timestamps in plaintext, everything else sealed.
- **Answers are not asked that the channel must not ask.** The USSD/WhatsApp
  flow sets `self_harm_signal` and the cervical signals to `False` explicitly
  (never left missing), because a missing red-flag input would trigger the
  asymmetry and force RED/ORANGE for every subscriber. Those symptoms are
  detected on the app channel, in text conversations, or by a human.
- **The band comes from the engine**, via `evaluate_assessment()` — the same
  deterministic semantics as the diary path without the 14-day gate (CC-1,
  assumption A21).
- **Timeout privacy.** The session lives five minutes; after timeout the user
  restarts at the welcome screen with no residual data shown. `00` exits and
  deletes the session immediately.
- **The SMS carries no result.** Only "your health check results are ready"
  style wording (SPEC §3.5); the detail lives in-session and in the app.

**Downstream of an assessment (school module).** The nurse queue reads
pseudonym + band + age band + consent state + channel; recording an action
writes `school.assessment_actions` (sanitised note) and an audit
`assessment_action` row. Re-identification requires ORANGE/RED or a request for
contact, a typed reason (≥5 chars), and writes `student_reidentified` with the
reason; it is the only path that decrypts `core.student_contact_map`.
`POST /v1/school/guardian-alerts/run` sends **RED-only, generic** alerts, writes
`school.guardian_alerts` (`sent` / `failed` / `skipped_safeguarding`), and skips
the guardian entirely when the payload's `safeguarding` flag is set.

## 3. Corridor consult — the features snapshot, never the diary

```mermaid
sequenceDiagram
  participant P as Patient (user token)
  participant API as Backend :8000
  participant DB as PostgreSQL
  participant AUD as audit schema
  participant N as Nurse / Gynecologist
  P->>API: POST /v1/corridor/consult/requests
  API->>API: require active consent, then compute age
  API->>API: compute_features() over the SEALED diary (in-process decrypt)
  API->>API: engine.evaluate() -> band, urgent, safeguarding, indicators
  API->>API: seal_json(owner_type=corridor, owner_id=request_id)
  API->>DB: INSERT corridor.consult_requests (band PLAIN, features SEALED, note SEALED)
  API->>AUD: audit consult_requested (band, safeguarding ONLY)
  N->>API: GET /v1/corridor/queue
  API-->>N: pseudonym, band, flags, age band, consent state, chaperone
  N->>API: GET /v1/corridor/consults/{id}
  API->>DB: open_json(features snapshot) — the ONLY decryption here
  API->>AUD: audit corridor_case_viewed (band ONLY)
  API-->>N: band, indicators, feature aggregates (trends)
  N->>API: POST review / schedule / consents
  Note over API: minor => guardian_consent + minor_assent required before approval<br/>chaperone requested => chaperone_confirmed before the session starts
  API->>DB: INSERT corridor.consult_events (+ audit consult_reviewed / consult_scheduled)
  N->>API: POST /sessions/{id}/start
  API->>API: sign one-time Jitsi JWT (recording=false, 2h expiry)
  API->>DB: consult_sessions.recorded stays FALSE (DB CHECK)
  API->>AUD: audit consult_started (room ONLY)
```

The corridor is the one place where staff see more than a band — and even there,
**raw diary ciphertext is never opened by any corridor code path** (assumption
A30, non-negotiable 5). The case view is the *computed feature snapshot* sealed
at booking time, plus the band and the indicator names. Every view is audited,
which is what makes "who looked at this minor's case" answerable later.

Telehealth rooms are one-time (random room name per session), JWT-gated, and
cannot be recorded: the database CHECK `recorded IS FALSE` makes a recorded
session impossible to persist, and the room token claims
`features.recording = false`.

## 4. Referral — the patient approves every section

```mermaid
sequenceDiagram
  participant G as Gynecologist
  participant API as Backend :8000
  participant DB as PostgreSQL
  participant AUD as audit schema
  participant P as Patient (user token)
  G->>API: POST /v1/corridor/referrals (from the features snapshot + facility)
  API->>API: build sections: diary_summary, triage_summary,<br/>recommendations, facility_details, personal_details
  API->>API: seal_json(owner_type=corridor, owner_id=referral_id)
  API->>DB: INSERT corridor.referrals (letter SEALED, sections offered, status=awaiting_approval)
  API->>AUD: audit referral_drafted (section keys ONLY)
  P->>API: GET /referrals/{id}/preview
  API-->>P: the FULL letter, decrypted, patient-scoped
  P->>API: POST /referrals/{id}/approve (subset she chooses)
  API->>DB: UPDATE approved_sections, INSERT corridor.sharing_approvals (approved)
  API->>AUD: audit referral_approved (approved section keys ONLY)
  G->>API: POST /referrals/{id}/send
  API->>DB: status=sent, sent_at
  API->>AUD: audit referral_sent
  API-->>G: PDF of APPROVED sections only
  P->>API: POST /referrals/{id}/revoke (any time)
  API->>DB: status=revoked, INSERT sharing_approvals (revoked)
  API->>AUD: audit referral_revoked
```

Two invariants are enforced in code, not by convention: the patient-scoped
routes take the **user** token (a staff role cannot approve on her behalf), and
the PDF endpoint returns `409` unless the referral is `approved` or `sent` and
renders **only** the approved section keys. Revocation is recorded as a
`sharing_approvals` row and an audit event; nothing silently un-shares.

Referral text never asserts a diagnosis — the triage section states the band and
the indicator phrases ("possible endometriosis pattern", "heavy bleeding with
dizziness") plus the standing disclaimer.

## 5. AI ask — the pipeline order is the safety property

```mermaid
flowchart TB
  IN["POST /v1/ai/ask<br/>question, language, age, band, indicators"]
  RF{"1. deterministic red-flag matcher<br/>en / sw / sheng"}
  URG["urgent script + helplines 116 / 1195<br/>model NEVER called"]
  RX{"2. prescription ask?"}
  DX{"2. diagnosis / risk ask?"}
  TOPIC{"3. women's-health topic?"}
  MINOR{"4. minor gate (age < 18 or unknown)"}
  PROC["procedure hard gate<br/>age_gated_minor, no content"]
  SEX["sexual-health two-step:<br/>ask the check question,<br/>then generic text or continue"]
  RETR{"5. retrieval over approved chunks"}
  REF["deterministic refusal text"]
  PROMPT["6. prompt: engine band + indicators + chunk ids ONLY<br/>(schema has no id / phone / name field)"]
  CALL["7. the single model call"]
  POST{"8. post-filter: diagnosis, drug+dose,<br/>band mismatch, prompt leaks, citation"}
  OUT["9. answer + cited chunk ids<br/>(+ deterministic nurse line after the filter)"]
  IN --> RF
  RF -->|hit, or urgent/safeguarding flag| URG
  RF -->|no hit| RX
  RX -->|yes| REF
  RX -->|no| DX
  DX -->|yes| REF
  DX -->|no| TOPIC
  TOPIC -->|off topic| REF
  TOPIC -->|ok| MINOR
  MINOR -->|procedure| PROC
  MINOR -->|sexual health| SEX
  MINOR -->|other| RETR
  RETR -->|no chunks| REF
  RETR -->|chunks| PROMPT
  PROMPT --> CALL
  CALL --> POST
  POST -->|fail| REF
  POST -->|pass| OUT
```

Encryption and audit annotations for this flow:

- 🔒 **Nothing is sealed here because nothing patient-identifying is stored.**
  The AI service persists no conversation content; its request schema
  (`AskRequest`) has no id, phone, name, or email field by construction (A36).
- 📝 The only audit row from this flow is `ai_content_indexed`, written by
  `POST /v1/ai/index` (counts, mode, and model only — never chunk text).
- The retrieval store is `ai.content_chunks` + `ai.chunk_embeddings` (public
  education content, CC-BY 4.0). A **Sheng** question is served from the English
  library (`FALLBACK_LANGUAGE = "en"`).
- `request.urgent` or `request.safeguarding` set by the engine also forces the
  urgent script — the text matcher is not the only trigger.

## 6. Consent, revocation, and erasure

```mermaid
flowchart TB
  AGE{"age check"}
  BLOCKED["under 13: blocked, nothing stored"]
  ADULT["18+: self_grant required"]
  MINOR["13-17: guardian_grant + minor_assent required"]
  GRANT["consent.consent_events row<br/>(who, when, how: digital / sms_link / paper / voice,<br/>which consent_texts version)"]
  AUD1["audit consent_granted"]
  REVOKE["POST /v1/consent/revoke"]
  DEACT["deactivate every active grant + insert revoke event"]
  JOB["diary.erasure_jobs (status=pending, deadline = DSR deadline)"]
  AUD2["audit consent_revoked (grants_deactivated count ONLY)"]
  RUN["POST /v1/dsr/requests/{id}/process (dsr:process)<br/>-> run_erasure()"]
  DEL1["DELETE diary_entry_versions + diary_entries"]
  DEL2["DELETE diary.rule_evaluations"]
  DEL3["DELETE core.data_keys (owner_type=user)"]
  DEL4["DELETE devices, refresh_tokens"]
  DEL5["DELETE consent_events, dsr_requests"]
  REDACT["users row survives as an unlinkable anchor:<br/>phone/DOB/pseudonym NULLed, status=erased"]
  AUD3["audit erasure_completed (counts ONLY)"]
  AGE --> BLOCKED
  AGE --> ADULT
  AGE --> MINOR
  ADULT --> GRANT
  MINOR --> GRANT
  GRANT --> AUD1
  REVOKE --> DEACT
  DEACT --> JOB
  DEACT --> AUD2
  JOB --> RUN
  RUN --> DEL1
  DEL1 --> DEL2
  DEL2 --> DEL3
  DEL3 --> DEL4
  DEL4 --> DEL5
  DEL5 --> REDACT
  REDACT --> AUD3
```

Things a reviewer should notice:

- Consent is **data**, not a checkbox: the row records the grant type, the
  capture method, the staff member who recorded it (nurse-assisted paths), an
  evidence reference, and the version of the consent text shown
  (`consent.consent_texts` with a content hash).
- Minors require **two** grants; a `self_grant` for a minor is refused, and a
  guardian grant for an adult is refused.
- Revocation deactivates grants immediately (processing stops), then schedules
  the erasure job; the job's deadline uses `SISI_DSR_DEADLINE_DAYS` (assumption
  A2, `TO CONFIRM` with counsel). The erasure itself runs through the DSR
  processing endpoint and destroys the ciphertexts, the evaluations, the data
  keys, the auth material, the consent events, and the DSR records — the user
  row survives only as an unlinkable anchor.
- **The audit trail is deliberately retained.** Its rows carry pseudonymous ids
  and sanitised payloads; once the keys and the pseudonym mapping are destroyed
  they identify nobody. That reasoning is documented in assumption A7 and is
  the lawful-basis argument counsel must confirm.

**Retention purge (scheduled, not user-driven).** `.\make.ps1 purge-retention`
(`backend/scripts/purge_retention.py` → `purge_retention_job`) deletes diary
entries and versions whose newest version predates `SISI_RETENTION_DIARY_DAYS`,
their stale rule evaluations, the user's data keys once no diary row or
evaluation remains, and expires lapsed vouchers
(`SISI_RETENTION_VOUCHER_DAYS`). It **never touches `audit.audit_events`**: the
append-only hash chain and an audit retention period are in conflict, so audit
rows are currently retained indefinitely and `SISI_RETENTION_AUDIT_DAYS` has no
automated effect — an open maintainer decision recorded in assumption A3 and
contract note CC-6. The script re-runs the chain verifier after the purge.

## 7. The audit chain itself

```mermaid
sequenceDiagram
  participant SVC as Any service (backend / gateway / AI index)
  participant TRG as audit.chain_insert() (BEFORE INSERT trigger)
  participant T as audit.audit_events (append-only)
  SVC->>SVC: sanitize_payload() first (forbidden keys + 9+ digit runs redacted)
  SVC->>T: INSERT (event_type, actor, resource, payload) — hash columns omitted
  TRG->>TRG: pg_advisory_xact_lock(424242) — serialise
  TRG->>T: read the latest row_hash
  TRG->>T: set prev_hash (genesis anchor 0x00 when empty) and<br/>row_hash = sha256(prev_hash || utf8(jsonb_build_object(...)))
  Note over T: UPDATE and DELETE raise 'audit.audit_events is append-only'
  participant V as verify_chain()
  V->>T: recompute the same digest in SQL + lag() linkage check
  V-->>V: broken_seqs = content edits, genesis change, interior deletions
  Note over V: tail truncation is NOT detected (no re-anchor, no checkpoint)<br/>— keep off-host hashed snapshots
```

Entry points for verification: `.\make.ps1 audit-verify`
(`backend/scripts/verify_audit_chain.py`), `POST /v1/audit/verify`
(`audit:verify`), and the arq job `verify_audit_chain_job`. A break logs an
ERROR and returns the sequence numbers — alert on it; do not "repair" the chain.

## 8. Where each data class stops

| Data class | Reaches | Never reaches |
|---|---|---|
| Diary content | the user's own device and authenticated reads | school staff, corridor staff, the LLM, SMS, logs |
| Computed feature snapshot | corridor staff inside a consult case view (audited) | school staff; anybody outside the corridor |
| Assessment answers + band | the rules engine and the nurse queue (band only) | guardians, SMS, the LLM |
| Student identity | the re-identify endpoint (ORANGE/RED or contact request + typed reason, audited) | the queue, dashboards, exports |
| Guardian contact | the RED-only alert runner and the consent flow | the minor's diary views; any aggregate |
| Aggregates | school / employer / MoH dashboards through the shared k-anonymity module | anything below 5 per cell, or below 20 subjects at all |
| Audit rows | super-admin reads and the verifier | any diary content, name, or phone number (scrubbed at write time) |
