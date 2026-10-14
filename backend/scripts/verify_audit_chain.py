"""Nightly audit-chain verification entry point (also wired as an arq job stub).
Exits 1 when the chain is broken so CI/cron alerting picks it up."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.verifier import verify_chain
from app.db import SessionLocal


def main() -> int:
    with SessionLocal() as db:
        report = verify_chain(db)
    print(f"[audit] events_checked={report['events_checked']} ok={report['ok']}")
    if not report["ok"]:
        print(f"[audit] CHAIN BREAK at seq {report['broken_seqs']} — investigate immediately")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
