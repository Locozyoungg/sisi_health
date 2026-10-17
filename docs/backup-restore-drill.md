# Backup / restore drill — SISI Health

**Status: PASS** — executed twice, for real, on the Windows dev machine against the
dev `sisi` database, using the portable PostgreSQL 16.8 install at
`.tools/pgsql/pgsql/bin`. No production data was involved: the dev database contains
synthetic demo data only (non-negotiable 2).

The drill proves three things the runbook depends on:

1. `scripts/backup_db.py` produces an encrypted archive that is actually restorable.
2. `scripts/restore_db.py` recreates the database faithfully — every table, every row,
   and the append-only audit hash chain intact.
3. The operator can rehearse a restore against a scratch database without touching the
   live one.

## Runs

| Run | When (UTC) | Dataset | Archive | Required sample | All tables | Audit chain |
|---|---|---|---|---|---|---|
| 1 (baseline) | 2026-10-16 23:27 | 33 users, 463 diary entries | 464,714 B | PASS | 47/47 identical | PASS (153 events) |
| 2 (expanded seeds) | 2026-10-17 02:29 | 70 users, 3,793 diary entries, 2 schools | 1,931,667 B | PASS | 48/48 identical | PASS (239 events) |

Run 2 is the authoritative run for the phase gate; run 1 is kept because it was the
first end-to-end pass and it shows the drill is repeatable as the dataset grows. The
table count rose from 47 to 48 between the runs because migration 0010 added
`core.auth_throttle`.

## Environment (both runs)

| Item | Value |
|---|---|
| Host | Windows 10 dev machine (no VPS, no Docker database) |
| PostgreSQL | 16.8, portable install at `.tools/pgsql/pgsql/bin` |
| Python | backend venv (`backend/.venv/Scripts/python.exe`) |
| Source database | `sisi` (dev, synthetic data) |
| Scratch database | `sisi_restore_test` (created by `--create-db`, dropped after) |
| Master key | `backend/data/master.key` (dev, auto-generated, gitignored) |
| Archive format | `pg_dump --format=custom`, AES-256-GCM, 12-byte nonce prefix |

## Exact commands, with results (run 2)

### 0. Start the database

```powershell
.\make.ps1 db-up          # portable PostgreSQL ("ensure"); or `docker compose up -d db redis`
```

Result: **PASS** — the server is running on `localhost:5432`; databases `sisi` and
`sisi_test` are present.

### 1. Back up the dev database

```powershell
.\make.ps1 backup
# equivalent: backend\.venv\Scripts\python.exe scripts\backup_db.py
```

```
[backup] pg_dump:  E:\Projects\sisi_health\.tools\pgsql\pgsql\bin\pg_dump.exe
[backup] source:   postgresql://sisi@localhost:5432/sisi
[backup] archive:  1,931,667 bytes (pg_dump custom format)
[backup] encrypted 1,931,695 bytes -> E:\Projects\sisi_health\.backups\sisi-20261017T022918Z.dump.enc
[backup] cipher:   AES-256-GCM (12-byte nonce prefix), key from E:\Projects\sisi_health\backend\data\master.key
[backup] OK
```

Result: **PASS** — a 1,931,667-byte custom-format archive, encrypted to
`.backups/sisi-20261017T022918Z.dump.enc` (1,931,695 bytes; the 28-byte overhead is
the 12-byte nonce plus the 16-byte GCM tag). The plaintext archive never lands on disk.

### 2. Restore into a scratch database

```powershell
.\make.ps1 restore --target-url "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_restore_test" --create-db
# equivalent (what the drill actually ran):
backend\.venv\Scripts\python.exe scripts\restore_db.py --yes --create-db `
  --target-url "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_restore_test"
```

```
[restore] source:     E:\Projects\sisi_health\.backups\sisi-20261017T022918Z.dump.enc (1,931,695 bytes encrypted)
[restore] created database sisi_restore_test
[restore] pg_restore: E:\Projects\sisi_health\.tools\pgsql\pgsql\bin\pg_restore.exe
[restore] target:     postgresql://sisi@localhost:5432/sisi_restore_test (--clean --if-exists)
[restore] archive:    1,931,667 bytes replayed
[restore] OK
```

Result: **PASS** — the scratch database did not exist and was created by the script
(`--create-db`); `pg_restore` returned 0 with no `error:` lines.

### 3. Verify the row-count sample

```powershell
$psql = ".\.tools\pgsql\pgsql\bin\psql.exe"
$q = "select 'users='||(select count(*) from core.users)" +
     "||' diary='||(select count(*) from diary.diary_entries)" +
     "||' audit='||(select count(*) from audit.audit_events)" +
     "||' chunks='||(select count(*) from ai.content_chunks);"
& $psql -h 127.0.0.1 -p 5432 -U sisi -d sisi               -tAc $q
& $psql -h 127.0.0.1 -p 5432 -U sisi -d sisi_restore_test  -tAc $q
```

| Table | `sisi` (source) | `sisi_restore_test` (restored) | Match |
|---|---|---|---|
| `core.users` | 70 | 70 | YES |
| `diary.diary_entries` | 3,793 | 3,793 | YES |
| `audit.audit_events` | 239 | 239 | YES |
| `ai.content_chunks` | 92 | 92 | YES |

Result: **PASS** — the required four-table sample matches exactly.

### 4. Verify *every* table (stronger check)

The drill goes past the required sample and compares the row count of all 48 tables
across the `core`, `diary`, `audit`, `school`, `corridor` and `ai` schemas, using
psql's `\gexec` to generate one `count(*)` per table:

```sql
-- counts.sql
SELECT format('SELECT %L AS tbl, count(*) AS n FROM %I.%I;',
              table_schema||'.'||table_name, table_schema, table_name)
FROM information_schema.tables
WHERE table_schema IN ('core','diary','audit','school','corridor','ai')
ORDER BY table_schema, table_name
\gexec
```

```powershell
& $psql -h 127.0.0.1 -p 5432 -U sisi -d sisi              -tA -F'|' -f counts.sql > counts_sisi.txt
& $psql -h 127.0.0.1 -p 5432 -U sisi -d sisi_restore_test -tA -F'|' -f counts.sql > counts_restore.txt
if (Compare-Object (Get-Content counts_sisi.txt) (Get-Content counts_restore.txt)) { "FAIL" } else { "IDENTICAL" }
```

Result: **PASS** — `source tables: 48  restored tables: 48`, diff empty
(`FULL TABLE COUNT DIFF: IDENTICAL`).

### 5. Verify the audit hash chain in the restored copy

The append-only audit trail is hash-chained (each row stores the hash of the previous
row); a byte-faithful restore must leave the chain verifiable.

```powershell
cd backend
$env:SISI_DATABASE_URL = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_restore_test"
..\backend\.venv\Scripts\python.exe scripts\verify_audit_chain.py
```

```
[audit] events_checked=239 ok=True
```

Result: **PASS** — all 239 restored audit events reproduce their `row_hash` and their
`prev_hash` linkage. This is the strongest evidence in the drill that the encryption
round-trip and `pg_dump`/`pg_restore` preserve the data bit-for-bit.

### 6. Drop the scratch database

```powershell
& ".\.tools\pgsql\pgsql\bin\dropdb.exe" -h 127.0.0.1 -p 5432 -U sisi --no-password sisi_restore_test
```

```
sisi
sisi_test
```

Result: **PASS** — the scratch database is gone; only `sisi` and `sisi_test` remain.

## Summary

| # | Step | Run 1 | Run 2 |
|---|---|---|---|
| 0 | Start database | PASS | PASS |
| 1 | `backup_db.py` → encrypted archive | PASS (464,742 B) | PASS (1,931,695 B) |
| 2 | `restore_db.py` → `sisi_restore_test` (`--clean --if-exists`) | PASS | PASS |
| 3 | Required 4-table row-count sample | PASS | PASS |
| 4 | All tables compared — identical | PASS (47/47) | PASS (48/48) |
| 5 | Audit hash chain verified in restored DB | PASS (153) | PASS (239) |
| 6 | Scratch database dropped | PASS | PASS |

**Drill verdict: PASS.**

## Findings and follow-ups

- **`--clean --if-exists` is destructive by design.** `restore_db.py` refuses to run
  without `--yes`, and it prints the redacted target URL in the refusal message so an
  operator sees which database they were about to overwrite.
- **Restore the dump to a scratch name and check counts before any production restore.**
  This drill is the template: `--target-url` a scratch database, compare `count(*)` per
  table, verify the audit chain, then promote.
- **Take the comparison inside a quiet window.** The drill compares the restored copy
  against the live `sisi` database; if a seed or test is writing to `sisi` while the
  drill runs, the source counts can move after the dump and the comparison will show a
  false difference. Run the drill on a quiescent database.
- **Key custody is the real risk, not the archive.** The encrypted dump is useless
  without the master key. The backup and the key must never be stored together
  (see docs/runbook.md, "Backup and restore"). Losing the master key also destroys the
  per-record data-key wrappings in `core.data_keys`, so key backup is as critical as
  database backup.
- **NOT yet drilled (human task H17):** the nightly encrypted off-host backup and the
  *tested restore from object storage* on the provisioned VPS, including a restore into a
  fresh PostgreSQL instance with a different data directory. This drill validates the
  tooling only; the scheduling, off-site copy and retention window are deployment work.
- **NOT yet drilled:** point-in-time recovery (WAL archiving). The current scheme is a
  nightly logical dump — RPO is up to 24 hours. PITR is a decision for the maintainer,
  not an assumption.
