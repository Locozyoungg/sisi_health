"""Cervical follow-up tracker (spec 5.4.1): referred -> screened ->
result_received -> further_assessment -> treatment -> follow_up -> completed.
Status-only for staff: no results detail exists anywhere in the schema.
Aggregates go through the shared k-anonymity module only."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.errors import Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.corridor.config import reminder_interval_days
from app.k_anon import Cell, apply_k_anon
from app.models import FollowUpTracker, TrackerEvent, User

TRACKER_TRANSITIONS: dict[str, set[str]] = {
    "referred": {"screened"},
    "screened": {"result_received"},
    "result_received": {"further_assessment"},
    "further_assessment": {"treatment"},
    "treatment": {"follow_up"},
    "follow_up": {"completed"},
}
TERMINAL_TRACKER = {"completed"}


def create_tracker(
    db: Session, *, user_id: uuid.UUID, facility_id: uuid.UUID | None, staff_id: uuid.UUID
) -> dict[str, Any]:
    tracker = FollowUpTracker(
        id=uuid7(),
        user_id=user_id,
        facility_id=facility_id,
        due_at=utc_now_naive() + timedelta(days=reminder_interval_days("referred")),
    )
    db.add(tracker)
    db.flush()
    db.add(
        TrackerEvent(
            id=uuid7(),
            tracker_id=tracker.id,
            status_to=tracker.status,
            actor_type="staff",
            actor_id=staff_id,
        )
    )
    record_event(
        db,
        event_type="follow_up_tracker_opened",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="follow_up_tracker",
        resource_id=tracker.id,
        payload={},
    )
    return {"id": str(tracker.id), "status": tracker.status}


def transition_tracker(
    db: Session,
    *,
    staff_id: uuid.UUID,
    tracker_id: uuid.UUID,
    to_status: str,
) -> dict[str, Any]:
    tracker = db.get(FollowUpTracker, tracker_id)
    if tracker is None:
        raise NotFound("follow-up tracker not found")
    allowed = TRACKER_TRANSITIONS.get(tracker.status, set())
    if to_status not in allowed:
        raise Conflict(f"cannot move a tracker from {tracker.status} to {to_status}")
    from_status = tracker.status
    tracker.status = to_status
    # Terminal states have no next reminder; every other state recomputes due_at
    # from the config interval (spec 5.4.1: configurable reminder intervals).
    if to_status in TERMINAL_TRACKER:
        tracker.due_at = None
    else:
        tracker.due_at = utc_now_naive() + timedelta(days=reminder_interval_days(to_status))
    tracker.updated_at = utc_now_naive()
    db.add(
        TrackerEvent(
            id=uuid7(),
            tracker_id=tracker.id,
            status_from=from_status,
            status_to=to_status,
            actor_type="staff",
            actor_id=staff_id,
        )
    )
    record_event(
        db,
        event_type="follow_up_tracker_transitioned",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="follow_up_tracker",
        resource_id=tracker.id,
        payload={"from": from_status, "to": to_status},
    )
    return {"id": str(tracker.id), "status": tracker.status}


def list_trackers(db: Session, status: str | None = None) -> list[dict[str, Any]]:
    """Staff view: status + loss-to-follow-up flag ONLY (no results detail)."""
    query = select(FollowUpTracker).order_by(FollowUpTracker.created_at.desc())
    if status is not None:
        query = query.where(FollowUpTracker.status == status)
    return [
        {
            "id": str(r.id),
            "pseudonym": str(r.user_id)[:8],
            "facility_id": str(r.facility_id) if r.facility_id else None,
            "status": r.status,
            "consent_to_share": r.consent_to_share,
            "due_at": r.due_at,
            "lost_to_follow_up": r.lost_to_follow_up,
            "updated_at": r.updated_at,
        }
        for r in db.execute(query).scalars()
    ]


def my_trackers(db: Session, user: User) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(FollowUpTracker)
            .where(FollowUpTracker.user_id == user.id)
            .order_by(FollowUpTracker.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "consent_to_share": r.consent_to_share,
            "due_at": r.due_at,
            "lost_to_follow_up": r.lost_to_follow_up,
        }
        for r in rows
    ]


def set_sharing(
    db: Session, user: User, *, tracker_id: uuid.UUID, consent_to_share: bool
) -> dict[str, Any]:
    """Patient-consented sharing (spec 5.4.1)."""
    tracker = db.get(FollowUpTracker, tracker_id)
    if tracker is None or tracker.user_id != user.id:
        raise NotFound("follow-up tracker not found")
    tracker.consent_to_share = consent_to_share
    tracker.updated_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="follow_up_sharing_updated",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="follow_up_tracker",
        resource_id=tracker.id,
        payload={"consent_to_share": consent_to_share},
    )
    return {"id": str(tracker.id), "consent_to_share": tracker.consent_to_share}


def aggregates(db: Session) -> dict[str, Any]:
    """Aggregate-only reporting through the shared k-anonymity module (spec 3.4)."""
    rows = db.execute(select(FollowUpTracker)).scalars().all()
    cells = [
        Cell(key=(f"status_{status}",), value=sum(1 for r in rows if r.status == status))
        for status in ("referred", "screened", "result_received", "further_assessment",
                       "treatment", "follow_up", "completed")
    ]
    cells.append(
        Cell(key=("lost_to_follow_up",), value=sum(1 for r in rows if r.lost_to_follow_up))
    )
    public = apply_k_anon(total=len(rows), counts=cells).public()
    return public
