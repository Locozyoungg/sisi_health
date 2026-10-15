"""Referral letters (spec 5.4): auto-generated from the diary summary + triage
output, shown to the patient BEFORE sending, containing only what she approves.
She can revoke sharing at any time. PDF export renders approved sections only."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.errors import Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.envelope import open_json, seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import (
    ConsultRequest,
    Facility,
    Referral,
    SharingApproval,
    User,
)
from app.rules.bands import BAND_LABELS_EN
from app.users.service import age_of

SECTIONS = (
    "diary_summary",
    "triage_summary",
    "recommendations",
    "facility_details",
    "personal_details",
)
DISCLAIMER = "SISI supports you and your doctor — it does not diagnose."

# Display labels for condition indicators (never diagnoses — non-negotiable 1).
INDICATOR_LABELS = {
    "anemia-risk-flag": "possible anaemia risk",
    "endo-indicator": "possible endometriosis pattern",
    "endo-indicator-adult": "possible endometriosis pattern",
    "fibroid-indicator": "possible fibroid pattern",
    "pcos-indicator": "possible PCOS pattern",
    "redflag-heavy-bleeding-dizziness": "heavy bleeding with dizziness",
    "redflag-severe-acute-pain": "severe acute pain",
    "redflag-self-harm": "self-harm signal",
    "redflag-postcoital-bleeding": "bleeding after sex",
    "redflag-intermenstrual-bleeding": "bleeding between periods",
    "redflag-postmenopausal-bleeding": "bleeding after menopause",
    "redflag-persistent-discharge": "persistent unusual discharge",
}


def _section_content(
    request: ConsultRequest,
    features: dict[str, Any],
    age: int | None,
    facility: Facility | None,
) -> dict[str, list[dict[str, str]]]:
    band_label = BAND_LABELS_EN.get(request.band, request.band)
    triage = {
        "key": "triage_summary",
        "title": "Health check summary",
        "body": (
            f"Band: {request.band} ({band_label}). "
            + (
                "Patterns suggested: "
                + "; ".join(INDICATOR_LABELS.get(i, i) for i in request.indicators)
                + ". "
                if request.indicators
                else ""
            )
            + DISCLAIMER
        ),
    }
    diary = {
        "key": "diary_summary",
        "title": "Diary summary (90 days)",
        "body": (
            f"Max pain: {features.get('max_pain_90d')} / 10. "
            f"Average bleeding volume: {features.get('avg_bleeding_volume_90d')} / 4. "
            f"Fatigue ratio (30 days): {features.get('fatigue_ratio_30d')}. "
            f"Cycle irregularity score: {features.get('cycle_irregularity_90d')}."
        ),
    }
    recommendations = {
        "key": "recommendations",
        "title": "Recommended next step",
        "body": f"Next step per the assessment band: {band_label}. {DISCLAIMER}",
    }
    if facility is None:
        facility_body = "No facility selected yet."
    else:
        cost = (
            f"Estimated consultation cost (indicative, please confirm): "
            f"KES {facility.estimated_cost_ksh_min}-{facility.estimated_cost_ksh_max}."
            if facility.estimated_cost_ksh_min is not None
            else "Estimated costs not listed — please confirm with the facility."
        )
        facility_body = (
            f"{facility.name}, {facility.county} (level: {facility.level}). "
            f"Screening tests offered: "
            f"{', '.join(facility.screening_tests or []) or 'not listed'}. "
            f"{cost}"
        )
    facility_detail = {"key": "facility_details", "title": "Facility", "body": facility_body}
    personal = {
        "key": "personal_details",
        "title": "Personal details",
        "body": (
            f"Patient reference: {str(request.user_id)}. Age: {age}. "
            f"Preferred language: {request.preferred_language}."
        ),
    }
    return {"sections": [diary, triage, recommendations, facility_detail, personal]}


def _decrypt_letter(
    db: Session, provider: DatabaseKeyProvider, referral: Referral
) -> dict[str, Any]:
    if referral.letter_ciphertext is None or referral.letter_key_id is None:
        raise Conflict("referral letter not generated yet")
    return open_json(provider, db, referral.letter_ciphertext, referral.letter_key_id)


def create_referral(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    staff_id: uuid.UUID,
    request_id: uuid.UUID,
    facility_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Draft the letter from the request's features snapshot + triage output."""
    request = db.get(ConsultRequest, request_id)
    if request is None:
        raise NotFound("consult request not found")
    facility = db.get(Facility, facility_id) if facility_id else None
    if facility_id and facility is None:
        raise NotFound("facility not found")
    user = db.get(User, request.user_id)
    age = age_of(provider, db, user) if user else None
    features = open_json(provider, db, request.features_ciphertext, request.features_key_id)
    content = _section_content(request, features, age, facility)
    referral = Referral(
        id=uuid7(),
        user_id=request.user_id,
        consult_request_id=request.id,
        facility_id=facility_id,
        status="awaiting_approval",
        sections=[s["key"] for s in content["sections"]],
        created_by=staff_id,
    )
    db.add(referral)
    db.flush()
    blob, key_id = seal_json(provider, db, "corridor", referral.id, content)
    referral.letter_ciphertext = blob
    referral.letter_key_id = key_id
    record_event(
        db,
        event_type="referral_drafted",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="referral",
        resource_id=referral.id,
        payload={"sections": referral.sections},
    )
    return {"id": str(referral.id), "status": referral.status, "sections": referral.sections}


def list_referrals(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "status": r.status,
            "sections": r.sections,
            "approved_sections": r.approved_sections,
            "created_at": r.created_at,
        }
        for r in db.execute(select(Referral).order_by(Referral.created_at.desc())).scalars()
    ]


def preview(
    db: Session, provider: DatabaseKeyProvider, *, user: User, referral_id: uuid.UUID
) -> dict[str, Any]:
    """The patient sees the FULL letter content before approving (spec 5.4)."""
    referral = db.get(Referral, referral_id)
    if referral is None or referral.user_id != user.id:
        raise NotFound("referral not found")
    return _decrypt_letter(db, provider, referral)


def approve(
    db: Session,
    *,
    user: User,
    referral_id: uuid.UUID,
    approved_sections: list[str],
) -> dict[str, Any]:
    referral = db.get(Referral, referral_id)
    if referral is None or referral.user_id != user.id:
        raise NotFound("referral not found")
    if referral.status != "awaiting_approval":
        raise Conflict(f"referral is {referral.status}, not awaiting approval")
    unknown = set(approved_sections) - set(referral.sections)
    if unknown:
        raise Conflict(f"unknown sections: {sorted(unknown)}")
    if not approved_sections:
        raise Conflict("at least one section must be approved")
    referral.approved_sections = approved_sections
    referral.status = "approved"
    referral.approved_at = utc_now_naive()
    referral.updated_at = utc_now_naive()
    db.add(
        SharingApproval(
            id=uuid7(),
            user_id=user.id,
            resource_type="referral",
            resource_id=referral.id,
            action="approved",
        )
    )
    db.flush()
    record_event(
        db,
        event_type="referral_approved",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="referral",
        resource_id=referral.id,
        payload={"approved_sections": approved_sections},
    )
    return {
        "id": str(referral.id),
        "status": referral.status,
        "approved_sections": approved_sections,
    }


def revoke(db: Session, *, user: User, referral_id: uuid.UUID) -> dict[str, Any]:
    """The patient can revoke sharing at any time (spec 5.4)."""
    referral = db.get(Referral, referral_id)
    if referral is None or referral.user_id != user.id:
        raise NotFound("referral not found")
    if referral.status in {"revoked", "draft"}:
        raise Conflict("referral already revoked")
    referral.status = "revoked"
    referral.revoked_at = utc_now_naive()
    referral.updated_at = utc_now_naive()
    db.add(
        SharingApproval(
            id=uuid7(),
            user_id=user.id,
            resource_type="referral",
            resource_id=referral.id,
            action="revoked",
        )
    )
    db.flush()
    record_event(
        db,
        event_type="referral_revoked",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="referral",
        resource_id=referral.id,
        payload={},
    )
    return {"id": str(referral.id), "status": referral.status}


def mark_sent(db: Session, *, staff_id: uuid.UUID, referral_id: uuid.UUID) -> dict[str, Any]:
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise NotFound("referral not found")
    if referral.status != "approved":
        raise Conflict("only an approved referral can be sent")
    referral.status = "sent"
    referral.sent_at = utc_now_naive()
    referral.updated_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="referral_sent",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="referral",
        resource_id=referral.id,
        payload={},
    )
    return {"id": str(referral.id), "status": referral.status}


def letter_pdf(
    db: Session, provider: DatabaseKeyProvider, *, referral_id: uuid.UUID
) -> bytes:
    """PDF of the APPROVED sections only (reportlab). 409 unless approved."""
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise NotFound("referral not found")
    if referral.status not in {"approved", "sent"}:
        raise Conflict("referral letter is not approved by the patient")
    content = _decrypt_letter(db, provider, referral)
    approved_keys = set(referral.approved_sections)

    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    styles = getSampleStyleSheet()
    story: list[Any] = [Paragraph("SISI Health — Referral Letter", styles["Title"]), Spacer(1, 12)]
    for section in content["sections"]:
        if section["key"] not in approved_keys:
            continue
        story.append(Paragraph(section["title"], styles["Heading2"]))
        story.append(Paragraph(section["body"], styles["BodyText"]))
        story.append(Spacer(1, 8))
    story.append(Paragraph(DISCLAIMER, styles["Italic"]))
    doc.build(story)
    return buffer.getvalue()
