"""Re-anchor the audit hash chain after a break (dev/demo ONLY).

CC-7: before migration 0011, concurrent inserts could produce pairwise seq
swaps that break the chain. This script recomputes prev_hash/row_hash
SEQUENTIALLY in seq order (each hash chains from the newly computed previous
one — a single-pass lag would not be transitive-correct). The no-update
trigger is disabled for the duration and re-enabled afterwards; the chain is
verified at the end. Production incidents must preserve the broken chain as
evidence instead — see docs/breach-runbook.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.audit.verifier import verify_chain  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402

RECOMPUTE_SQL = """
DO $$
DECLARE
    r record;
    prev bytea := '\\x00'::bytea;
    h bytea;
BEGIN
    FOR r IN SELECT * FROM audit.audit_events ORDER BY seq LOOP
        h := digest(
            prev || convert_to(
                jsonb_build_object(
                    'event_type',    r.event_type,
                    'actor_type',    r.actor_type,
                    'actor_id',      r.actor_id,
                    'actor_role',    r.actor_role,
                    'resource_type', r.resource_type,
                    'resource_id',   r.resource_id,
                    'payload',       r.payload,
                    'created_at',    r.created_at
                )::text, 'UTF8'),
            'sha256');
        UPDATE audit.audit_events SET prev_hash = prev, row_hash = h WHERE seq = r.seq;
        prev := h;
    END LOOP;
END;
$$;
"""


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("repair_audit_chain refuses to run outside dev/demo")
        return 1
    if "--yes" not in sys.argv:
        print("recomputes the audit chain; pass --yes to confirm (dev/demo only)")
        return 1
    with SessionLocal() as db:
        db.execute(text("ALTER TABLE audit.audit_events DISABLE TRIGGER audit_no_update"))
        try:
            db.execute(text(RECOMPUTE_SQL))
        finally:
            db.execute(text("ALTER TABLE audit.audit_events ENABLE TRIGGER audit_no_update"))
        db.commit()
        report = verify_chain(db)
        db.commit()
    print("[repair] chain recomputed;", report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
