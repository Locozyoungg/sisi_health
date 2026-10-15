"""Workers and DB-session plumbing (small but kept at 100% per the 70% floor)."""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.time import utc_now_naive
from app.corridor import tracking
from app.corridor.config import screening_schedule
from app.db import get_db
from app.models import AuditEvent, FollowUpTracker
from app.workers.jobs import (
    send_screening_reminders_job,
    send_tracker_reminders_job,
    verify_audit_chain_job,
)


def test_verify_audit_chain_job(db):
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


def test_send_screening_reminders_job_dispatches_and_audits(db, make_adult):
    user = make_adult()
    # Backdate registration so the configured 365-day screening interval elapsed.
    user.created_at = utc_now_naive() - timedelta(days=400)
    db.commit()

    report = asyncio.run(send_screening_reminders_job({}))
    assert report["kind"] == "screening"
    assert report["dispatched"] >= 1
    assert report["statuses"] == {"sent": report["dispatched"]}

    events = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "reminders_run")
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload["kind"] == "screening"
    assert events[0].payload["count"] == report["dispatched"]


def test_tracker_reminders_job_skips_future_due_dates(db, make_staff, make_adult):
    """A tracker due 30 days out produces no nudge and no lost-to-follow-up."""
    staff = make_staff("nurse")
    user = make_adult()
    tracking.create_tracker(db, user_id=user.id, facility_id=None, staff_id=staff.id)
    db.commit()
    report = asyncio.run(send_tracker_reminders_job({}))
    assert report == {
        "kind": "follow_up",
        "dispatched": 0,
        "statuses": {},
        "lost_to_follow_up": 0,
    }


def test_send_tracker_reminders_job_derives_loss_to_follow_up(db, make_staff, make_adult):
    config = screening_schedule()
    staff = make_staff("nurse")
    user = make_adult()
    created = tracking.create_tracker(
        db, user_id=user.id, facility_id=None, staff_id=staff.id
    )
    tracker = db.get(FollowUpTracker, uuid.UUID(created["id"]))
    tracker.due_at = utc_now_naive() - timedelta(days=config["reminder_grace_days"] + 1)
    tracker.reminders_sent = config["max_missed_reminders"] - 1
    db.commit()

    report = asyncio.run(send_tracker_reminders_job({}))
    assert report == {
        "kind": "follow_up",
        "dispatched": 1,
        "statuses": {"sent": 1},
        "lost_to_follow_up": 1,
    }
    db.refresh(tracker)
    assert tracker.reminders_sent == config["max_missed_reminders"]
    assert tracker.lost_to_follow_up is True
    assert tracker.last_reminder_at is not None

    events = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "reminders_run")
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload["kind"] == "follow_up"
    assert events[0].payload["count"] == 1
    assert "user_id" not in events[0].payload and "tracker" not in events[0].payload


def test_send_tracker_reminders_job_with_nothing_due(db):
    report = asyncio.run(send_tracker_reminders_job({}))
    assert report == {
        "kind": "follow_up",
        "dispatched": 0,
        "statuses": {},
        "lost_to_follow_up": 0,
    }
