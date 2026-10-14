"""Audit chain verifier. Recomputes hashes in the database (same expression as the
trigger) so writer and verifier can never drift, then checks both the row-content
hash and the previous-row linkage. Run nightly via workers/jobs.py or
`make audit-verify`; any break must alert (log ERROR + return broken seqs)."""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("sisi.audit")

VERIFY_SQL = text(
    """
    WITH data AS (
        SELECT seq, prev_hash, row_hash,
               digest(prev_hash || convert_to(
                   jsonb_build_object(
                       'event_type',   event_type,
                       'actor_type',   actor_type,
                       'actor_id',     actor_id,
                       'actor_role',   actor_role,
                       'resource_type', resource_type,
                       'resource_id',  resource_id,
                       'payload',      payload,
                       'created_at',   created_at
                   )::text, 'UTF8'), 'sha256') AS expected
        FROM audit.audit_events
    ),
    with_prev AS (
        SELECT seq, prev_hash, row_hash, expected,
               lag(row_hash) OVER (ORDER BY seq) AS prior_hash,
               min(seq) OVER () AS first_seq
        FROM data
    )
    SELECT seq FROM with_prev
    WHERE row_hash <> expected
       OR (seq = first_seq AND prev_hash <> '\\x00'::bytea)
       OR (seq > first_seq AND prev_hash IS DISTINCT FROM prior_hash)
    ORDER BY seq
    """
)


def verify_chain(db: Session) -> dict[str, Any]:
    """Return {ok, events_checked, broken_seqs}. Logs an alert when the chain is broken."""
    total: int = db.execute(text("SELECT count(*) FROM audit.audit_events")).scalar_one()
    broken = [row[0] for row in db.execute(VERIFY_SQL).all()]
    if broken:
        logger.error("AUDIT CHAIN BREAK detected at seq %s", broken)
    return {"ok": not broken, "events_checked": total, "broken_seqs": broken}
