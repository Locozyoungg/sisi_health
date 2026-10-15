"""Screening + follow-up reminder wording and job logic (spec 5.4.1). Wording is
generic — nothing condition-identifying may ever appear in a notification or SMS
(non-negotiable 4). Delivery goes through an injectable `sms_send` closure; the
backend records delivery status either way."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.corridor.config import screening_schedule
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import FollowUpTracker, Reminder, User
from app.users.service import age_of

GENERIC_REMINDER_TEXT = "Time for your health check-in."
MESSAGE_KEY = "generic_health_checkin"  # generic wording only, never condition names


def due_screening_users(
    db: Session, provider: DatabaseKeyProvider, now: Any
) -> list[tuple[User, int]]:
    """Users age >= config.screening_start_age who are due for a screening prompt
    (interval from config, never hard-coded)."""
    config = screening_schedule()
    start_age = config["screening_start_age"]
    interval_days = config["screening_interval_days"]
    out: list[tuple[User, int]] = []
    for user in db.execute(select(User).where(User.status == "active")).scalars():
        age = age_of(provider, db, user)
        if age is None or age < start_age:
            continue
        last = (
            db.execute(
                select(Reminder)
                .where(Reminder.user_id == user.id, Reminder.kind == "screening")
                .order_by(Reminder.due_at.desc())
            )
            .scalars()
            .first()
        )
        due = last.due_at if last is not None else user.created_at
        if (now - due) >= timedelta(days=interval_days):
            out.append((user, age))
    return out


def send_screening_reminders(
    db: Session,
    provider: DatabaseKeyProvider,
    sms_send: Any,
    now: Any,
) -> list[dict[str, Any]]:
    """Idempotent per (user, kind, due_at) via the unique constraint. Skips users
    without effective consent... (consent is checked by the caller's gate; here we
    record and dispatch)."""
    report: list[dict[str, Any]] = []
    for user, _age in due_screening_users(db, provider, now):
        existing = (
            db.execute(
                select(Reminder).where(
                    Reminder.user_id == user.id,
                    Reminder.kind == "screening",
                    Reminder.due_at == now,
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            continue
        row = Reminder(
            id=uuid7(),
            user_id=user.id,
            kind="screening",
            message_key=MESSAGE_KEY,
            due_at=now,
        )
        db.add(row)
        try:
            # Contract-level stub: real delivery goes through the gateway
            # provider at pilot time (phone resolution is a human task); the
            # backend records status either way.
            sms_send(str(user.phone_hash), GENERIC_REMINDER_TEXT)
            row.status = "sent"
            row.sent_at = utc_now_naive()
        except Exception:  # noqa: BLE001 — delivery failure recorded, not fatal
            row.status = "failed"
        db.flush()
        report.append({"user": str(user.id), "status": row.status})
    return report


def send_tracker_reminders(
    db: Session, sms_send: Any, now: Any
) -> list[dict[str, Any]]:
    """Follow-up nudges per tracker due_at; derives lost_to_follow_up after the
    configured missed-reminder threshold (status only — no results detail)."""
    config = screening_schedule()
    grace_days = config["reminder_grace_days"]
    max_missed = config["max_missed_reminders"]
    report: list[dict[str, Any]] = []
    for tracker in db.execute(
        select(FollowUpTracker).where(FollowUpTracker.status != "completed")
    ).scalars():
        if tracker.due_at is None or tracker.due_at > now:
            continue
        tracker.reminders_sent += 1
        tracker.last_reminder_at = now
        if tracker.reminders_sent >= max_missed and (now - tracker.due_at) >= timedelta(
            days=grace_days
        ):
            tracker.lost_to_follow_up = True
        tracker.updated_at = utc_now_naive()
        try:
            sms_send(str(tracker.user_id), GENERIC_REMINDER_TEXT)
            status = "sent"
        except Exception:  # noqa: BLE001 — delivery failure recorded, not fatal
            status = "failed"
        report.append(
            {
                "tracker": str(tracker.id),
                "status": status,
                "lost_to_follow_up": tracker.lost_to_follow_up,
            }
        )
    return report


def run_reminders(
    db: Session, provider: DatabaseKeyProvider, sms_send: Any, now: Any
) -> dict[str, Any]:
    screening = send_screening_reminders(db, provider, sms_send, now)
    tracker = send_tracker_reminders(db, sms_send, now)
    record_event(
        db,
        event_type="reminders_run",
        actor_type="system",
        actor_id=None,
        actor_role=None,
        resource_type="reminders",
        resource_id=uuid7(),
        payload={"screening": len(screening), "tracker": len(tracker)},  # counts only
    )
    return {"screening": screening, "tracker": tracker}
