# ASVS L2 → code path → test mapping

Companion to `docs/pen-test-checklist.md`. The checklist records **whether** a control is
enforced; this file records **where** it lives and **which test would catch a regression**.

Read the columns as: *control* → *implementation* → *the test that fails if the
implementation is removed*. "No direct test" is called out honestly rather than papered
over — those are the controls the external test (H8) should probe hardest.

Paths are relative to the repository root. Test files are under `backend/tests/` unless
stated otherwise.

## V1 — Architecture / design

| ASVS | Code path | Test |
|---|---|---|
| 1.4.1 trust boundaries | `docker-compose.prod.yml`, `deploy/Caddyfile` | no direct test (config validated with `docker compose config` + `caddy validate`) |
| 1.7.1 security event logging | `backend/app/audit/service.py:56`, `backend/app/auth/staff.py:102` | `test_rate_limit.py::test_lock_engages_writes_a_counts_only_audit_event`, `test_audit_chain.py` |
| 1.11.1 business logic | `backend/app/rules/`, `backend/app/employer/` | `test_rules_*.py`, `test_employer_module.py` |

## V2 — Authentication

| ASVS | Code path | Test |
|---|---|---|
| 2.1.1 password length | `backend/app/auth/staff.py:42` | `test_auth.py::test_staff_password_min_length` |
| 2.2.1 anti-automation (staff) | `backend/app/auth/rate_limit.py:50`, `backend/app/auth/staff.py:138` | `test_rate_limit.py::test_staff_login_wrong_password_locks_out_even_correct_credentials` |
| 2.2.1 anti-automation (OTP) | `backend/app/auth/otp.py:40-90` | `test_otp.py` (request window, verify lockout) |
| 2.2.2 lockout | `backend/app/auth/rate_limit.py:73-87` | `test_rate_limit.py::test_lockout_after_max_failures`, `::test_lockout_expires_and_the_next_window_starts_clean` |
| 2.5.1 provisioning (no self-service reset) | `backend/app/auth/staff.py:30` (`create_staff`) | `test_auth.py::test_staff_totp_setup_and_login` |
| 2.7.1 / 2.8.1 TOTP | `backend/app/auth/staff.py:57-99` | `test_auth.py::test_staff_totp_setup_and_login`, `::test_staff_login_requires_confirmed_totp` |
| 2.8.4 TOTP replay | not implemented | **no direct test** (known gap) |
| 2.10.1 service auth | `ai_service/ai_service/api.py:36-49` | `ai_service/tests/test_api.py` |
| 2.10.4 default credentials | `backend/app/config.py:73-96`, `ai_service/ai_service/config.py:64-82` | `ai_service/tests/test_config.py`; backend guards exercised by CI boot |

## V3 — Session management

| ASVS | Code path | Test |
|---|---|---|
| 3.1.1 token not in URL | `backend/app/auth/deps.py:11`, `web/src/api.ts:27` | `test_auth.py::test_staff_token_scopes` |
| 3.2.1 / 3.2.2 token generation | `backend/app/auth/tokens.py:22,26,65` | `test_auth.py` (login issues a token), `test_crypto.py` (randomness of keys) |
| 3.3.1 logout / refresh revocation | `backend/app/auth/tokens.py:83-129` | `test_auth.py` (token scopes); refresh-rotation reuse covered by `test_auth.py` |
| 3.3.2 idle timeout | `backend/app/auth/deps.py:58` | `test_auth.py::test_staff_idle_timeout` |
| 3.5.1 stateless token integrity | `backend/app/auth/tokens.py:57-62` (algorithm pinned) | `test_auth.py::test_staff_token_scopes` (tampered/absent token paths) |

## V4 — Access control

| ASVS | Code path | Test |
|---|---|---|
| 4.1.1 least privilege | `backend/app/auth/rbac.py:6-79` | `test_rbac.py::test_role_matrix_document_matches_code`, `::test_corridor_permission_table_matches_the_role_matrix`, `::test_employer_permission_table_matches_the_role_matrix` |
| 4.2.1 endpoint authorization | `backend/app/auth/deps.py:66-73` | `test_rbac.py::test_rbac_matrix`, `::test_unauthenticated_gets_401` |
| 4.2.2 IDOR / scoping | `backend/app/school/`, `backend/app/corridor/`, `backend/app/employer/` | `test_rbac.py`, `test_school_module.py`, `test_corridor_*.py`, `test_employer_module.py` |
| 4.3.1 admin interface | `backend/app/api/v1/admin.py` + `rbac.py` | `test_rbac.py::test_rbac_matrix` |
| 4.3.3 multi-tenant aggregate safety | `backend/app/k_anon.py:51` | `test_k_anon.py` (suppression + differencing) |

## V5 — Validation and encoding

| ASVS | Code path | Test |
|---|---|---|
| 5.1.1 / 5.1.3 input validation | Pydantic models in `backend/app/api/v1/*.py` | `test_rules_validation.py`, endpoint tests in `test_school_module.py` / `test_corridor_*.py` |
| 5.3.1 output encoding (XSS) | `web/src/**` (React, no raw HTML sinks) | `web/e2e/*.spec.ts` (console renders staff-controlled strings) |
| 5.3.4 SQL injection | SQLAlchemy ORM everywhere except `backend/app/audit/verifier.py` (bound `text()`) | `test_audit_chain.py` |
| 5.5.1 / 5.9.1 serialization | JSON only; no `pickle`/`eval` in app code | no direct test (code review invariant) |
| 5.7.1 XSS | `web/` | no automated scanner; `web/e2e` covers rendering |

## V6 — Stored cryptography

| ASVS | Code path | Test |
|---|---|---|
| 6.1.1 / 6.2.1 algorithms | `backend/app/crypto/key_provider.py:57-63`, `backend/app/auth/staff.py:20` | `test_crypto.py::test_roundtrip`, `::test_wrong_key_fails` |
| 6.2.2 randomness | `os.urandom` in `key_provider.py:58`, `tokens.py` | `test_crypto.py::test_data_key_persisted_once` |
| 6.3.1 field encryption | `backend/app/crypto/envelope.py:13,26`, `core.data_keys` | `test_crypto.py::test_roundtrip`, `::test_delete_data_keys`, `test_consent_erasure.py` |
| 6.4.1–6.4.4 key management | `backend/app/crypto/key_provider.py:37-52` | `test_crypto.py`; `test_auth.py` TOTP sealing |
| 6.4.3 rotation | documented in `AGENTS.md` §2 | **no test** (manual procedure) |

## V7 — Error handling and logging

| ASVS | Code path | Test |
|---|---|---|
| 7.1.1 / 7.1.2 / 7.4.1 error envelope | `backend/app/main.py:27-32`, `backend/app/api/envelope.py`, `backend/app/core/errors.py` | endpoint tests assert the envelope (`test_school_module.py`, `test_corridor_*.py`) |
| 7.1.3 debug disabled | `backend/app/main.py:23` | `ai_service/tests/test_config.py` covers the analogous AI setting; backend boot guard by config |
| 7.2.1 log scrubbing | `backend/app/audit/service.py:39` | `test_audit_chain.py` (no phone-like values in payloads), `test_rate_limit.py::test_lock_engages_writes_a_counts_only_audit_event` |
| 7.3.1 log integrity | `backend/migrations/versions/0001_phase1_baseline.py` (trigger), `backend/app/audit/verifier.py:46` | `test_audit_chain.py` |

## V8 — Data protection

| ASVS | Code path | Test |
|---|---|---|
| 8.1.1 browser storage | `web/src/api.ts:9-15` (`sessionStorage`) | `web/e2e/console.spec.ts` (login/logout flows) |
| 8.2.1 cache control | `web/nginx.conf` | no direct test |
| 8.3.7 privacy / consent | `backend/app/consent/`, `backend/app/dsr/` | `test_consent_erasure.py`, `test_dsr.py` |
| 8.4.1 app-switcher | `mobile/app/src/main` (`FLAG_SECURE`) | `mobile` unit tests (privacy lint) |

## V9 — Communication

| ASVS | Code path | Test |
|---|---|---|
| 9.1.1 / 9.1.2 TLS | `deploy/Caddyfile` (`protocols tls1.3`) | validated with `caddy validate`; no automated TLS test |
| 9.3.1 channel limits | `AGENTS.md` §3.5, `ussd-whatsapp/gateway/flows/screens.py` | `ussd-whatsapp/tests/test_ussd_screen_lint.py` (no condition names / scores in screens) |

## V10 — Malicious code / dependencies

| ASVS | Code path | Test |
|---|---|---|
| 10.2.1 secrets scan | `.github/workflows/ci.yml:47` (gitleaks) | CI job |
| 10.3.1 dependency audit | `.github/workflows/ci.yml:45` (pip-audit) | CI job |
| 10.3.2 SBOM | `scripts/export_sbom.py` → `docs/sbom.json` | `scripts/check_coverage.py` / CI freshness check (Agent E) |
| 10.4.1 pipeline | `.github/workflows/ci.yml` | CI itself |

## V11 — Business logic

| ASVS | Code path | Test |
|---|---|---|
| 11.1.1 deterministic banding | `backend/app/rules/engine.py`, `bands.py`, `redflags.py` | `test_rules_bands.py`, `test_rules_redflags.py`, `test_redflag_patterns.py`, `test_rules_service.py`, golden cases |
| 11.1.2 anti-automation | `backend/app/auth/otp.py`, `rate_limit.py` | `test_otp.py`, `test_rate_limit.py` |
| 11.1.4 race conditions | `backend/app/employer/ledger.py`, `backend/app/diary/service.py` | `test_employer_module.py` (wallet invariants), `test_diary_sync.py` (property-based merge) |
| 11.1.5 aggregate limits | `backend/app/k_anon.py:51` | `test_k_anon.py` |
| 11.1.8 idempotency | `backend/app/diary/service.py:27` | `test_diary_sync.py` |

## V12 — Files and resources

| ASVS | Code path | Test |
|---|---|---|
| 12.3.1 no user-controlled paths | `scripts/backup_db.py`, `scripts/restore_db.py` (fixed `.backups/`, generated names) | verified by the drill (`docs/backup-restore-drill.md`) |

## V13 — API

| ASVS | Code path | Test |
|---|---|---|
| 13.1.3 versioning | `backend/app/api/v1/router.py` | all endpoint tests |
| 13.2.1 schema validation | Pydantic request models | `test_rules_validation.py`, endpoint tests |
| 13.3.1 / 13.3.2 JWT | `backend/app/auth/tokens.py:57-62` | `test_auth.py::test_staff_token_scopes` |
| 13.3.4 revocation | `backend/app/auth/tokens.py:83-129` | `test_auth.py` |
| 13.5.1 API protection | `backend/app/auth/rate_limit.py`, `otp.py` | `test_rate_limit.py`, `test_otp.py` |

## V14 — Configuration

| ASVS | Code path | Test |
|---|---|---|
| 14.3.1 dev features off | `backend/app/config.py:73-96`, `docker-compose.prod.yml` | backend prod-guard tests are boot-time; `ai_service/tests/test_config.py` mirrors them |
| 14.3.3 no default secrets | `scripts/deploy.sh`, `scripts/deploy.ps1` | manual dry-run verification (recorded in the Phase 8 report) |
| 14.5.3 CORS | `backend/app/main.py:34-45`, `backend/app/config.py:38-40,87-88` | `test_rate_limit.py::test_cors_origins_are_required_outside_dev_and_demo`, `::test_cors_origins_may_stay_empty_in_dev` |
| 14.4.1 security headers | `deploy/Caddyfile` `header` block | `caddy validate`; no automated header test |
| 14.1.1 build pipeline | `backend/Dockerfile`, `web/Dockerfile`, `ussd-whatsapp/Dockerfile`, `ai_service/Dockerfile` | `docker compose config`; images built on the deploy host (H17) |

---

## Coverage gaps to hand to the external tester

| ASVS | Why it is not covered here |
|---|---|
| 2.8.4 | TOTP codes are not single-use within their validity window. |
| 6.4.3 | Master-key rotation is a documented manual procedure. |
| 9.1.1 / 9.1.2 | TLS is configured but asserted only by `caddy validate`, never by an automated handshake test. |
| 14.4.1 | No Content-Security-Policy. |
| 13.5.1 | No general rate limit; only auth surfaces are throttled. |
| 1.1.2 | No formal security threat model. |
| 5.5.1 / 5.9.1 | Serialization safety is a code-review invariant, not a test. |

## How to keep this mapping honest

1. When a control's file or line moves, update the row in the same change.
2. When a test is renamed, grep the new name into this file in the same change.
3. `docs/role-matrix.md` is already asserted against code by
   `test_rbac.py::test_role_matrix_document_matches_code`; the same drift-detection
   pattern is the long-term goal for this file.
