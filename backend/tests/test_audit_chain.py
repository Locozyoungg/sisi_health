"""Audit trail: hash-chain integrity, append-only enforcement, and content
sanitization (never names, phones, or symptom content in audit)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.audit.service import record_event
from app.audit.verifier import verify_chain
from app.models import AuditEvent


def _event(db, **overrides):
    payload = {"action": "test", "band": "ORANGE"}
    payload.update(overrides.get("payload", {}))
    record_event(
        db,
        event_type="test_event",
        actor_type="user",
        actor_id=uuid.uuid4(),
        actor_role=None,
        resource_type="test",
        resource_id=uuid.uuid4(),
        payload=payload,
    )
    db.commit()


def test_chain_verifies_after_inserts(db):
    for _ in range(5):
        _event(db)
    report = verify_chain(db)
    assert report["ok"] is True
    assert report["events_checked"] == 5


def test_append_only_blocks_update_and_delete(db):
    _event(db)
    row = db.query(AuditEvent).first()
    with pytest.raises(ProgrammingError, match="append-only"):
        db.execute(
            text("UPDATE audit.audit_events SET payload = '{}' WHERE id = :id"), {"id": row.id}
        )
        db.commit()
    db.rollback()
    with pytest.raises(ProgrammingError, match="append-only"):
        db.execute(text("DELETE FROM audit.audit_events WHERE id = :id"), {"id": row.id})
        db.commit()
    db.rollback()


def test_verifier_detects_tampering(db):
    _event(db)
    _event(db)
    db.execute(text("ALTER TABLE audit.audit_events DISABLE TRIGGER audit_no_update"))
    db.execute(text("UPDATE audit.audit_events SET row_hash = '\\xdeadbeef'::bytea WHERE seq = 1"))
    db.commit()
    db.execute(text("ALTER TABLE audit.audit_events ENABLE TRIGGER audit_no_update"))
    report = verify_chain(db)
    assert report["ok"] is False
    assert report["broken_seqs"]


def test_sanitization_strips_pii(db):
    _event(
        db,
        payload={
            "phone": "+254712345678",
            "name": "Amina",
            "symptoms": {"pain": 7},
            "notes": "severe pain today",
            "ok_field": "band ORANGE",
            "long_number": "call 0712345678 for help",
            "nested": {"diary": {"text": "secret"}},
        },
    )
    row = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
    payload = row.payload
    assert payload["phone"] == "[REDACTED]"
    assert payload["name"] == "[REDACTED]"
    assert payload["symptoms"] == "[REDACTED]"
    assert payload["notes"] == "[REDACTED]"
    assert payload["ok_field"] == "band ORANGE"
    assert payload["long_number"] == "call [REDACTED] for help"
    assert payload["nested"] == {"diary": "[REDACTED]"}


def test_chain_survives_mixed_content(db):
    for n in range(3):
        _event(db, payload={"n": n})
    assert verify_chain(db)["ok"] is True


def test_concurrent_inserts_keep_the_chain_intact(db):
    """CC-7 regression: before migration 0011 the advisory lock was taken AFTER
    the identity seq assignment, so concurrent inserts could swap adjacent seqs
    and break the chain (surfaced by the 1,000-concurrent-USSD load test)."""
    from concurrent.futures import ThreadPoolExecutor

    from app.audit.service import record_event
    from app.audit.verifier import verify_chain
    from app.db import SessionLocal

    def write(i: int) -> None:
        with SessionLocal() as session:
            for j in range(5):
                record_event(
                    session,
                    event_type="concurrency_test",
                    actor_type="system",
                    actor_id=None,
                    actor_role=None,
                    resource_type="test",
                    resource_id=None,
                    payload={"i": i, "j": j},
                )
            session.commit()

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(write, range(20)))

    with SessionLocal() as check:
        report = verify_chain(check)
    assert report["ok"], f"broken_seqs={report['broken_seqs']}"
