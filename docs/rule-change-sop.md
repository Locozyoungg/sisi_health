# Rule-Change SOP

How a triage rule, red-flag pattern, or threshold is changed in SISI Health —
from draft to activation to rollback. **The deterministic rules engine assigns
every band; nothing in this process may move band assignment to a model**
(non-negotiable 1).

**Scope.** Every change under `/ontology/rules/*.json`, `/ontology/redflags/*.json`,
`/ontology/golden/cases.json`, and the rule engine code on either side
(`backend/app/rules/`, `mobile/…/engine/`) — because the two engines must stay
identical on the same JSON. A content-only change (`/ontology/content/*.json`)
follows §7.

**Rule of thumb:** if the change can alter a band, an indicator, `urgent`, or
`safeguarding` for any input, it is a safety change and this SOP applies in
full — including the two-person activation and the golden-suite gate.

**Roles.**

| Role | Who | Responsibility |
|---|---|---|
| Author | engineer or clinician | drafts the change, cites evidence, runs the suite |
| Clinician approver | licensed Kenyan clinician (**H7**) | signs the clinical content; must differ from the author |
| Activator | `rules:activate` holder (GYNECOLOGIST, per `/docs/role-matrix.md`) | runs register → request → approve |
| Release owner | maintainer | decides when a rollback is needed |

## 1. Draft

1. Edit the rule JSON in `/ontology/rules/<rule_id>.json`:
   - bump `version` (`MAJOR.MINOR.PATCH` — the activation API enforces the
     `^[0-9]+\.[0-9]+\.[0-9]+$` shape);
   - add a `changelog` entry saying **what changed and why**;
   - cite the source of every new or changed threshold in `evidence[]`;
   - keep `clinically_validated: false` and leave `reviewer_name`,
     `reviewer_registration_no`, `signed_at` **empty** until §3.
2. Stay inside the constrained DSL (assumption A12: `and`/`or`/`not` over
   `gte`/`gt`/`lte`/`lt`/`eq`/`neq`/`between`/`in`). A construct the Kotlin
   engine cannot evaluate is not portable and is rejected.
3. Add or update golden cases in `/ontology/golden/cases.json`:
   - at least one case that **distinguishes** the new behaviour from the old
     (otherwise the change is untested);
   - boundary cases at every threshold;
   - a case asserting the safety asymmetry still holds (no input combination
     lowers a band when a red flag is present).
4. Run the suite locally (`.\make.ps1 test` for the backend; the Android parity
   suite for the Kotlin side — `.\make.ps1 android-test`). A failing red-flag or
   band test **blocks** the change (non-negotiable 8).
5. Never present a draft as validated. Text in the UI or content that says
   otherwise is a defect.

**Checkpoint gate:** `RULE_SET_VERSION` (in `backend/app/rules/loader.py` and
its Kotlin twin) and the golden file version bump together whenever semantics
change, so an evaluation row can always be traced to the rule set that produced
it.

## 2. Evidence and review packet

1. Regenerate the clinician review packet:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe scripts\export_review_packet.py
   ```

   It rewrites `docs/clinician-review-packet.md` with every rule, its evidence,
   its logic, its test cases, and signature lines.
2. Send the changed rules (or the whole packet) to the clinician approver.
   Include the golden cases that demonstrate the new behaviour — reviewers sign
   the *content*, not the code.

## 3. Clinician sign-off

The clinician completes, **in the rule JSON**:

```json
{
  "clinically_validated": true,
  "reviewer_name": "<full name>",
  "reviewer_registration_no": "<KMPDC registration>",
  "signed_at": "<ISO-8601 UTC timestamp>"
}
```

Facts that matter:

- The engine refuses to run **any** unvalidated rule unless
  `SISI_ALLOW_UNVALIDATED_RULES=true`, which staging/prod refuse to boot with
  (`backend/app/config.py` prod guards). So a rule that is not signed off is
  literally unusable outside dev/demo.
- The activation gate (`_run_golden_check` in `backend/app/rules/service.py`)
  runs the golden suite with the candidate payload regardless of validation
  status; sign-off is a **separate** gate. Both must pass.
- The signature is clinical authorship of a threshold. If the clinician
  proposes a different threshold, they edit the JSON (or ask the author to) and
  the file is re-reviewed — no verbal sign-off is recorded as data.

## 4. Register the version

The activation API reads the rule **from `/ontology`** and stores a copy with a
content hash (`register_rule_version`, `rules.rule_versions`).

```
POST /v1/rules/registrations        { "rule_id": "<id>", "version": "1.2.0" }   # rules:activate
GET  /v1/rules                       → list versions with status + content_hash  # rules:read
GET  /v1/rules/{rule_id}/versions/{version}  → the payload copy                  # rules:read
```

Outcome: a `draft` row whose `content_hash` is the fingerprint of exactly what
was reviewed. If the file changes afterwards, a new registration is required —
the hash will differ, and the old row stays as the record of what was approved.

## 5. Two-person activation

```
POST /v1/rules/activations                 { "rule_id": "...", "version": "..." }   # step 1 (author)
POST /v1/rules/activations/{id}/approve                                              # step 2 (approver)
```

What the code enforces (`backend/app/rules/service.py`):

| Rule | Enforcement |
|---|---|
| Author ≠ approver | `approve_activation` raises `Conflict("two-person approval: approver must differ from author")` |
| One active version per rule | a partial unique index (`rules.rule_versions` WHERE `status='active'`); the previous active version is set to `rolled_back` and flushed **before** the new one is activated |
| Golden suite must pass with the candidate | `_run_golden_check` loads `/ontology/golden/cases.json`, swaps in the candidate payload, and raises `PreconditionFailed` listing every failing case id — activation is blocked |
| Every transition is audited | `rule_activation_requested`, `rule_activated` (with `rolled_back: <previous version>`), `rule_rolled_back` |
| Re-activating an already-active version | `Conflict("rule version already active")` |

The gate is intentionally run **in-process** here and again in CI, so a broken
rule cannot be activated by hand-editing the DB either.

## 6. Rollback

```
POST /v1/rules/rollback   { "rule_id": "...", "version": "<the active one>" }   # rules:activate
```

`rollback_rule` marks the active version `rolled_back`, then restores the most
recently activated other version (never the row just rolled back) and audits
both. Rollback is instant and needs no golden run — it restores a version that
was already gated.

**When to roll back immediately:** any of the following, without waiting for a
root-cause analysis —
- a red flag stops firing on a case it previously caught;
- a band is produced that contradicts a signed-off expectation;
- an activation is discovered that skipped the two-person step or the gate;
- hazard-log HZ-08 (rule-version error) is suspected.

**After a rollback:** open a hazard-log entry (new row or HZ-08), add the
regression case to the golden file, and only then re-enter the SOP.

## 7. Content and pattern changes (lighter path, same gates)

| Artefact | Path | Extra gate |
|---|---|---|
| Red-flag text patterns (en/sw/sheng) | `/ontology/redflags/*.json` | every pattern must have a matching test case; `backend/tests/test_redflag_patterns.py` must pass; the AI service guardrail eval (`.\make.ps1 ai-eval`, 170 cases) must stay green; patterns must never introduce condition names into channel-facing text |
| Education content | `/ontology/content/*.json` | clinician review of the text; content ships `clinically_validated: false` until signed (H16); every screening message keeps the "a normal symptom check does not replace screening" sentence |
| Guardrail cases | `/ontology/guardrail/*.json` | `scripts/eval_guardrails.py --ci` must pass at 100% red-flag routing |
| Rule *engine* code | `backend/app/rules/`, `mobile/…/engine/` | both engines must produce identical results on the whole golden file |

## 8. Verification commands

| What | Command |
|---|---|
| Backend suite (rules, red flags, bands, activation, rollback) | `.\make.ps1 test` |
| Coverage report with the 70% floor | `.\make.ps1 coverage` |
| Android engine parity (same JSON, Kotlin) | `.\make.ps1 android-test` |
| AI guardrail eval (170 cases, 100% red-flag routing) | `.\make.ps1 ai-eval` |
| Audit chain intact after the change | `.\make.ps1 audit-verify` |
| Review packet regenerated | `cd backend; .\.venv\Scripts\python.exe scripts\export_review_packet.py` |

## 9. Record of the change (fill in per change)

| Field | Value |
|---|---|
| Change id / ticket | |
| Rule id + from → to version | |
| Author (name) | |
| Clinician approver (name + KMPDC no.) | |
| Evidence cited (guideline / study) | |
| Golden cases added | |
| Activation id | |
| Activated at (UTC) | |
| Previous version rolled back | |
| Rollback exercised? when / why | |
| Hazard-log row (if any) | |
