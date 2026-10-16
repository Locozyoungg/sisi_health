"""Employer module (Phase 7) — minimal: wallet + aggregate dashboard.

Deliberately small: an employer has a wallet (the Phase 4 `school.wallets` /
`school.wallet_ledger` tables with `owner_type='employer'` — no new wallet
schema) and a k-anonymized dashboard that counts only the linked employees'
rule evaluations. No employee-level data ever leaves this module; the dashboard
goes through the shared k-anonymity module (`app.k_anon`) exactly like the
school dashboard (spec 3.4)."""
