# Role Matrix

Per role: every endpoint it may call and every data class it may read or
write. RBAC tests assert every endpoint denies unauthorized roles.

Roles active in Phase 1: `SUPER_ADMIN`, `NURSE`, `GYNECOLOGIST`, and patients
(`USER` scope). Phase 4 activates `SCHOOL_ADMIN` (school-scope console) and
`PHARMACY` (voucher redemption). `EMPLOYER_ADMIN`, `MOH_VIEWER` are defined in
the permission table now and become usable with their modules (Phases 4/7);
the matrix is updated then via contract notes.

## Permissions

| Permission | Meaning |
|---|---|
| `diary:self` | read/write own encrypted diary entries |
| `rules:evaluate` | run the rules engine on own data |
| `rules:read` | read rule definitions and evidence |
| `rules:activate` | run the two-person activation workflow / rollback |
| `consent:self` | grant/revoke own consent |
| `dsr:self` | file own data-subject-rights requests |
| `dsr:process` | process DSR requests |
| `audit:read` | read audit events |
| `audit:verify` | trigger chain verification |
| `admin:users` | read user admin views |
| `admin:dsr` | read the DSR queue |
| `school:queue` | read the nurse flag queue (bands + pseudonyms only) |
| `school:actions` | record actions on assessments |
| `school:reidentify` | re-identify a student (ORANGE/RED or contact request) |
| `school:consents` | record guardian consents / run guardian alerts |
| `school:dashboard` | read the k-anonymized school dashboard |
| `vouchers:issue` | issue vouchers (single-use, capped) |
| `vouchers:redeem` | redeem vouchers at a verified pharmacy |
| `vouchers:reconcile` | run/read voucher reconciliation |

## Role → permissions

| Permission | SUPER_ADMIN | NURSE | GYNECOLOGIST | SCHOOL_ADMIN | EMPLOYER_ADMIN (P7) | MOH_VIEWER (P7) | PHARMACY |
|---|---|---|---|---|---|---|---|
| `diary:self` | — | — | — | — | — | — | — |
| `rules:evaluate` | — | — | — | — | — | — | — |
| `rules:read` | ✓ | ✓ | ✓ | ✓ | — | ✓ | — |
| `rules:activate` | — | — | ✓ | — | — | — | — |
| `consent:self` | — | — | — | — | — | — | — |
| `dsr:self` | — | — | — | — | — | — | — |
| `dsr:process` | ✓ | — | — | — | — | — | — |
| `audit:read` | ✓ | — | — | — | — | — | — |
| `audit:verify` | ✓ | — | — | — | — | — | — |
| `admin:users` | ✓ | — | — | — | — | — | — |
| `admin:dsr` | ✓ | — | — | — | — | — | — |
| `school:queue` | ✓ | ✓ | — | ✓ | — | — | — |
| `school:actions` | ✓ | ✓ | — | ✓ | — | — | — |
| `school:reidentify` | ✓ | ✓ | — | — | — | — | — |
| `school:consents` | ✓ | ✓ | — | ✓ | — | — | — |
| `school:dashboard` | ✓ | ✓ | — | ✓ | — | — | — |
| `vouchers:issue` | ✓ | — | — | ✓ | — | — | — |
| `vouchers:redeem` | ✓ | — | — | — | — | — | ✓ |
| `vouchers:reconcile` | ✓ | — | — | ✓ | — | — | — |

Patients (USER scope) hold `diary:self`, `rules:evaluate`, `consent:self`,
`dsr:self` implicitly — they are a token scope, not staff roles.

## Data classes per role (Phase 1)

| Data class | SUPER_ADMIN | NURSE | GYNECOLOGIST | Patient |
|---|---|---|---|---|
| Own diary plaintext | — | — | — | read/write |
| Any diary plaintext | never (ciphertext exists; keys are per-user) | never | never | — |
| Own consent state | — | — | — | read |
| Rule definitions | read | read | read | — |
| Audit events (sanitized) | read | — | — | — |
| User admin views (no medical data) | read | — | — | — |

Minors' raw symptom data: **no staff role** reads it outside the clinical
corridor (Phase 5). School staff see severity bands and actions only.
