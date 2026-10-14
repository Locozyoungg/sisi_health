# Assumptions

Every assumption that affects safety, privacy, cost, or the database is
recorded here before it is coded. Each entry: date, phase, decision made,
reason, and who must confirm it.

## Phase 1 (2026-10-14)

| # | Assumption | Reason | To confirm |
|---|---|---|---|
| A1 | Self-consent age threshold defaults to **18** (guardian consent + minor assent required for all users under 18). Config: `SISI_SELF_CONSENT_AGE`. | We never invent Kenyan law. The spec requires a config value, not a hard-coded one; 18 is the most conservative lawful default until counsel confirms any younger threshold. | Legal counsel (human task H6). |
| A2 | Data-subject-rights request deadline defaults to **30 days**. Config: `SISI_DSR_DEADLINE_DAYS`. | Kenya DPA 2019 requires responses within a legally defined window; we default to a conservative placeholder rather than asserting the statute. | Legal counsel (H6). |
| A3 | Retention defaults (placeholders): diary/assessments 7 years, audit 10 years, vouchers 2 years. All config-driven; purge job is a Phase 1 stub executed by `make audit-verify`-style targets until arq workers are fully wired (Phase 3+). | Spec demands a stated retention schedule with automated purge; periods themselves are legal decisions. | Legal counsel (H6). |
| A4 | Hotline numbers 116 (child helpline) and 1195 (GBV) are carried in config marked **UNVERIFIED**. Nothing ships hard-coded. | Spec: "Verify all hotline numbers before launch and keep them in config." | Maintainer / H9 (hotline verification). |
| A5 | Dev/demo OTP delivery: the OTP is returned in the API response (`dev_otp` field) only when `SISI_OTP_DEV_RETURN=true`; `staging`/`prod` refuse to boot with it enabled. No SMS credentials exist yet (Africa's Talking sandbox is human task H2). | Keeps auth e2e-testable without inventing credentials. | Maintainer at H2 completion. |
| A6 | OTP store is Postgres-backed in Phase 1 (`core.otp_requests`). Redis-backed session state arrives with the USSD phase (spec reserves Redis for USSD sessions; OTP storage was unspecified, so it is a recorded choice, not a spec change). | Runs without Redis locally; Redis stays optional for Phase 1. | Maintainer. |
| A7 | Erasure deletes diary ciphertexts, evaluations, per-user data keys, PII fields, devices, refresh tokens, consent events, and DSR requests. The audit chain is retained: audit rows carry only pseudonymous UUIDs and sanitized payloads, and after erasure the UUID→person mapping is destroyed, so remaining rows identify nobody. This design is documented as lawful-basis reasoning. | Spec: "Erasure keeps only the audit-trail hash with no personal content, and the design documents why that is lawful." | Legal counsel (H6). |
| A8 | `pgvector` extension is installed in the Phase 6 migration (when RAG lands), not Phase 1. | Spec names pgvector as the DB decision but embedding/vector work is Phase 6; installing unused extensions now would be speculative. | Maintainer. |
| A9 | Severity bands are `GREEN` self-care, `YELLOW` see a nurse, `ORANGE` see a doctor soon, `RED` urgent (colors named in spec §3.1/§3.3; labels named in §5.1). `NOT_ENOUGH_DATA` is a non-band result for <14 diary days. | Spec names the labels but not the color mapping; ORANGE/RED are the only colors the spec uses, so the mapping is forced. | Maintainer. |
| A10 | All Phase 1 rule thresholds are **drafts** from published guidance, cited in each rule's `evidence` field, and are `clinically_validated: false` until a Kenyan clinician signs off (H7). The engine refuses to serve them to real users unless `SISI_ALLOW_UNVALIDATED_RULES=true` (dev/demo only). | Spec §7 sanctions drafting from published guidance with citations; we never present drafts as validated. | Kenyan clinician (H7). |
| A11 | Rule payloads in `/ontology` are the canonical source of truth; the DB stores copies + approval/activation state keyed by content hash. | One source of truth guarantees on-device (Kotlin) and server (Python) parity from the same JSON. | Maintainer. |
| A12 | The rules DSL is the constrained expression-tree DSL approved by the maintainer (operators: and/or/not over gte/gt/lte/lt/eq/neq/between/in). | Portability to Kotlin and no code-injection surface. | Approved 2026-10-14. |
| A13 | Audit chain hashing is computed in the database (pgcrypto `digest()`, advisory-locked) so the Python verifier and the writer can never drift. | Parity by construction. | Maintainer. |
| A14 | Windows dev uses `.\make.ps1 <target>`; the Makefile serves Linux/CI. | `make` is not installed on the dev machine. | Maintainer. |
