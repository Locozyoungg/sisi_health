"""Workers and DB-session plumbing (small but kept at 100% per the 70% floor)."""

import asyncio

from app.db import get_db
from app.workers.jobs import verify_audit_chain_job


def test_verify_audit_chain_job(db):
    import uuid

    from app.audit.service import record_event

    record_event(
        db,
        event_type="worker_test",
        actor_type="system",
        actor_id=None,
        actor_role=None,
        resource_type="test",
        resource_id=uuid.uuid4(),
    )
    db.commit()
    # The job opens its own session; run it against the same DB.
    report = asyncio.run(verify_audit_chain_job({}))
    assert report["ok"] is True
    assert report["events_checked"] >= 1


def test_get_db_yields_session(db):
    gen = get_db()
    session = next(gen)
    try:
        assert session is not None
        assert session.is_active
    finally:
        gen.close()  # triggers the finally: db.close()
