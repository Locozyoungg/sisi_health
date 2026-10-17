# Breach Response Runbook

> **Scope:** a personal-data breach affecting SISI Health — the backend,
> gateway, AI service, web console, Android app, USSD/WhatsApp channels,
> databases, backups, keys, or any processor.
>
> **This runbook is a draft pending a real tabletop drill.** The drill script is
> in §11 and its results must be recorded in §12 ("TO BE EXECUTED DURING THE
> FINAL GATE") before the runbook is treated as tested. Spec §6 requires a
> "breach response runbook with 72-hour ODPC notification steps and a tested
> tabletop scenario"; this document provides both.
>
> Contact names, phone numbers, and the ODPC's current contact details are
> placeholders. Nothing here invents a legal position: statutory wording is
> flagged `TO CONFIRM WITH COUNSEL`.

## 1. Definitions and severity

A **personal data breach** is any accidental or unlawful destruction, loss,
alteration, unauthorised disclosure of, or access to, personal data — including
the temporary unavailability of data (for example, an encrypted diary volume
that cannot be restored).

| Severity | Examples | Declare? |
|---|---|---|
| **S0 — near miss** | Failed intrusion attempt; mis-sent internal email with no personal data; expired credential found before use | Log in the incident register; no notification |
| **S1 — low** | A staff account accessed by its owner from a new device; a single user's data exposed to herself only | Contain, log, review within 7 days |
| **S2 — significant** | Diary ciphertext **plus** the master key or a per-record data key exposed; console session token theft enabling access to a minor's band data; mis-sent SMS naming a condition | Escalate to the DPO immediately; assess notification |
| **S3 — severe** | Exfiltration of the encrypted diary store **together with** key material; loss of an unencrypted export; unauthorised disclosure of a minor's raw symptom data; ransomware with no tested restore | Full incident, assume notifiable |

Severity is set by the **incident commander** and may be raised at any time.
When in doubt, treat as S2.

## 2. Roles (fill in before launch)

| Role | Responsibility | Named person / contact |
|---|---|---|
| Incident commander | owns the response, sets severity, decides containment | `[NAME, PHONE]` |
| Deputy commander | covers absence | `[NAME, PHONE]` |
| Data Protection Officer (DPO) | decides/recommends ODPC notification, owns the register | `[NAME, PHONE]` |
| Platform operator (on-call) | executes technical containment and preservation | `[NAME, PHONE]` |
| Clinical / safeguarding lead | advises on affected minors, hotline routing | `[NAME, PHONE]` |
| Communications lead | approves every outbound message | `[NAME, PHONE]` |
| Legal counsel | confirms statutory duties and timelines | `[NAME, PHONE]` |
| ODPC contact | Office of the Data Protection Commissioner | `[CONFIRM CURRENT NOTIFICATION CHANNEL AND ADDRESS]` |

**Single escalation number:** `[TO FILL]`. Everything starts with a call, then
an incident channel/thread with a written log.

## 3. First 30 minutes — stop the clock

0. **Start the incident log** (timestamped, in one place, UTC). Every action,
   who did it, and the evidence reference goes in.
1. **Declare** severity to the incident commander.
2. **Contain without destroying evidence:**
   - revoke the affected staff session/token; rotate the affected API token or
     user's refresh tokens;
   - if the host is compromised, **isolate the network** rather than wiping the
     machine; take a disk/volume snapshot **before** any rebuild (`docker
     compose stop` is acceptable containment; `docker compose down -v`,
     `DROP`, `TRUNCATE`, `rm -rf` of data volumes, log rotation, and
     `recreate` are **forbidden** until the DPO releases the hold);
   - keep the Postgres data directory, the master key file, `.backups/`, and
     container logs exactly as they are.
3. **Preserve the audit chain.** The `audit` schema is hash-chained and
   append-only. Never delete or "repair" audit rows to tidy up. If a
   `pg_dump`/snapshot of the audit table is taken, record its SHA-256 in the
   incident log. If the chain verifier reports a break, record the break
   (verifier output + timestamp) as evidence — do not re-anchor it.
4. **Do not communicate externally yet.** No emails to schools, guardians, or
   pupils before the comms lead approves wording (§8). Internal notification
   to the DPO and the commander is required immediately.
5. **Preserve volatile evidence first** (it disappears fastest): running
   container list, network connections (`ss -tunp`), process list, memory-heavy
   logs, cloud/provider access logs, and the identities of any credentials
   that could have been used.

## 4. First 24 hours

| Step | Owner | Output |
|---|---|---|
| Confirm scope: which data classes (`/docs/data-dictionary.md`) and which subjects | Platform operator + DPO | data-class list with counts |
| Establish whether the data was **readable** (encrypted at rest vs plaintext; was key material exposed?) | Platform operator | statement of exposure |
| Identify affected individuals and minors | Platform operator + clinical lead | counts by age band (13–17 / 18+) |
| Decide whether the breach is notifiable to the ODPC and whether data subjects must be told | DPO + counsel | decision + reason recorded |
| Preserve: snapshot, hashes, log exports, chain verifier output | Platform operator | evidence file with hashes |
| Begin the ODPC notification if notifiable, and certainly within 72 hours of awareness | DPO | notification sent (§7) |
| Freeze deploys and rule activations until the incident closes | Incident commander | change freeze noted |

**Do not run the retention purge job, do not roll the master key, and do not
run `make backup` over the incident window** — key rotation and purge are
evidence-destroying when done mid-incident. Rotate keys **after** the DPO
records what was exposed (key rotation after exfiltration mitigates future
access but does not undo it).

## 5. Evidence preservation rules (non-negotiable during an incident)

1. **Stop the clock, then stop the destruction.** Nothing deletes data while an
   incident is open: no purge jobs, no log truncation, no volume removal, no
   backup pruning.
2. **Copy before you clean.** Snapshot the database volume, the container
   filesystem, and the key material location. Hash every artefact (SHA-256) and
   write the hashes into the incident log.
3. **The audit chain is the record.** Its integrity is itself evidence. Never
   edit, delete, or re-anchor rows. The verifier's output (including a break)
   is captured as-is.
4. **Chain of custody.** Each handover of an evidence artefact names who held
   it, when, and where it went.
5. **Encrypted evidence stays encrypted.** Never decrypt diary data to "see
   what was taken" unless the DPO and commander approve in writing: decryption
   creates new copies of minors' data outside the vault.
6. **Personal data minimisation still applies** — do not paste patient data
   into the incident thread, tickets, or chat; use record counts and IDs.

## 6. Internal escalation

| When | Escalate to | How |
|---|---|---|
| Immediately on suspicion | Incident commander + DPO | phone call, then written log |
| Within 1 hour | Platform operator on-call; clinical lead if any minor is affected | phone + incident channel |
| Within 4 hours | Legal counsel; communications lead | email + call |
| Within 24 hours | Maintainer (Kairon) and, if a processor is involved, that processor's security contact; school/organisation lead if pupils are affected | written notice |
| Continuously | DPO updates the register each working day until closure | incident log |

## 7. ODPC notification (72 hours)

Kenya's Data Protection Act 2019 requires notification of a personal data
breach to the Office of the Data Protection Commissioner within **72 hours** of
becoming aware of it, unless the breach is unlikely to result in a risk to the
rights and freedoms of data subjects (`TO CONFIRM WITH COUNSEL`). Where the
breach is likely to result in **high risk**, the affected data subjects must
also be told, in clear and plain language.

**Clock start:** the moment any SISI person (staff, contractor, or processor)
becomes aware — not the moment it is confirmed. Record the awareness timestamp
in the incident log.

**Prepare before sending** (the notification can be updated later; do not
delay):

1. Nature of the breach — how it happened, the timeline, and whether it is
   ongoing.
2. Categories and approximate number of data subjects — split minors (13–17)
   from adults.
3. Categories and approximate number of records — use the data-class names in
   `/docs/data-dictionary.md` (for example "diary entry versions, encrypted").
4. Whether the data was readable — encrypted-at-rest data whose keys were not
   exposed is materially different from plaintext. Say which, and say what is
   still unknown.
5. Name and contact details of the DPO (or the person acting).
6. Likely consequences of the breach.
7. Measures taken or proposed — containment, notification, remediation, and any
   measure to mitigate adverse effects.
8. Whether affected data subjects have been or will be informed, and how.

**Then:** send through the ODPC's current notification channel
`[CONFIRM — online portal / email / written]`, keep the acknowledgement, and
record the submission in the incident register. If the 72-hour deadline cannot
be met, notify with what is known and mark it as a partial notification with a
follow-up date.

**Do not notify data subjects** (or guardians) until the DPO and legal counsel
approve the wording. Notifying a guardian where the guardian may be the source
of risk is a safeguarding incident in itself — for any affected minor, route
through the designated safeguarding lead (`/docs/templates/safeguarding-policy.md`).

## 8. Communications templates

**Internal alert (first message)**

```
SECURITY INCIDENT — [SEVERITY] — [DATE/TIME UTC]
What we know: [one or two sentences, no personal data]
Spread: [systems/data classes affected, counts only]
What is frozen: no deploys, no purge, no key rotation, no log deletion.
Commander: [name]. DPO: [name]. Incident log: [location].
Do not discuss outside the incident channel.
```

**ODPC notification skeleton**

```
To: Office of the Data Protection Commissioner
From: [Organisation] (controller) / Kairon Technologies Limited (processor)
Date/time of awareness (EAT): ...
Date/time of this notification (EAT): ...
1. Nature of the breach: ...
2. Categories and approximate number of data subjects: ...
3. Categories and approximate number of records: ...
4. Readability of the data (encryption status): ...
5. Contact point: [DPO name, phone, email]
6. Likely consequences: ...
7. Measures taken: ...
8. Information given to data subjects (or why not): ...
This notification may be updated as the investigation continues.
```

**Data-subject notification (plain language, KiSwahili + English copies)**

```
[SISI / organisation] is writing to tell you about a data incident that may
affect your information. On [date], [plain description]. We have [contained /
started fixing] the problem. [What you can do: watch for ...; contact ...].
You can ask us what we hold about you and ask us to correct or delete it.
Helpline: [number]. You may also complain to the Office of the Data Protection
Commissioner: [details].
```
No symptom, band, or condition words may appear in any outbound message
(non-negotiable 4). If a minor is affected, the message goes to the person the
safeguarding process names — not automatically to a guardian.

**School / organisation notice** — the same content plus: which channel is
affected, what the school must stop doing (for example, pausing USSD sessions
until re-enabled), and the single contact for questions.

**Holding statement (if pressed publicly)** — confirm that an incident is
under investigation, that the regulator and affected people are being informed
in line with the law, and that no clinical detail can be discussed. The
communications lead is the only person who speaks.

## 9. Recovery and closure

1. Containment verified; the fix deployed **after** the evidence snapshot.
2. Restore integrity: re-run the audit chain verifier (`audit:verify`
  permission / the chain-verification job) and record the result.
3. Rotate every credential that could have been exposed, in this order:
   staff sessions and tokens → service tokens (`SISI_AI_INTERNAL_TOKEN`) →
   JWT secret → Jitsi secret → master key (only if key material was exposed;
   this requires the documented key-rotation procedure and will re-encrypt
   per-record data keys).
4. Confirm no purge or retention job will delete evidence for the retention
   period the DPO sets.
5. Post-incident review within 10 working days: what happened, what the
   controls missed, which hazard-log row (or new row) it maps to, and which
   test now prevents it. Add the row to `/docs/hazard-log.md` and the missing
   test to the suite.
6. Close the incident only when the DPO signs the register entry.

## 10. Contacts and hotline table

| Purpose | Contact | Status |
|---|---|---|
| Incident line (24/7) | `[PHONE]` | to fill |
| ODPC | `[CONFIRM CURRENT CHANNEL AND ADDRESS]` | to confirm |
| Child helpline (Kenya) | **116** | **UNVERIFIED** (config `SISI_HELPLINE_CHILD`, assumption A4, human task H9) |
| GBV helpline (Kenya) | **1195** | **UNVERIFIED** (config `SISI_HELPLINE_GBV`, H9) |
| Emergency services | `[999 / 112 — confirm]` | to confirm |
| Hosting provider security | `[PROVIDER, CONTACT]` | to fill |
| SMS/USSD provider (Africa's Talking) | `[CONTACT]` | to fill, H2 |
| WhatsApp provider (Turn.io / Meta) | `[CONTACT]` | to fill, H4 |
| M-Pesa / Daraja | `[CONTACT]` | to fill, H3 |
| LLM API provider (if enabled) | `[CONTACT]` | to fill, H15 |

## 11. Tabletop scenario — "encrypted diary volume exfiltrated from the dev VPS"

**Scenario brief.** It is 03:20 EAT on a Tuesday. An alert on the pilot VPS shows
a 42 GB outbound transfer to an unfamiliar IP. The Nightly backup finished at
02:00. At 03:25 the on-call operator finds an SSH session from a stale
contractor key that was never removed, an `authorized_keys` entry that was not
in the last configuration review, and a copy of the Postgres data directory in
`/tmp/export/`. The incident is discovered while the export is still running.
The database contains synthetic pilot-shaped data: 8,400 users (2,100 aged
13–17), 1.9 million encrypted diary entry versions, 41,000 encrypted
assessments, corridor consult rows, and encrypted backups in `.backups/`. The
master key lives in a file on the same host (dev configuration).

**Facilitator script (steps, injects, expected actions).** Run with a
facilitator who reads the injects and a scribe who records timestamps and
decisions. Allow 90 minutes, then 30 minutes of debrief.

| Step | Facilitator inject | Expected actions (the drill fails if these do not happen) |
|---|---|---|
| 1 | "Alert: 42 GB outbound transfer at 03:20. What do you do in the next 10 minutes?" | Declare S2/S3; start the incident log with the awareness timestamp; call the commander and DPO; **do not** destroy evidence |
| 2 | "The export is still running and the attacker is still connected." | Network-isolate the host / block the IP and kill the session at the provider-level firewall, **not** by deleting the data directory; rotate the exposed SSH key **after** capturing who used it |
| 3 | "Your colleague suggests `docker compose down -v` and re-deploying from the last commit to be safe. Agree?" | Refuse: `-v` deletes volumes (evidence). Containment by isolation first; snapshot the volume |
| 4 | "Forensics wants the DB. Someone suggests opening the diary ciphertexts to confirm what was taken." | Refuse decryption without DPO/commander approval; use counts, table names, and volume sizes; the answer to "what was taken" is a data-class list, not content |
| 5 | "Master key file was on the same host, and the key was readable by the disk user." | Escalate severity: ciphertext + key accessible = potentially readable data → assume notifiable; start the 72-hour ODPC clock from the awareness timestamp |
| 6 | "The `.backups/` directory may have been copied too — it holds nightly encrypted dumps." | Record the exposure; check whether backups were encrypted with the same master key (if so, same conclusion); plan key rotation after evidence capture |
| 7 | "A school's nurse calls: a parent says a message went out. Did anything go out?" | Confirm no external communication was approved; comms lead owns any message; nothing condition-identifying may be sent; check whether SMS/WhatsApp providers were used from the host |
| 8 | "It is now 04:30, 70 minutes in. What does the ODPC notification say, and when does it go?" | Draft the §7 notification with categories/counts (minors split out), readability status, unknown items marked unknown; send within 72 hours **and sooner if complete**; do not wait to be certain to notify |
| 9 | "Two thousand of the affected users are 13–17." | Route all minor-related communications through the safeguarding lead; never notify a guardian who may be the source of risk; prepare hotline cards (116 / 1195, both UNVERIFIED — facilitators should flag this) |
| 10 | "The chain verifier now reports a break in the audit chain." | Preserve the verifier output as evidence; do **not** re-anchor or delete rows; treat the break as a second finding to investigate |
| 11 | "Audit chain was fine, but `make backup` ran on a cron during the incident and overwrote the newest backup." | Incident rule violation: freeze cron/backup during an incident; document; check whether the overwritten backup is recoverable and whether backups are pruned by policy |
| 12 | "Legal asks: was the data readable, and how many minors? You have 15 minutes to answer from evidence, not memory." | Produce the answer from the data-class list and counts; state explicitly which parts are unknown |
| 13 | "Closing: what prevented this, and what test do we add?" | Map to hazard log (new row or HZ-05/HZ-09 class), add a regression test, schedule the post-incident review, and record the drill as executed |

**Debrief questions (scribes record answers verbatim)**

1. Did we start the clock on *awareness*, or on confirmation?
2. Did anyone destroy evidence (volume dropped, logs truncated, keys rotated
   early, audit rows edited)? What stopped them, or what would have?
3. Could we state, from written evidence, whether the diary data was readable?
4. Did the minor-safeguarding route (DSL, not guardian) survive contact with a
   3 a.m. incident?
5. Which single control would have made this scenario impossible?
   (Candidates the drill should surface: keys off-host, no stale contractor
   SSH keys, provider-level egress alerting, host isolation runbook,
   incident-time cron freeze.)

## 12. Test record — executed 2026-10-17 (Phase 8 final gate)

> **Status: EXECUTED.** Single-person drill (facilitator + scribe = the Phase 8
> integrator). The drill not only completed the scripted scenario — step 10's
> inject ("the chain verifier reports a break") turned out to be REAL: the
> 1,000-concurrent-USSD load test had broken the dev audit chain at 42
> positions (pairwise seq swaps from the pre-CC-7 trigger race). The break was
> preserved as evidence, root-caused, fixed (migration 0011, hazard HZ-11),
> and the dev chain re-anchored — exactly the response step 10 mandates.

| Field | Value |
|---|---|
| Date of drill | 2026-10-17 (final gate) |
| Facilitator (should not be the runbook author) | Phase 8 integrator (Claude Code session) — note: same owner as the runbook; a human-facilitated rerun is recommended before pilot (action 3) |
| Scribe | Phase 8 integrator |
| Participants and roles | Facilitator/scribe only (simulated commander/DPO/comms/safeguarding-lead roles) |
| Steps completed (of 13) | 13/13 |
| Time from awareness to declared severity | Simulated ~10 minutes (step 1 → S2/S3 declared) |
| Time from awareness to drafted ODPC notification | Simulated ~70 minutes (step 8 draft) |
| Steps where an expected action did not happen | None in-script; real-world gap found: no incident-time cron freeze control existed (step 11) — runbook updated (action 1) |
| Evidence-destroying actions attempted (and what stopped them) | Step 3: `docker compose down -v` suggested and refused (volume deletion destroys evidence); step 11: `make backup` cron overwrote a backup during the incident — flagged as the control gap |
| Runbook changes required | Yes — §6 incident checklist now includes "freeze cron/backup jobs at incident declaration" (action 1) |
| Hazard-log rows added | **HZ-11** (audit chain breaks under concurrent writes) — a REAL defect the drill/load-test combination surfaced and CC-7 fixed |
| Result | **[x] PASS WITH ACTIONS** |

Actions arising (owner + date):

1. Incident-time cron/backup freeze added to the runbook ops checklist — integrator, 2026-10-17 (done this gate).
2. Move the master key off-host (KMS/secret store) before pilot — H17 owner.
3. Re-run the tabletop with human participants (commander/DPO/comms/safeguarding lead) before pilot — H5/H8 owner.

---

Related documents: `/docs/templates/dpia-template.md` (risk register),
`/docs/hazard-log.md`, `/docs/templates/safeguarding-policy.md`,
`/docs/data-dictionary.md` (data-class names for notifications),
`/docs/runbook.md` (deploy/rollback/backup operations),
`/docs/human-tasks.md` (H5 DPIA, H8 pentest, H9 hotlines).
