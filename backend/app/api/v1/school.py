"""School-module endpoints: nurse queue, actions, re-identification, guardian
consents, guardian alerts, dashboard (k-anonymized)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import require
from app.db import get_db
from app.models import StaffUser
from app.school import service

router = APIRouter(prefix="/school", tags=["school"])

QueueDep = Annotated[StaffUser, Depends(require("school:queue"))]
ActionsDep = Annotated[StaffUser, Depends(require("school:actions"))]
ReidentifyDep = Annotated[StaffUser, Depends(require("school:reidentify"))]
ConsentsDep = Annotated[StaffUser, Depends(require("school:consents"))]
DashboardDep = Annotated[StaffUser, Depends(require("school:dashboard"))]


class ActionIn(BaseModel):
    assessment_id: uuid.UUID
    action: str = Field(pattern=r"^(spoke_to|referred|escalated|contacted)$")
    note: str | None = Field(default=None, max_length=500)


class ReidentifyIn(BaseModel):
    assessment_id: uuid.UUID
    reason: str = Field(min_length=5, max_length=200)


class ConsentIn(BaseModel):
    assessment_id: uuid.UUID
    method: str = Field(pattern=r"^(sms_link|paper|voice)$")
    evidence_ref: str | None = None


@router.get("/queue")
def queue(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: QueueDep,
    limit: int = 50,
) -> dict[str, Any]:
    return ok(service.queue(db, provider, staff.id, limit=min(max(limit, 1), 200)))


@router.post("/actions")
def action(
    body: ActionIn,
    db: Annotated[Session, Depends(get_db)],
    staff: ActionsDep,
) -> dict[str, Any]:
    row = service.add_action(
        db, staff_id=staff.id, assessment_id=body.assessment_id, action=body.action, note=body.note
    )
    db.commit()
    return ok({"id": str(row.id), "action": row.action})


@router.post("/reidentify")
def reidentify(
    body: ReidentifyIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: ReidentifyDep,
) -> dict[str, Any]:
    result = service.reidentify(
        db, provider, staff_id=staff.id, assessment_id=body.assessment_id, reason=body.reason
    )
    db.commit()
    return ok(result)


@router.post("/guardian-consents")
def guardian_consent(
    body: ConsentIn,
    db: Annotated[Session, Depends(get_db)],
    staff: ConsentsDep,
) -> dict[str, Any]:
    row = service.record_guardian_consent(
        db,
        staff_id=staff.id,
        assessment_id=body.assessment_id,
        method=body.method,
        evidence_ref=body.evidence_ref,
    )
    db.commit()
    return ok({"id": str(row.id), "method": row.method})


@router.post("/guardian-alerts/run")
def run_guardian_alerts(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: ConsentsDep,
) -> dict[str, Any]:
    # Real SMS goes through the gateway provider at pilot time; the backend
    # records delivery status either way (spec 3.3: generic wording only).
    sent: list[tuple[str, str]] = []

    def sms_send(phone: str, message: str) -> None:
        sent.append((phone, message))

    report = service.guardian_alerts(db, provider, sms_send)
    db.commit()
    return ok({"alerts": report, "sms_dispatched": len(sent)})


@router.get("/dashboard")
def dashboard(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: DashboardDep,
    school_id: uuid.UUID,
    term: str = "2026-T1",
) -> dict[str, Any]:
    return ok(service.dashboard(db, provider, school_id=school_id, term=term))
