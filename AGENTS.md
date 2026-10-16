# AGENTS.md — SISI Health session protocol

Auto-loaded every session. Full build specification: `/docs/SPEC.md`.
These Sections 1–3 restatements are non-negotiable.

## 1. Non-negotiables

1. The deterministic rules engine assigns every risk band and every condition
   indicator. The LLM never assigns, changes, or contradicts a band — it only
   explains what the rules engine decided. Replacing rules with LLM triage is
   forbidden.
2. No real patient data anywhere in the repo, tests, fixtures, logs, or CI.
   Synthetic only.
3. Every triage rule, red-flag script, and education chunk ships with
   `clinically_validated: false` and empty sign-off fields (`reviewer_name`,
   `reviewer_registration_no`, `signed_at`) until a licensed Kenyan clinician
   signs off. The app must refuse to enable unvalidated rules for real users;
   a build flag allows them only in dev and demo.
4. Nothing condition-identifying ever appears in notifications, SMS, USSD
   screens, app-switcher previews, filenames, or crash reports.
5. Minors' raw symptom data is never visible to staff outside the clinical
   corridor (nurse-reviewed referral, consented gynecologist consult). School
   staff see severity bands and actions only.
6. All timestamps in UTC in storage, Africa/Nairobi in display. All IDs are
   UUIDv7. No auto-increment IDs exposed.
7. Secrets never in the repo. `.env.example` only, with a secrets-scanning step
   in CI.
8. Every phase adds tests before it is declared done. A failing red-flag or
   band test blocks the merge.
9. Anything not specified in the spec and affecting safety, privacy, cost, or
   the database is a question for the maintainer, not a guess.

## 2. Technical decisions (change only after asking the maintainer)

| Area | Decision |
|---|---|
| Database | PostgreSQL 16 with pgvector. Schemas: `core`, `diary` (separately encrypted), `audit` (append-only), `school`, `corridor`, `ai`. |
| Migrations | Alembic, forward-only, every migration reviewed with a rollback note. |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Ruff, mypy strict on the rules and consent packages. |
| Jobs/queue | Redis + arq workers (sync, SMS, PDF, reconciliation). |
| Auth (users) | Phone-number OTP via SMS, short-lived JWT + rotating refresh tokens, device binding. |
| Auth (staff) | Email + password + mandatory TOTP, RBAC on every endpoint, 15-minute idle timeout. |
| Key management | Envelope encryption: per-record data keys wrapped by a master key behind a `KeyProvider` interface (dev: local file; pilot: self-hosted Vault or cloud KMS). Key rotation procedure documented. |
| Audit trail | Hash-chained append-only table. Each row stores the hash of the previous row. A nightly job verifies the chain and alerts on a break. |
| Mobile | Kotlin, Compose, Room + SQLCipher, Hilt, WorkManager, Retrofit. Android Keystore for keys. Release builds set FLAG_SECURE and hide the app-switcher preview. |
| Offline sync | Client-generated UUIDv7 per diary entry. Entries are append-only events; edits create a new version. Conflict rule: highest version wins per field, server timestamp breaks ties. Every sync call carries an idempotency key. Property-based tests for sync merge. |
| Web | React + TypeScript, Vite, TanStack Query, Playwright e2e. |
| USSD/SMS | Africa's Talking (sandbox first). Session state in Redis with a 5-minute resume window keyed by phone hash. |
| WhatsApp | Turn.io or WhatsApp Business API behind a `MessagingProvider` interface. |
| Telehealth | Self-hosted Jitsi with JWT-gated rooms. No recording by default. |
| Embeddings/RAG | Multilingual embedding model (bge-m3 or multilingual-e5) into pgvector. Answers must cite chunk IDs or are refused. |
| LLM | `LLMProvider` interface. Pilot: hosted API with strict system prompt and no patient identifiers in prompts. Open-weight path (Llama 3.x or Qwen served by vLLM on a separate GPU host) implemented and eval-compared before pilot. |
| Deploy | Docker Compose on one VPS, Caddy for TLS 1.3, separate staging and prod stacks, nightly encrypted backups with a tested restore. |
| Observability | Structured JSON logs with PII scrubbing, OpenTelemetry, Prometheus + Grafana. Logs never contain diary content, phone numbers, or names. |
| Open-source | MIT for code, CC-BY 4.0 for `/ontology` and content. |

## 3. Design decisions that resolve spec conflicts

**3.1 Nurse re-identification.** School nurses see anonymized IDs by default. A
nurse may re-identify a student only when (a) the student's band is ORANGE or
RED, or (b) the student asked to be contacted. Re-identification requires a
typed reason and writes an audit entry. The pseudonym-to-person mapping lives
in an encrypted table that only the re-identify endpoint can read. The privacy
notice shown at assessment tells the student a nurse may contact her if her
result needs follow-up.

**3.2 Minors, discreet features, guardians.**
- Users under 13 are blocked at the age check.
- Discreet name/icon, decoy mode, and quick-exit are available to all users
  including minors. They are never disabled by a guardian.
- Guardians never read a minor's diary or assessment answers.
- Consent for 13–17: guardian consent plus the minor's own assent, both
  recorded. Counsel must confirm whether any age within 13–17 may self-consent
  to health services; that threshold is a config value, not hard-coded.

**3.3 Guardian alerts and safeguarding override.**
- Guardians are alerted only for RED-band events. The message is generic
  ("Please contact the school nurse or take her to a clinic soon") with no
  symptoms or condition names.
- Safeguarding override: if any input suggests abuse, sexual violence,
  pregnancy concerns in a minor, self-harm, or that the guardian may be the
  source of risk, the system does not alert the guardian. It routes to the
  designated safeguarding lead, shows the child helpline 116 and the GBV
  helpline 1195, and logs the escalation. Verify all hotline numbers before
  launch and keep them in config.
- Red-flag text (severe acute pain, heavy bleeding with dizziness, self-harm)
  always shows the urgent-care script first, regardless of any other state.

**3.4 k-anonymity at small scale.**
- Any cell with fewer than 5 is suppressed, with complementary suppression so
  subtraction cannot reveal it.
- A school reports nothing until at least 20 students have completed
  assessments in the term.
- Below threshold the dashboard shows "Not enough data yet", never a zero.
- Enforcement lives in one shared query module with property-based tests
  against differencing attacks.

**3.5 Channel limits.** SMS and USSD run over unencrypted carrier networks.
Therefore: no names, no conditions, no scores in them. SMS summaries say only
"Your health check results are ready. Visit your school nurse or open the
app." Detailed guidance is delivered in-session and never stored in SMS
history.
