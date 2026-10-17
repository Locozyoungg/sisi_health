"""Retention purge entry point (spec 6, assumption A3) — run nightly by cron/arq.

Deletes diary data past `SISI_RETENTION_DIARY_DAYS` and expires vouchers past
`SISI_RETENTION_VOUCHER_DAYS`. The audit table is deliberately NOT purged: it is
append-only and hash-chained, and the retention-vs-chain conflict is an open
maintainer decision (docs/assumptions.md A3). Counts-only evidence is written to
the audit trail as `retention_purge_run`; this runner re-verifies the chain
afterwards so a purge can never silently break it."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.verifier import verify_chain
from app.db import SessionLocal
from app.workers.jobs import purge_retention_job


def main() -> int:
    report = asyncio.run(purge_retention_job({}))
    print(
        "[retention] "
        + " ".join(f"{key}={value}" for key, value in sorted(report.items()))
    )
    with SessionLocal() as db:
        chain = verify_chain(db)
    print(f"[retention] audit_chain_ok={chain['ok']} events_checked={chain['events_checked']}")
    if not chain["ok"]:
        print(f"[retention] CHAIN BREAK at seq {chain['broken_seqs']} — investigate immediately")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
