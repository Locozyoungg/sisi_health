# SISI Health — OWASP ASVS Level 2 self-assessment (pen-test preparation)

**Purpose.** This is the hand-over document for the third-party penetration test
(human task **H8**, still outstanding). It itemises the OWASP Application Security
Verification Standard **4.0.3, Level 2** controls that apply to this system and records,
honestly, where each one is enforced in this repository.

**This is a self-assessment, not a certification.** "Implemented" means the control
exists in code and has a reference; it does not mean an independent tester has verified
it. Anything marked **Partial** has a named gap. Anything marked **Human task** cannot be
closed by code in this repo.

| Status | Meaning |
|---|---|
| **Implemented** | Enforced in code/config, with a file:line reference. |
| **Partial** | Partly enforced; the gap is named in the row. |
| **Human task** | Procedural, infrastructure or third-party work (H-numbers refer to `docs/human-tasks.md`). |
| **N/A** | Not applicable to this architecture; the reason is given. |

Scope of the requested test: the public staff console and API, the USSD/WhatsApp
gateway, the internal AI service, authentication/session handling, the triage engine's
safety invariants, and the backup/deploy artefacts.

---

## V1 — Architecture, Design and Threat Modeling

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 1.1.1 | Secure SDLC, documented and repeatable | `AGENTS.md` §1–3 (non-negotiables), `docs/rule-change-sop.md`, `.github/workflows/ci.yml` | Partial — process is documented, but no formal SDLC review gate |
| 1.1.2 | Threat modeling performed, per feature | `docs/architecture.md`, `docs/hazard-log.md` (clinical hazards) | **Human task** — no security threat model has been produced |
| 1.2.1 | Trusted/untrusted components separated | Separate containers `backend` / `gateway` / `ai` / `web`; `ai` is internal-only | Implemented (see V13 for the AI token) |
| 1.4.1 | Trust boundaries defined | `docs/architecture.md`, `docs/data-flow.md`; Caddy is the only public listener (`docker-compose.prod.yml`) | Implemented |
| 1.5.1 | Input separation between components | Services exchange JSON only; no shared in-process objects | Implemented |
| 1.5.2 | Components use the least privilege | **Partial** — all Python services use the same PostgreSQL role `sisi`; per-service DB roles are a H17 task |
| 1.5.3 | SSRF protections for outbound calls | `ai_service/ai_service/providers/*`, `gateway/providers/messaging.py` — outbound targets are config values, never user input | Implemented |
| 1.7.1 | Logging of security events | `backend/app/audit/service.py:56` `record_event`; audit triggers; `staff_login_locked` events (`app/auth/staff.py:102`) | Implemented |
| 1.9.1 | Data classification | `docs/data-flow.md`, `docs/data-dictionary.md` | Implemented (documentation) |
| 1.11.1 | Business logic security testing | `backend/tests/test_rules_*`, `test_rbac.py`, `test_k_anon.py`, golden cases in `ontology/golden/` | Implemented |

## V2 — Authentication

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 2.1.1 | Passwords ≥ 12 characters | `create_staff` rejects anything shorter (`app/auth/staff.py:42`), covered by `backend/tests/test_auth.py:74` | Implemented |
| 2.1.2 | Passwords ≥ 64 characters permitted | Pydantic `str` accepts any length | Implemented |
| 2.1.7 | Breached-password check | Not implemented | **Human task** — accept residual risk or add a k-anonymity range check |
| 2.2.1 | Anti-automation on login | `backend/app/auth/rate_limit.py:50` `check_and_record`, wired in `app/auth/staff.py:138`, `app/api/v1/staff_auth.py`; OTP limiter `app/auth/otp.py:40-90` | Implemented |
| 2.2.2 | Weak authenticator countermeasures | Lockout `app/auth/rate_limit.py:81-87`; OTP lockout `app/auth/otp.py:82-83` | Implemented |
| 2.2.3 | Security notifications | `staff_login_locked` audit event (`app/auth/staff.py:102`) | Partial — no out-of-band notification to the account owner |
| 2.3.1 | Authenticator binding | Session bound to device (`core.devices`); refresh tokens bound to a device via `app/auth/tokens.py` | Implemented |
| 2.5.1 | Password change/reset | Staff accounts are provisioned by an admin; no self-service reset exists | **Human task** — define the reset procedure (currently out-of-band) |
| 2.7.1 | Possession authenticator (TOTP) | Mandatory staff TOTP: `app/auth/staff.py:57-99` | Implemented |
| 2.8.1 | Time-based OTP | `pyotp` with `verify_totp` (`app/auth/staff.py:90`) | Implemented |
| 2.8.4 | TOTP single-use / replay resistance | **Gap** — `pyotp.TOTP.verify` accepts the code for its whole window; no used-code ledger | **Partial** — replay is limited by the 15-minute idle timeout but not prevented |
| 2.10.1 | Service authentication | `ai_service/ai_service/api.py:36-49` `require_internal_token`, `secrets.compare_digest` | Implemented |
| 2.10.4 | No default credentials in production | `backend/app/config.py:73-96` `_prod_guards`; `ai_service/ai_service/config.py:64-82`; hard-coded `false` flags in `docker-compose.prod.yml` | Implemented |
| 2.10.5 | No hard-coded secrets | CI `gitleaks` (`.github/workflows/ci.yml:47`); `.env.example` only; `.env.prod.example` all-empty | Implemented |

## V3 — Session Management

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 3.1.1 | No session token in the URL | Bearer token in the `Authorization` header (`web/src/api.ts:27`; `app/auth/deps.py:11`) | Implemented |
| 3.2.1 | Tokens from a CSPRNG | JWT signed with `SISI_JWT_SECRET`; refresh tokens are random and stored hashed (`app/auth/tokens.py:22,65`) | Implemented |
| 3.2.2 | High-entropy session tokens | HS256 JWT + 32-byte secret; refresh token hashed with SHA-256 | Implemented |
| 3.3.1 | Logout invalidates the session | `revoke_refresh` (`app/auth/tokens.py:121`); access tokens expire in ≤15 min (users) / 60 min (staff) | Partial — an access token stays valid until expiry (no per-token denylist) |
| 3.3.2 | Idle timeout | Staff: `app/auth/deps.py:58` (`staff_idle_minutes`, default 15). Users: access-token expiry (`app/auth/tokens.py:33`) | Implemented |
| 3.4.1 | Cookie-based session security | **N/A** — tokens travel in the `Authorization` header, no cookies, so CSRF/XSRF cookie controls do not apply |
| 3.5.1 | Stateless tokens with integrity protection | Signed JWT; algorithm pinned with `algorithms=[ALGORITHM]` (`app/auth/tokens.py:57-62`) | Implemented |
| 3.5.3 | Token revocation | Refresh-token rotation with family revocation on reuse (`app/auth/tokens.py:83-118`) | Partial — access tokens are not individually revocable |
| 3.7.1 | Re-authentication for sensitive operations | Staff idle timeout + TOTP on login; no step-up prompt for individual actions | Partial |

## V4 — Access Control

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 4.1.1 | Least privilege | Role → permission matrix `backend/app/auth/rbac.py:6-76`; `has_permission` `:79` | Implemented |
| 4.1.3 | Attribute-based access control | School/employer scoping in `app/school/*`, `app/employer/*`; corridor consent gates | Implemented |
| 4.2.1 | User-level access control on every endpoint | `require(permission)` dependency (`app/auth/deps.py:66-73`); every router applies it | Implemented |
| 4.2.2 | Horizontal access (IDOR) | School scoping and the pseudonym→person map (`app/school/*`); re-identify requires ORANGE/RED + typed reason | Partial — verified by `tests/test_rbac.py`, but no exhaustive IDOR sweep |
| 4.3.1 | Admin interface protected | `/v1/admin/*` behind `require("admin:users")` / `super_admin` (`app/auth/rbac.py`) | Implemented |
| 4.3.3 | Multi-tenancy isolation | `school_id` / `employer_id` scoping; k-anonymity suppresses small cells (`app/k_anon.py:51`) | Implemented |
| 4.4.1 | Directory / API key access | No directory service; AI token is per-deployment, not per-client | Partial |

## V5 — Validation, Sanitization and Encoding

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 5.1.1 | Positive server-side validation | Pydantic v2 request models throughout `backend/app/api/v1/*` (e.g. `staff_auth.py:21-27`, `diary.py:23`) | Implemented |
| 5.1.3 | All input is validated | All request bodies are Pydantic models; query params typed | Implemented |
| 5.1.4 | Structured data strongly typed | Pydantic + SQLAlchemy 2 typed mappings | Implemented |
| 5.3.1 | Output encoding | React escapes by default; **no `dangerouslySetInnerHTML` anywhere in `web/src`** | Implemented |
| 5.3.4 | SQL injection prevented | SQLAlchemy ORM / bound parameters; the only raw SQL is `audit/verifier.py` with bound-aware `text()` | Implemented |
| 5.3.10 | SSRF prevention | No user-supplied outbound URLs (see V1 1.5.3) | Implemented |
| 5.5.1 | Serialization safety | JSON only; no `pickle`, `eval` or unsafe deserialization in app code | Implemented |
| 5.6.1 | XXE | **N/A** — no XML parsing on any request path |
| 5.7.1 | XSS | React auto-escaping + no raw HTML sinks | Implemented |
| 5.7.4 | Content-Type correctness | FastAPI sets JSON; `web/nginx.conf` for static assets | Implemented |
| 5.9.1 | Deserialization safeguards | No native deserialization of untrusted input | N/A |

## V6 — Stored Cryptography

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 6.1.1 | Approved cryptographic module | `cryptography` (AES-GCM), `argon2-cffi` (argon2id) | Implemented |
| 6.2.1 | Key length / algorithms | AES-256-GCM (`app/crypto/key_provider.py:57-63`); argon2id defaults (`app/auth/staff.py:20`) | Implemented |
| 6.2.2 | Cryptographic randomness | `os.urandom`, `secrets` (`app/auth/tokens.py`, `app/crypto/key_provider.py:58`) | Implemented |
| 6.3.1 | Sensitive data encrypted at rest | Diary content and TOTP secrets are envelope-encrypted under per-record data keys (`app/crypto/envelope.py:13,26`, `core.data_keys`) | Partial — assessments, audit payloads and identifiers are not field-encrypted; database/disk encryption is an infrastructure control (H17) |
| 6.4.1 | Key management policy | Envelope scheme; master key via `SISI_MASTER_KEY_B64` or key file (`app/crypto/key_provider.py:37-52`) | Implemented |
| 6.4.2 | Key material protected | Secret manager / env only; `.env*` and `data/` gitignored; deploy script refuses dev defaults | Implemented |
| 6.4.3 | Key rotation | Procedure described in `AGENTS.md` §2 | **Partial** — no automated re-wrap migration; rotation is a manual, tested operation |
| 6.4.4 | Key separation | Different secrets for JWT, phone pepper, Jitsi, AI token, master key | Implemented |

## V7 — Error Handling and Logging

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 7.1.1 | No stack traces / internal detail to users | Global `AppError` handler (`app/main.py:27-32`); error envelope `app/api/envelope.py` | Implemented |
| 7.1.2 | Consistent error responses | `{"success":false,"error":{...}}` envelope everywhere | Implemented |
| 7.1.3 | No debug mode in production | API docs disabled outside dev/demo (`app/main.py:23`); no `--reload` in the prod image command | Implemented |
| 7.2.1 | Logs do not contain sensitive data | `sanitize_payload` (`app/audit/service.py:39`) strips forbidden keys and phone-like runs; edge log is method/path/status only | Implemented |
| 7.3.1 | Log integrity | Audit trail is hash-chained (`backend/migrations/versions/0001_phase1_baseline.py` trigger; `app/audit/verifier.py:46`) | Implemented |
| 7.4.1 | Generic error handler | `app/main.py:27`; `ai_service/main.py`, `gateway/main.py` mirror it | Implemented |
| 7.5.1 | Fail-safe error handling | Exceptions map to typed `AppError` subclasses (`app/core/errors.py`); no silent catches in request paths | Implemented |
| 7.6.1 | No sensitive data in client-side error rendering | `web/src/api.ts:33-36` shows `error.message` from the envelope only | Implemented |

## V8 — Data Protection

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 8.1.1 | No sensitive data in browser storage | Staff token in `sessionStorage` (`web/src/api.ts:9-15`), not `localStorage` | Partial — `sessionStorage` is still readable by any same-origin XSS; the 15-minute idle timeout bounds exposure |
| 8.1.5 | No sensitive data in URL parameters | Tokens are header-borne; IDs only in paths | Implemented |
| 8.2.1 | Cache control | `web/nginx.conf` (`no-store` for the shell, immutable for hashed assets) | Implemented |
| 8.2.2 | No sensitive data in browser cache | API responses are not cached by the SPA; no service worker | Implemented |
| 8.3.1 | Sensitive data cleared after use | Token removed on logout; idle timeout | Partial |
| 8.3.4 | Data not sent in query strings | `school_id`/`term` appear in query strings (identifiers, not clinical data) | Implemented |
| 8.3.7 | User privacy preferences | Consent module (`app/consent/*`), DSR flow (`app/dsr/*`) | Implemented |
| 8.4.1 | Sensitive data in app-switcher previews | Android `FLAG_SECURE` + hidden recents (mobile, `mobile/app/src/main`) | Implemented |
| 8.5.1 | Client-side caching of sensitive responses | React Query default (no persistence) | Implemented |

## V9 — Communication

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 9.1.1 | TLS for all client connections | `deploy/Caddyfile` (Caddy auto-HTTPS + HTTP→HTTPS redirect) | Implemented |
| 9.1.2 | TLS 1.3 / strong suites | `deploy/Caddyfile` `tls { protocols tls1.3 }` | Implemented |
| 9.1.3 | TLS for external service calls | Provider base URLs must be HTTPS in prod (`SISI_AI_HOSTED_BASE_URL`, etc.) | Partial — not programmatically enforced |
| 9.2.1 | Service-to-service encryption | **Gap** — compose-network traffic between backend/gateway/ai/db is plaintext HTTP on a private bridge network | **Partial** — acceptable only while all services share one host; document and revisit if services split across hosts |
| 9.3.1 | SMS/USSD confidentiality | **By design**: SMS and USSD are unencrypted carrier channels, so no names, conditions or scores ever traverse them (`AGENTS.md` §3.5) | N/A — mitigated by content policy |

## V10 — Malicious Code

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 10.2.1 | Malicious code search | CI `gitleaks` (`.github/workflows/ci.yml:47`) | Partial — secret scanning only; no malware/backdoor scan |
| 10.3.1 | Dependency management | `pip-audit` in CI (`.github/workflows/ci.yml:45`) | Partial — backend only; no `npm audit` for `web` |
| 10.3.2 | SBOM | `scripts/export_sbom.py` → `docs/sbom.json` (Agent E deliverable) | Partial — see `docs/sbom.json` for freshness |
| 10.3.3 | Vulnerable-component alerts | `pip-audit`; no Dependabot/renovate config in the repo | **Human task** — enable repository alerts |
| 10.4.1 | CI/CD pipeline hardening | GitHub Actions, pinned major versions | Partial — actions are tag-pinned, not SHA-pinned |

## V11 — Business Logic

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 11.1.1 | Business logic sequence enforced server-side | Deterministic rules engine (`app/rules/*`); golden cases `ontology/golden/` | Implemented |
| 11.1.2 | Anti-automation on business flows | OTP limiter (`app/auth/otp.py`), staff limiter (`app/auth/rate_limit.py`) | Partial — no general per-IP API rate limit |
| 11.1.4 | Race conditions / TOCTOU | Wallet ledger invariants (`app/employer/*`), idempotency keys on sync (`app/diary/service.py:27`) | Implemented |
| 11.1.5 | Business logic limits | k-anonymity suppression (`app/k_anon.py:51`); voucher state machine | Implemented |
| 11.1.6 | Resource exhaustion | Pydantic bounds (e.g. diary batch `max_length=200`, `app/api/v1/diary.py:23`) | Partial |
| 11.1.8 | Idempotency | `idempotency_key` on diary sync; sync merge property tests (`tests/test_diary_sync.py`) | Implemented |

## V12 — Files and Resources

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 12.1.1 | File size limits | Diary batch bounds; no file uploads in the product | N/A |
| 12.3.1 | No user-controlled file paths | Backups write to a fixed `.backups/` directory with a generated filename (`scripts/backup_db.py`) | Implemented |
| 12.6.1 | File upload security | **N/A** — no upload endpoint |

## V13 — API and Web Service

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 13.1.1 | HTTP methods / content types | FastAPI route methods; JSON bodies | Implemented |
| 13.1.3 | Versioned API | `/v1` prefix (`app/api/v1/router.py`) | Implemented |
| 13.2.1 | Schema validation | Pydantic models on every endpoint | Implemented |
| 13.2.2 | JSON parsing | `application/json` only | Implemented |
| 13.2.5 | Content-Type validation | FastAPI rejects mismatched bodies | Implemented |
| 13.3.1 | JWT signature validated | `jwt.decode(..., algorithms=[ALGORITHM])` (`app/auth/tokens.py:57-62`) | Implemented |
| 13.3.2 | JWT `exp`/`iat` validated | PyJWT expiry check + `iat` set (`app/auth/tokens.py:26-54`) | Implemented |
| 13.3.3 | JWT audience/issuer | No `aud`/`iss` claim | Partial — single-audience deployment; add if a second API consumer appears |
| 13.3.4 | Token revocation | See V3 3.5.3 | Partial |
| 13.4.1 | GraphQL | **N/A** — no GraphQL |
| 13.4.6 | WebSocket security | **N/A** — no WebSocket server; Jitsi is self-hosted and JWT-gated |
| 13.5.1 | REST service protection | Schema validation + auth throttling | Partial — no general rate limit or WAF |
| 13.5.3 | SSRF / outbound URL control | Config-only outbound targets | Implemented |

## V14 — Configuration

| ID | Control (L2) | Where enforced | Status |
|---|---|---|---|
| 14.1.1 | Repeatable build pipeline | `.github/workflows/ci.yml`; Dockerfiles in `backend/`, `web/`, `ussd-whatsapp/`, `ai_service/` | Implemented |
| 14.2.1 | Dependencies declared | `pyproject.toml` per service | Partial — lock files are Agent E's deliverable |
| 14.2.2 | Third-party libraries current | `pip-audit` in CI | Partial (see V10) |
| 14.3.1 | No debug/dev features in production | Prod guards (`app/config.py:64-88`), docs disabled, `SISI_ALLOW_UNVALIDATED_RULES=false`, `SISI_OTP_DEV_RETURN=false` hard-coded in the prod compose | Implemented |
| 14.3.2 | No default accounts | No seeded staff accounts in prod; seeds are dev-only scripts | Implemented |
| 14.3.3 | No default secrets | Deploy script refuses dev defaults; application guards refuse to boot | Implemented |
| 14.4.1 | Security headers | `deploy/Caddyfile` header block: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `-Server` | Partial — **no Content-Security-Policy** yet |
| 14.5.1 | HTTP method handling | FastAPI returns 405 for unsupported methods | Implemented |
| 14.5.3 | CORS | `app/main.py:34-45`; staging/prod require an explicit origin list (`app/config.py:38-40,87-88`); wildcard is dev/demo only; credentials off | Implemented |
| 14.5.4 | Security headers on error responses | Caddy `defer` in the header block | Implemented |
| 14.6.1 | Server-side HTTP headers | See 14.4.1 | Partial — add CSP |

---

## Findings this self-assessment already knows about

These are recorded here so the external tester is not charged for rediscovering them:

1. **No general API rate limiting.** Only OTP and staff login are throttled. The
   unauthenticated `/ussd/callback` and `/whatsapp/webhook` endpoints rely on carrier
   behaviour and session binding.
2. **TOTP replay window.** A code is accepted for the full `pyotp` window; no used-code
   ledger.
3. **Service-to-service traffic is plaintext** inside the compose network.
4. **No Content-Security-Policy** header.
5. **No web-dependency scanning** (`npm audit`) in CI, and no lock files yet.
6. **No formal security threat model** (V1.1.2) — the clinical hazard log is not a
   substitute.
7. **No third-party penetration test** — that is the point of H8.

## What the test should focus on

1. **The deterministic safety invariant**: can any input path make the LLM (or an API
   caller) assign, change or contradict a risk band or red-flag route? The engine is in
   `backend/app/rules/`; the LLM never writes a band (`AGENTS.md` §1.1).
2. **Re-identification**: can a school nurse reach a student's identity outside the
   ORANGE/RED-or-requested rules (`AGENTS.md` §3.1)? The pseudonym map and audit entry
   are the controls.
3. **Minors**: does any guardian or school-staff path expose raw symptom data
   (`AGENTS.md` §3.2–3.3)?
4. **Safeguarding override**: can a guardian be alerted when the system decided not to?
5. **k-anonymity**: differencing attacks against a school or employer dashboard with
   one or two subjects.
6. **Session lifecycle**: idle timeout, refresh rotation and reuse detection.
7. **The backup archive**: confirm it is unusable without the master key, and that the
   decrypted archive never persists on disk (see `scripts/restore_db.py`).

## Sign-off

| Field | Value |
|---|---|
| Self-assessment date | 2026-10-17 |
| Assessor | Engineering (as recorded in `docs/human-tasks.md`) |
| Third-party test (H8) | **Not commissioned** |
| Target date for external test | Before any real pilot data is processed |
