"""Phase 5 reminder tests (spec 5.4.1): screening prompts are driven by the
ontology schedule config (never hard-coded), the wording is generic in every
channel (non-negotiable 4), and the follow-up tracker sweep advances its counters
and derives loss-to-follow-up."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.core.time import utc_now_naive
from app.corridor import reminders, tracking
from app.corridor.config import REQUIRED_STATES, screening_schedule
from app.models import AuditEvent, FollowUpTracker, User
from app.testkit import auth_headers
from app.users.service import create_user

SCHEDULE = screening_schedule()


def make_user(db, provider, *, birth_date: date, phone_prefix: str = "+2548") -> User:
    user = create_user(
        db,
        provider,
        phone=f"{phone_prefix}{uuid.uuid4().int % 10**8:08d}",
        birth_date=birth_date,
        language="en",
        settings=get_settings(),
    )
    db.flush()
    return user


def due_now(user: User):
    """A clock far enough past registration that the screening interval elapsed."""
    return user.created_at + timedelta(days=SCHEDULE["screening_interval_days"] + 1)


def add_tracker(db, staff, user, *, due_days: int | None = -1) -> FollowUpTracker:
    created = tracking.create_tracker(
        db, user_id=user.id, facility_id=None, staff_id=staff.id
    )
    tracker = db.get(FollowUpTracker, uuid.UUID(created["id"]))
    if due_days is not None:
        tracker.due_at = utc_now_naive() + timedelta(days=due_days)
        db.flush()
    return tracker


def raw_reminder_rows(db) -> list:
    """Read `corridor.reminders` without the (broken) ORM mapping."""
    return db.execute(text("SELECT kind, status, message_key FROM corridor.reminders")).all()


# --- ontology schedule config ------------------------------------------------


def test_screening_schedule_comes_from_the_ontology_config():
    assert isinstance(SCHEDULE["screening_start_age"], int)
    assert SCHEDULE["screening_start_age"] == 25
    assert SCHEDULE["screening_interval_days"] > 0
    assert set(SCHEDULE["reminder_intervals_days"]) == set(REQUIRED_STATES)
    assert SCHEDULE["reminder_grace_days"] > 0
    assert SCHEDULE["max_missed_reminders"] >= 1


def test_completed_has_no_configured_interval():
    """The schedule has no `completed` interval: terminal states clear due_at
    instead of recomputing it (see test_corridor_tracking.py)."""
    assert "completed" not in SCHEDULE["reminder_intervals_days"]
    with pytest.raises(KeyError):
        reminders.screening_schedule()["reminder_intervals_days"]["completed"]


# --- screening sweep ---------------------------------------------------------


def test_user_below_the_screening_start_age_is_never_due(db, provider):
    """The age gate comes first: a 20-year-old is never due, however long ago
    she registered."""
    young = make_user(db, provider, birth_date=date(2006, 5, 1))
    now = young.created_at + timedelta(days=SCHEDULE["screening_interval_days"] + 1)
    assert reminders.due_screening_users(db, provider, now) == []
    assert young.status == "active"


def test_due_screening_users_returns_due_adults(db, provider, make_adult):
    user = make_adult()  # 25+ today
    due = reminders.due_screening_users(db, provider, due_now(user))
    assert [u.id for u, _age in due] == [user.id]
    assert due[0][1] >= SCHEDULE["screening_start_age"]


def test_send_screening_reminders_dispatches_generic_sms_idempotently(db, provider,
                                                                     make_adult):
    user = make_adult()
    sent: list[tuple[str, str]] = []
    now = due_now(user)
    report = reminders.send_screening_reminders(
        db, provider, lambda p, m: sent.append((p, m)), now
    )
    assert report[0]["status"] == "sent"
    assert sent == [(str(user.phone_hash), reminders.GENERIC_REMINDER_TEXT)]
    assert raw_reminder_rows(db) == [("screening", "sent", "generic_health_checkin")]
    # Idempotent: the unique (user, kind, due_at) row is skipped on a rerun.
    again = reminders.send_screening_reminders(
        db, provider, lambda p, m: sent.append((p, m)), now
    )
    assert again == []
    assert len(sent) == 1


def test_run_reminders_dispatches_and_audits(db, provider, make_adult):
    user = make_adult()
    sent: list[tuple[str, str]] = []
    result = reminders.run_reminders(
        db, provider, lambda p, m: sent.append((p, m)), due_now(user)
    )
    assert len(result["screening"]) == 1
    assert sent == [(str(user.phone_hash), reminders.GENERIC_REMINDER_TEXT)]
    events = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "reminders_run")
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload["screening"] == 1


def test_reminders_run_endpoint_dispatches(client, db, provider, make_staff,
                                           staff_token, adult_with_consent):
    staff = make_staff("nurse")
    db.commit()
    response = client.post(
        "/v1/corridor/reminders/run", headers=auth_headers(staff_token(staff))
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "sms_dispatched" in body["data"]
    events = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "reminders_run")
    ).scalars().all()
    assert events


# --- generic wording ---------------------------------------------------------


def test_screening_reminder_constants_are_generic():
    assert reminders.GENERIC_REMINDER_TEXT == "Time for your health check-in."
    assert reminders.MESSAGE_KEY == "generic_health_checkin"
    assert not any(character.isdigit() for character in reminders.GENERIC_REMINDER_TEXT)
    lowered = reminders.GENERIC_REMINDER_TEXT.lower()
    for term in (
        "cervical",
        "hpv",
        "cancer",
        "endometriosis",
        "fibroid",
        "pcos",
        "bleeding",
        "discharge",
        "pain",
        "period",
        "diagnosis",
        "symptom",
    ):
        assert term not in lowered, term


# --- follow-up tracker sweep -------------------------------------------------


def test_tracker_sweep_advances_counters_and_sends_generic_text(db, make_staff,
                                                                adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent, due_days=-1)
    sent: list[tuple[str, str]] = []
    report = reminders.send_tracker_reminders(
        db, lambda phone, message: sent.append((phone, message)), utc_now_naive()
    )
    assert tracker.reminders_sent == 1
    assert tracker.last_reminder_at is not None
    assert report == [
        {"tracker": str(tracker.id), "status": "sent", "lost_to_follow_up": False}
    ]
    assert sent == [(str(tracker.user_id), reminders.GENERIC_REMINDER_TEXT)]
    assert raw_reminder_rows(db) == []  # this path never writes corridor.reminders

    reminders.send_tracker_reminders(db, lambda p, m: None, utc_now_naive())
    assert tracker.reminders_sent == 2
    assert tracker.lost_to_follow_up is False  # the grace window has not elapsed


def test_tracker_sweep_skips_a_future_due_date(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    # due_days=None keeps the config-computed due_at (30 days out for "referred")
    tracker = add_tracker(db, staff, adult_with_consent, due_days=None)
    report = reminders.send_tracker_reminders(db, lambda p, m: None, utc_now_naive())
    assert report == []
    assert tracker.reminders_sent == 0
    assert tracker.lost_to_follow_up is False
    assert tracker.due_at > utc_now_naive()


def test_tracker_sweep_records_a_delivery_failure(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent, due_days=-1)

    def boom(phone: str, message: str) -> None:
        raise RuntimeError("synthetic gateway failure")

    report = reminders.send_tracker_reminders(db, boom, utc_now_naive())
    assert report[0]["status"] == "failed"
    assert tracker.reminders_sent == 1  # the attempt still counts


def test_tracker_sweep_derives_lost_to_follow_up_after_the_grace_window(db, make_staff,
                                                                       adult_with_consent):
    grace = SCHEDULE["reminder_grace_days"]
    max_missed = SCHEDULE["max_missed_reminders"]
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent, due_days=-(grace + 1))
    tracker.reminders_sent = max_missed - 1
    db.flush()
    report = reminders.send_tracker_reminders(db, lambda p, m: None, utc_now_naive())
    assert tracker.reminders_sent == max_missed
    assert tracker.lost_to_follow_up is True
    assert report[0]["lost_to_follow_up"] is True
    # status only — a tracker reminder never carries results detail
    assert set(report[0].keys()) == {"tracker", "status", "lost_to_follow_up"}


def test_tracker_sweep_never_reports_content(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    add_tracker(db, staff, adult_with_consent, due_days=-1)
    rows = reminders.send_tracker_reminders(db, lambda p, m: None, utc_now_naive())
    for row in rows:
        assert "result" not in str(row)
        assert "indicator" not in str(row)
