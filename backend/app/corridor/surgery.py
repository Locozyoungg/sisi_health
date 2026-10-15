"""Surgery navigation (spec 5.4): track referred cases through diagnostic ->
surgical evaluation -> surgery -> follow-up -> closed. Navigation and follow-up
only — no clinical decisions; pricing stubs are indicative and sourced, never
presented as medical advice."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event, sanitize_payload
from app.core.errors import Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import Facility, OutcomeLog, PricingStub, SurgeryCase, SurgeryEvent

SURGERY_TRANSITIONS: dict[str, set[str]] = {
    "diagnostic": {"surgical_evaluation", "cancelled"},
    "surgical_evaluation": {"surgery", "cancelled"},
    "surgery": {"follow_up", "cancelled"},
    "follow_up": {"closed", "cancelled"},
}
TERMINAL_SURGERY = {"closed", "cancelled"}
OUTCOME_CATEGORIES = {
    "completed_surgery",
    "follow_up_scheduled",
    "referred_on",
    "cancelled",
    "no_show",
}


def list_cases(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(SurgeryCase).order_by(SurgeryCase.created_at.desc())).scalars().all()
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "referral_id": str(r.referral_id) if r.referral_id else None,
            "facility_id": str(r.facility_id) if r.facility_id else None,
            "gynecologist_id": str(r.gynecologist_id) if r.gynecologist_id else None,
            "status": r.status,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def create_case(
    db: Session,
    *,
    staff_id: uuid.UUID,
    user_id: uuid.UUID,
    referral_id: uuid.UUID | None,
    facility_id: uuid.UUID | None,
) -> dict[str, Any]:
    case = SurgeryCase(
        id=uuid7(),
        user_id=user_id,
        referral_id=referral_id,
        facility_id=facility_id,
        gynecologist_id=staff_id,
    )
    db.add(case)
    db.flush()
    db.add(
        SurgeryEvent(
            id=uuid7(),
            case_id=case.id,
            event_type="opened",
            status_to=case.status,
            actor_type="staff",
            actor_id=staff_id,
        )
    )
    record_event(
        db,
        event_type="surgery_case_opened",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="surgery_case",
        resource_id=case.id,
        payload={},
    )
    return {"id": str(case.id), "status": case.status}


def transition_case(
    db: Session,
    *,
    staff_id: uuid.UUID,
    case_id: uuid.UUID,
    to_status: str,
    note: str | None,
) -> dict[str, Any]:
    case = db.get(SurgeryCase, case_id)
    if case is None:
        raise NotFound("surgery case not found")
    allowed = SURGERY_TRANSITIONS.get(case.status, set())
    if to_status not in allowed:
        raise Conflict(f"cannot move a surgery case from {case.status} to {to_status}")
    from_status = case.status
    case.status = to_status
    case.updated_at = utc_now_naive()
    db.add(
        SurgeryEvent(
            id=uuid7(),
            case_id=case.id,
            event_type="transitioned",
            status_from=from_status,
            status_to=to_status,
            actor_type="staff",
            actor_id=staff_id,
            note=sanitize_payload({"note": note or ""})["note"] or None,
        )
    )
    record_event(
        db,
        event_type="surgery_case_transitioned",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="surgery_case",
        resource_id=case.id,
        payload={"from": from_status, "to": to_status},
    )
    return {"id": str(case.id), "status": case.status}


def add_outcome(
    db: Session,
    *,
    staff_id: uuid.UUID,
    case_id: uuid.UUID,
    outcome_category: str,
    note: str | None,
) -> dict[str, Any]:
    """Outcome log: generic categories only (navigation, not clinical records)."""
    if outcome_category not in OUTCOME_CATEGORIES:
        raise Conflict(f"unknown outcome category: {outcome_category}")
    if db.get(SurgeryCase, case_id) is None:
        raise NotFound("surgery case not found")
    row = OutcomeLog(
        id=uuid7(),
        case_id=case_id,
        outcome_category=outcome_category,
        note=sanitize_payload({"note": note or ""})["note"] or None,
        recorded_by=staff_id,
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="surgery_outcome_logged",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="outcome_log",
        resource_id=row.id,
        payload={"category": outcome_category},
    )
    return {"id": str(row.id), "category": row.outcome_category}


def add_pricing_stub(
    db: Session,
    *,
    staff_id: uuid.UUID,
    procedure: str,
    facility_id: uuid.UUID,
    amount_ksh_min: int,
    amount_ksh_max: int,
    source: str,
    note: str | None,
) -> dict[str, Any]:
    """Indicative pricing only: `source` is required and `indicative` is forced
    True in code AND by CHECK constraint (spec 5.4)."""
    if not source:
        raise Conflict("indicative pricing requires a source")
    if amount_ksh_min < 0 or amount_ksh_max < amount_ksh_min:
        raise Conflict("invalid price range")
    if db.get(Facility, facility_id) is None:
        raise NotFound("facility not found")
    row = PricingStub(
        id=uuid7(),
        procedure=procedure,
        facility_id=facility_id,
        amount_ksh_min=amount_ksh_min,
        amount_ksh_max=amount_ksh_max,
        source=source,
        indicative=True,
        note=note,
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="pricing_stub_recorded",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="pricing_stub",
        resource_id=row.id,
        payload={"procedure": procedure, "source": source},
    )
    return {
        "id": str(row.id),
        "procedure": row.procedure,
        "amount_ksh_min": row.amount_ksh_min,
        "amount_ksh_max": row.amount_ksh_max,
        "indicative": row.indicative,
        "source": row.source,
    }


def list_pricing(db: Session, facility_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    query = select(PricingStub)
    if facility_id is not None:
        query = query.where(PricingStub.facility_id == facility_id)
    return [
        {
            "id": str(r.id),
            "procedure": r.procedure,
            "facility_id": str(r.facility_id),
            "amount_ksh_min": r.amount_ksh_min,
            "amount_ksh_max": r.amount_ksh_max,
            "currency": r.currency,
            "indicative": r.indicative,
            "source": r.source,
        }
        for r in db.execute(query).scalars()
    ]
