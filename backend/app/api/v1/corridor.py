"""Corridor endpoints (Phase 5): consult booking/review/sessions, referrals with
patient-approved sharing, facility directory, surgery navigation, follow-up
tracker, reminders, and education content. RBAC on every staff endpoint."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import get_current_user, require
from app.config import Settings, get_settings
from app.consent.service import consent_state
from app.core.time import utc_now_naive
from app.corridor import consult, education, facilities, referral, reminders, surgery, tracking
from app.db import get_db
from app.models import StaffUser, User
from app.rules.loader import build_engine
from app.users.service import age_of

router = APIRouter(prefix="/corridor", tags=["corridor"])

QueueDep = Annotated[StaffUser, Depends(require("corridor:queue"))]
ConsultsDep = Annotated[StaffUser, Depends(require("corridor:consults"))]
ReferralsDep = Annotated[StaffUser, Depends(require("corridor:referrals"))]
FacilitiesReadDep = Annotated[StaffUser, Depends(require("corridor:facilities:read"))]
FacilitiesWriteDep = Annotated[StaffUser, Depends(require("corridor:facilities:write"))]
SurgeryDep = Annotated[StaffUser, Depends(require("corridor:surgery"))]
TrackingDep = Annotated[StaffUser, Depends(require("corridor:tracking"))]
AggregatesDep = Annotated[StaffUser, Depends(require("corridor:aggregates"))]
RemindersDep = Annotated[StaffUser, Depends(require("corridor:reminders"))]
EducationDep = Annotated[StaffUser, Depends(require("corridor:education:read"))]

UserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[Session, Depends(get_db)]


# ---- consult booking (patient) ---------------------------------------------


class BookIn(BaseModel):
    preferred_county: str | None = Field(default=None, max_length=128)
    preferred_language: str = Field(default="en", pattern=r"^(en|sw)$")
    patient_note: str | None = Field(default=None, max_length=500)
    chaperone_requested: bool = False


@router.post("/consult/requests")
def book(
    body: BookIn,
    db: DbDep,
    provider: ProviderDep,
    user: UserDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    age = age_of(provider, db, user)
    state = consent_state(db, user, age)
    engine = build_engine(
        settings.ontology_dir, allow_unvalidated=settings.allow_unvalidated_rules
    )
    result = consult.book_request(
        db,
        provider,
        user,
        engine,
        preferred_county=body.preferred_county,
        preferred_language=body.preferred_language,
        patient_note=body.patient_note,
        chaperone_requested=body.chaperone_requested,
        consent_satisfied=state["satisfied"],
    )
    db.commit()
    return ok(result)


@router.get("/consult/requests")
def my_bookings(db: DbDep, user: UserDep) -> dict[str, Any]:
    return ok(consult.my_requests(db, user))


# ---- review queue + sessions (staff) ---------------------------------------


@router.get("/queue")
def queue(
    db: DbDep, provider: ProviderDep, _staff: QueueDep, limit: int = 50
) -> dict[str, Any]:
    return ok(consult.queue(db, provider, limit=min(max(limit, 1), 200)))


@router.get("/consults/{request_id}")
def consult_detail(
    request_id: uuid.UUID, db: DbDep, provider: ProviderDep, staff: ConsultsDep
) -> dict[str, Any]:
    return ok(consult.detail(db, provider, request_id=request_id, staff_id=staff.id))


class ReviewIn(BaseModel):
    decision: str = Field(pattern=r"^(approved|declined)$")
    note: str | None = Field(default=None, max_length=500)


@router.post("/consults/{request_id}/review")
def review(
    request_id: uuid.UUID, body: ReviewIn, db: DbDep, provider: ProviderDep, staff: ConsultsDep
) -> dict[str, Any]:
    result = consult.review(
        db,
        provider,
        request_id=request_id,
        staff_id=staff.id,
        decision=body.decision,
        note=body.note,
    )
    db.commit()
    return ok(result)


class ScheduleIn(BaseModel):
    gynecologist_id: uuid.UUID
    scheduled_at: datetime
    modality: str = Field(pattern=r"^(video|audio)$")


@router.post("/consults/{request_id}/schedule")
def schedule(
    request_id: uuid.UUID, body: ScheduleIn, db: DbDep, staff: ConsultsDep
) -> dict[str, Any]:
    result = consult.schedule(
        db,
        request_id=request_id,
        gynecologist_id=body.gynecologist_id,
        scheduled_at=body.scheduled_at,
        modality=body.modality,
        staff_id=staff.id,
    )
    db.commit()
    return ok(result)


class ConsentIn(BaseModel):
    kind: str = Field(
        pattern=r"^(guardian_consent|minor_assent|chaperone_requested|chaperone_confirmed)$"
    )
    method: str = Field(default="digital", pattern=r"^(digital|sms_link|paper|voice)$")
    evidence_ref: str | None = None


@router.post("/consults/{request_id}/consents")
def record_consent(
    request_id: uuid.UUID, body: ConsentIn, db: DbDep, staff: ConsultsDep
) -> dict[str, Any]:
    result = consult.record_consent(
        db,
        request_id=request_id,
        kind=body.kind,
        method=body.method,
        evidence_ref=body.evidence_ref,
        staff_id=staff.id,
    )
    db.commit()
    return ok(result)


@router.post("/sessions/{session_id}/start")
def start_session(
    session_id: uuid.UUID, db: DbDep, provider: ProviderDep, staff: ConsultsDep
) -> dict[str, Any]:
    result = consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    db.commit()
    return ok(result)


class CompleteIn(BaseModel):
    outcome: str = Field(pattern=r"^(completed|no_show)$")


@router.post("/sessions/{session_id}/complete")
def complete_session(
    session_id: uuid.UUID, body: CompleteIn, db: DbDep, staff: ConsultsDep
) -> dict[str, Any]:
    result = consult.complete_session(
        db, session_id=session_id, outcome=body.outcome, staff_id=staff.id
    )
    db.commit()
    return ok(result)


# ---- referrals (staff draft/send; patient approve/revoke) ------------------


class ReferralIn(BaseModel):
    request_id: uuid.UUID
    facility_id: uuid.UUID | None = None


@router.post("/referrals")
def create_referral(
    body: ReferralIn, db: DbDep, provider: ProviderDep, staff: ReferralsDep
) -> dict[str, Any]:
    result = referral.create_referral(
        db,
        provider,
        staff_id=staff.id,
        request_id=body.request_id,
        facility_id=body.facility_id,
    )
    db.commit()
    return ok(result)


@router.get("/referrals")
def list_referrals(db: DbDep, _staff: ReferralsDep) -> dict[str, Any]:
    return ok(referral.list_referrals(db))


@router.get("/referrals/{referral_id}/preview")
def preview(
    referral_id: uuid.UUID, db: DbDep, provider: ProviderDep, user: UserDep
) -> dict[str, Any]:
    return ok(referral.preview(db, provider, user=user, referral_id=referral_id))


class ApproveIn(BaseModel):
    approved_sections: list[str] = Field(min_length=1)


@router.post("/referrals/{referral_id}/approve")
def approve(
    referral_id: uuid.UUID, body: ApproveIn, db: DbDep, user: UserDep
) -> dict[str, Any]:
    result = referral.approve(
        db, user=user, referral_id=referral_id, approved_sections=body.approved_sections
    )
    db.commit()
    return ok(result)


@router.post("/referrals/{referral_id}/revoke")
def revoke(referral_id: uuid.UUID, db: DbDep, user: UserDep) -> dict[str, Any]:
    result = referral.revoke(db, user=user, referral_id=referral_id)
    db.commit()
    return ok(result)


@router.post("/referrals/{referral_id}/send")
def send(referral_id: uuid.UUID, db: DbDep, staff: ReferralsDep) -> dict[str, Any]:
    result = referral.mark_sent(db, staff_id=staff.id, referral_id=referral_id)
    db.commit()
    return ok(result)


@router.get("/referrals/{referral_id}/pdf")
def pdf(
    referral_id: uuid.UUID, db: DbDep, provider: ProviderDep, _staff: ReferralsDep
) -> Response:
    content = referral.letter_pdf(db, provider, referral_id=referral_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="referral.pdf"'},
    )


# ---- facilities -------------------------------------------------------------


@router.get("/facilities")
def list_facilities(
    db: DbDep,
    _staff: FacilitiesReadDep,
    county: str | None = None,
    level: str | None = None,
    language: str | None = None,
    screening: str | None = None,
) -> dict[str, Any]:
    return ok(
        facilities.list_facilities(
            db, county=county, level=level, language=language, screening=screening
        )
    )


class FacilityIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    county: str | None = Field(default=None, max_length=128)
    level: str | None = None
    catchment_counties: list[str] | None = None
    languages: list[str] | None = None
    services: list[str] | None = None
    screening_tests: list[str] | None = None
    opening_hours: list[dict[str, str]] | None = None
    estimated_cost_ksh_min: int | None = None
    estimated_cost_ksh_max: int | None = None
    cost_note: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


@router.post("/facilities")
def create_facility(body: FacilityIn, db: DbDep, staff: FacilitiesWriteDep) -> dict[str, Any]:
    result = facilities.create_facility(
        db, staff_id=staff.id, fields=body.model_dump(exclude_none=True)
    )
    db.commit()
    return ok(result)


@router.put("/facilities/{facility_id}")
def update_facility(
    facility_id: uuid.UUID, body: FacilityIn, db: DbDep, staff: FacilitiesWriteDep
) -> dict[str, Any]:
    result = facilities.update_facility(
        db, staff_id=staff.id, facility_id=facility_id, fields=body.model_dump(exclude_none=True)
    )
    db.commit()
    return ok(result)


@router.delete("/facilities/{facility_id}")
def delete_facility(facility_id: uuid.UUID, db: DbDep, staff: FacilitiesWriteDep) -> dict[str, Any]:
    facilities.delete_facility(db, staff_id=staff.id, facility_id=facility_id)
    db.commit()
    return ok({"deleted": str(facility_id)})


@router.post("/facilities/{facility_id}/verify")
def verify_facility(
    facility_id: uuid.UUID, db: DbDep, staff: FacilitiesWriteDep
) -> dict[str, Any]:
    result = facilities.verify_facility(db, staff_id=staff.id, facility_id=facility_id)
    db.commit()
    return ok(result)


# ---- surgery navigation ------------------------------------------------------


@router.get("/surgery/cases")
def list_cases(db: DbDep, _staff: SurgeryDep) -> dict[str, Any]:
    return ok(surgery.list_cases(db))


class CaseIn(BaseModel):
    user_id: uuid.UUID
    referral_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None


@router.post("/surgery/cases")
def create_case(body: CaseIn, db: DbDep, staff: SurgeryDep) -> dict[str, Any]:
    result = surgery.create_case(
        db,
        staff_id=staff.id,
        user_id=body.user_id,
        referral_id=body.referral_id,
        facility_id=body.facility_id,
    )
    db.commit()
    return ok(result)


class TransitionIn(BaseModel):
    to_status: str
    note: str | None = Field(default=None, max_length=500)


@router.post("/surgery/cases/{case_id}/transition")
def transition_case(
    case_id: uuid.UUID, body: TransitionIn, db: DbDep, staff: SurgeryDep
) -> dict[str, Any]:
    result = surgery.transition_case(
        db, staff_id=staff.id, case_id=case_id, to_status=body.to_status, note=body.note
    )
    db.commit()
    return ok(result)


class OutcomeIn(BaseModel):
    outcome_category: str
    note: str | None = Field(default=None, max_length=500)


@router.post("/surgery/cases/{case_id}/outcomes")
def add_outcome(
    case_id: uuid.UUID, body: OutcomeIn, db: DbDep, staff: SurgeryDep
) -> dict[str, Any]:
    result = surgery.add_outcome(
        db,
        staff_id=staff.id,
        case_id=case_id,
        outcome_category=body.outcome_category,
        note=body.note,
    )
    db.commit()
    return ok(result)


class PricingIn(BaseModel):
    procedure: str = Field(min_length=1, max_length=128)
    facility_id: uuid.UUID
    amount_ksh_min: int = Field(ge=0)
    amount_ksh_max: int = Field(ge=0)
    source: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=255)


@router.post("/surgery/pricing-stubs")
def add_pricing(body: PricingIn, db: DbDep, staff: SurgeryDep) -> dict[str, Any]:
    result = surgery.add_pricing_stub(
        db,
        staff_id=staff.id,
        procedure=body.procedure,
        facility_id=body.facility_id,
        amount_ksh_min=body.amount_ksh_min,
        amount_ksh_max=body.amount_ksh_max,
        source=body.source,
        note=body.note,
    )
    db.commit()
    return ok(result)


@router.get("/surgery/pricing-stubs")
def list_pricing(
    db: DbDep, _staff: SurgeryDep, facility_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return ok(surgery.list_pricing(db, facility_id=facility_id))


# ---- follow-up tracker -------------------------------------------------------


@router.get("/tracking")
def list_trackers(db: DbDep, _staff: TrackingDep, status: str | None = None) -> dict[str, Any]:
    return ok(tracking.list_trackers(db, status=status))


class TrackingIn(BaseModel):
    user_id: uuid.UUID
    facility_id: uuid.UUID | None = None


@router.post("/tracking")
def create_tracker(body: TrackingIn, db: DbDep, staff: TrackingDep) -> dict[str, Any]:
    result = tracking.create_tracker(
        db, user_id=body.user_id, facility_id=body.facility_id, staff_id=staff.id
    )
    db.commit()
    return ok(result)


@router.post("/tracking/{tracker_id}/transition")
def transition_tracker(
    tracker_id: uuid.UUID, body: TransitionIn, db: DbDep, staff: TrackingDep
) -> dict[str, Any]:
    result = tracking.transition_tracker(
        db,
        staff_id=staff.id,
        tracker_id=tracker_id,
        to_status=body.to_status,
    )
    db.commit()
    return ok(result)


@router.get("/tracking/me")
def my_trackers(db: DbDep, user: UserDep) -> dict[str, Any]:
    return ok(tracking.my_trackers(db, user))


class SharingIn(BaseModel):
    consent_to_share: bool


@router.post("/tracking/me/{tracker_id}/sharing")
def set_sharing(
    tracker_id: uuid.UUID, body: SharingIn, db: DbDep, user: UserDep
) -> dict[str, Any]:
    result = tracking.set_sharing(
        db, user, tracker_id=tracker_id, consent_to_share=body.consent_to_share
    )
    db.commit()
    return ok(result)


@router.get("/tracking/aggregates")
def tracker_aggregates(db: DbDep, _staff: AggregatesDep) -> dict[str, Any]:
    return ok(tracking.aggregates(db))


# ---- reminders ----------------------------------------------------------------


@router.post("/reminders/run")
def run_reminders(db: DbDep, provider: ProviderDep, _staff: RemindersDep) -> dict[str, Any]:
    sent: list[tuple[str, str]] = []

    def sms_send(phone: str, message: str) -> None:
        sent.append((phone, message))

    result = reminders.run_reminders(db, provider, sms_send, utc_now_naive())
    db.commit()
    return ok({"result": result, "sms_dispatched": len(sent)})


# ---- education content --------------------------------------------------------


@router.get("/education")
def education_list(
    db: DbDep,
    _staff: EducationDep,
    language: str | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    return ok(education.list_content(language=language, audience=audience))


@router.get("/education/patient")
def education_patient(
    db: DbDep, user: UserDep, language: str | None = None
) -> dict[str, Any]:
    return ok(education.list_content(language=language, audience="patient"))
