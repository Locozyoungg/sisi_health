# Role Matrix

Per role: every endpoint it may call and every data class it may read or
write. RBAC tests assert every endpoint denies unauthorized roles.

Roles active in Phase 1: `SUPER_ADMIN`, `NURSE`, `GYNECOLOGIST`, and patients
(`USER` scope). Phase 4 activates `SCHOOL_ADMIN` (school-scope console) and
`PHARMACY` (voucher redemption). Phase 5 activates the specialist corridor for
`NURSE` (triage, tracker, reminders), `GYNECOLOGIST` (consults, referrals,
surgery navigation) and `MOH_VIEWER` (k-anonymized aggregates only).
Phase 7 activates `EMPLOYER_ADMIN` (CC-5): wallet read and the aggregate,
k-anonymized dashboard for the employer it is bound to — nothing else. A staff
account bound to no employer can read neither.

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
| `corridor:queue` | read the specialist review queue (pseudonym, band, flags only) |
| `corridor:consults` | review consult requests, record consent/chaperone, run telehealth sessions |
| `corridor:referrals` | draft and send referral letters (the patient approves the content) |
| `corridor:facilities:read` | read the facility directory |
| `corridor:facilities:write` | create/update/delete/verify facility entries |
| `corridor:surgery` | surgery navigation: cases, outcome categories, indicative pricing stubs |
| `corridor:tracking` | follow-up tracker (status only) and patient sharing toggles |
| `corridor:reminders` | run the screening / follow-up reminder sweep |
| `corridor:aggregates` | read k-anonymized corridor aggregates only |
| `corridor:education:read` | read the education content library |
| `employer:admin` | create employers, bind staff to them, fund employer wallets (super-admin action) |
| `employer:wallet` | read the bound employer's wallet balance and ledger |
| `employer:dashboard` | read the bound employer's k-anonymized dashboard |

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
| `corridor:queue` | ✓ | ✓ | ✓ | — | — | — | — |
| `corridor:consults` | ✓ | ✓ | ✓ | — | — | — | — |
| `corridor:referrals` | ✓ | — | ✓ | — | — | — | — |
| `corridor:facilities:read` | ✓ | ✓ | ✓ | — | — | — | — |
| `corridor:facilities:write` | ✓ | — | — | — | — | — | — |
| `corridor:surgery` | ✓ | — | ✓ | — | — | — | — |
| `corridor:tracking` | ✓ | ✓ | — | — | — | — | — |
| `corridor:reminders` | ✓ | ✓ | — | — | — | — | — |
| `corridor:aggregates` | ✓ | — | — | — | — | ✓ | — |
| `corridor:education:read` | ✓ | ✓ | ✓ | ✓ | — | — | — |
| `employer:admin` | ✓ | — | — | — | — | — | — |
| `employer:wallet` | ✓ | — | — | — | ✓ | — | — |
| `employer:dashboard` | ✓ | — | — | — | ✓ | — | — |

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

## Data classes per role (Phase 5 additions)

| Data class | SUPER_ADMIN | NURSE | GYNECOLOGIST | SCHOOL_ADMIN | MOH_VIEWER |
|---|---|---|---|---|---|
| Corridor case view (computed features + bands, inside the corridor) | read | read | read | — | — |
| Raw diary payloads | never decrypted by any corridor endpoint | same | same | — | — |
| Referral letter content (patient-approved sections) | read | — | read (draft/send) | — | — |
| Consult queue rows (pseudonym, band, flags) | read | read | read | — | — |
| Telehealth session room + JWT | issue | — | issue | — | — |
| Follow-up tracker rows (status only, no results detail) | read | read | — | — | — |
| Tracker results detail | **never stored anywhere** | never | never | — | — |
| Corridor aggregates (k-anonymized, cells < 5 suppressed) | read | — | — | — | read |
| Facility directory (with the 90-day staleness warning) | read/write | read | read | — | — |
| Education content library (unvalidated until clinician sign-off) | read | read | read | read | — |

Notes:

- The corridor never decrypts raw diary ciphertext. Case views decrypt only the
  sealed *computed feature snapshot* written at booking time (spec 5.4, D5), and
  every case view writes an audited `corridor_case_viewed` event.
- The tracker stores status and navigation counters only; there is no
  results-detail column anywhere in the schema, so no role can read one.
- Referral sharing is patient-controlled: the patient previews the full letter,
  approves section by section, and can revoke at any time. Every approval and
  revocation writes a `sharing_approvals` row.
- `MOH_VIEWER` can only ever see k-anonymized cells; below 20 tracker rows the
  response is `not_enough_data`, never a small or zero count.

## Data classes per role (Phase 7 additions)

| Data class | SUPER_ADMIN | EMPLOYER_ADMIN |
|---|---|---|
| Employer wallet balance + ledger | read, fund (admin action) | read (own employer only) |
| Employer dashboard cells (k-anonymized band counts) | read | read (own employer only) |
| Employee-level data (who a band belongs to, any diary payload) | **never through this module** | **never through this module** |
| Staff↔employer binding | write (create/bind) | read (own binding only) |

Notes:

- The employer module is aggregate-only: the dashboard returns band cells and a
  total, and it runs through the same `app/k_anon.py` module as the school
  dashboard, so cells below 5 are suppressed (with complementary suppression)
  and below 20 linked employees nothing is published.
- The `users.employer_id` linkage is an admin-action opt-in (super_admin only)
  and every create/bind/fund writes an audit event.
- Wallet and ledger tables are shared with the school module — Phase 7 adds no
  new wallet schema (contract note CC-5).
