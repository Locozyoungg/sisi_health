"""Corridor consult service (spec 5.4): patient-initiated booking, nurse review
queue, gynecologist telehealth sessions (Jitsi, JWT-gated, one-time, unrecorded),
and minor consent/chaperone guards. Corridor views decrypt ONLY the computed
features snapshot — raw diary ciphertext is never opened here (non-negotiable 5)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event, sanitize_payload
from app.config import get_settings
from app.core.errors import Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.envelope import open_json, seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.diary.service import compute_features
from app.models import (
    ConsultConsent,
    ConsultEvent,
    ConsultRequest,
    ConsultSession,
    User,
)
from app.rules.engine import RuleEngine
from app.rules.schemas import Evaluation
from app.users.service import age_of

CONSULT_TRANSITIONS: dict[str, set[str]] = {
    "pending_nurse_review": {"approved", "declined"},
    "approved": {"scheduled", "cancelled"},
    "scheduled": {"completed", "missed", "cancelled"},
}
SESSION_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "no_show", "cancelled"},
}
CONSENT_KINDS = {"guardian_consent", "minor_assent", "chaperone_requested", "chaperone_confirmed"}
CONSENT_METHODS = {"digital", "sms_link", "paper", "voice"}


def _transition(db: Session, row: ConsultRequest, to_status: str, actor: dict[str, Any]) -> None:
    allowed = CONSULT_TRANSITIONS.get(row.status, set())
    if to_status not in allowed:
        raise Conflict(f"cannot move a consult request from {row.status} to {to_status}")
    from_status = row.status
    row.status = to_status
    row.updated_at = utc_now_naive()
    db.add(
        ConsultEvent(
            id=uuid7(),
            request_id=row.id,
            event_type="status_changed",
            status_from=from_status,
            status_to=to_status,
            actor_type=actor["type"],
            actor_id=actor["id"],
        )
    )


def book_request(
    db: Session,
    provider: DatabaseKeyProvider,
    user: User,
    engine: RuleEngine,
    *,
    preferred_county: str | None,
    preferred_language: str,
    patient_note: str | None,
    chaperone_requested: bool,
    consent_satisfied: bool,
) -> dict[str, Any]:
    """Patient-initiated consult request (user JWT). Booking requires active
    consent (D9) and a computed features snapshot sealed per request (D5)."""
    if not consent_satisfied:
        raise Conflict("active consent is required before booking a consult")
    age = age_of(provider, db, user)
    if age is None:
        raise Conflict("age is required before booking a consult")
    features, diary_days = compute_features(db, provider, user)
    evaluation: Evaluation = engine.evaluate(age=age, diary_days=diary_days, features=features)
    # Seal the snapshot BEFORE the request row exists: seal_json flushes, and
    # features_ciphertext is NOT NULL — the row must carry its ciphertext from
    # the first flush (the id is client-generated, so the key can be created
    # against it up front).
    request_id = uuid7()
    blob, key_id = seal_json(provider, db, "corridor", request_id, features)
    note_blob = note_key_id = None
    if patient_note:
        note_blob, note_key_id = seal_json(
            provider, db, "corridor", request_id, {"note": patient_note}
        )
    row = ConsultRequest(
        id=request_id,
        user_id=user.id,
        band=evaluation.band,
        urgent=evaluation.urgent,
        safeguarding=evaluation.safeguarding,
        indicators=evaluation.indicators,
        features_ciphertext=blob,
        features_key_id=key_id,
        patient_note_ciphertext=note_blob,
        patient_note_key_id=note_key_id,
        preferred_county=preferred_county,
        preferred_language=preferred_language or "en",
        chaperone_requested=chaperone_requested,
    )
    db.add(row)
    db.flush()
    db.add(
        ConsultEvent(
            id=uuid7(),
            request_id=row.id,
            event_type="requested",
            status_to=row.status,
            actor_type="user",
            actor_id=user.id,
        )
    )
    record_event(
        db,
        event_type="consult_requested",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="consult_request",
        resource_id=row.id,
        payload={"band": evaluation.band, "safeguarding": evaluation.safeguarding},
    )
    return {
        "id": str(row.id),
        "status": row.status,
        "band": evaluation.band,
        "urgent": evaluation.urgent,
        "safeguarding": evaluation.safeguarding,
    }


def my_requests(db: Session, user: User) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(ConsultRequest)
            .where(ConsultRequest.user_id == user.id)
            .order_by(ConsultRequest.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(r.id), "status": r.status, "band": r.band, "created_at": r.created_at}
        for r in rows
    ]


def _age_band(age: int | None, settings_self_consent_age: int) -> str:
    if age is None:
        return "unknown"
    return "13-17" if age < settings_self_consent_age else "18+"


def queue(
    db: Session, provider: DatabaseKeyProvider, limit: int = 50
) -> list[dict[str, Any]]:
    """Nurse/gynecologist review queue: pseudonym, bands, flags, consent state,
    chaperone request — never answers, never raw symptom values."""
    settings = get_settings()
    rows = (
        db.execute(
            select(ConsultRequest).order_by(ConsultRequest.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        user = db.get(User, r.user_id)
        age = age_of(provider, db, user) if user else None
        out.append(
            {
                "request_id": str(r.id),
                "pseudonym": str(r.user_id)[:8],
                "band": r.band,
                "urgent": r.urgent,
                "safeguarding": r.safeguarding,
                "age_band": _age_band(age, settings.self_consent_age),
                "status": r.status,
                "chaperone_requested": r.chaperone_requested,
                "preferred_language": r.preferred_language,
                "created_at": r.created_at,
            }
        )
    return out


def detail(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    request_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict[str, Any]:
    """Case view: band + indicators + decrypted features snapshot (trends only,
    D5). Every view is audited."""
    row = db.get(ConsultRequest, request_id)
    if row is None:
        raise NotFound("consult request not found")
    features = open_json(provider, db, row.features_ciphertext, row.features_key_id)
    user = db.get(User, row.user_id)
    age = age_of(provider, db, user) if user else None
    consents = [
        {"kind": c.kind, "method": c.method, "captured_at": c.captured_at}
        for c in db.execute(
            select(ConsultConsent).where(ConsultConsent.request_id == row.id)
        ).scalars()
    ]
    record_event(
        db,
        event_type="corridor_case_viewed",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_request",
        resource_id=row.id,
        payload={"band": row.band},
    )
    return {
        "request_id": str(row.id),
        "pseudonym": str(row.user_id)[:8],
        "age_band": _age_band(age, get_settings().self_consent_age),
        "status": row.status,
        "band": row.band,
        "indicators": row.indicators,
        "urgent": row.urgent,
        "safeguarding": row.safeguarding,
        "features": features,  # computed feature aggregates only, never raw diary
        "consents": consents,
        "chaperone_requested": row.chaperone_requested,
        "preferred_county": row.preferred_county,
        "preferred_language": row.preferred_language,
    }


def _require_minor_consents(
    db: Session, provider: DatabaseKeyProvider, row: ConsultRequest
) -> None:
    """Minors' consults require recorded guardian consent + assent (spec 5.4)."""
    user = db.get(User, row.user_id)
    if user is None:
        raise NotFound("user not found")
    age = age_of(provider, db, user)
    if age is None or age >= get_settings().self_consent_age:
        return
    kinds = {
        c.kind
        for c in db.execute(
            select(ConsultConsent).where(ConsultConsent.request_id == row.id)
        ).scalars()
    }
    missing = {"guardian_consent", "minor_assent"} - kinds
    if missing:
        raise Conflict(f"minor consult requires recorded consent: {sorted(missing)}")


def review(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    request_id: uuid.UUID,
    staff_id: uuid.UUID,
    decision: str,
    note: str | None,
) -> dict[str, Any]:
    row = db.get(ConsultRequest, request_id)
    if row is None:
        raise NotFound("consult request not found")
    if decision not in {"approved", "declined"}:
        raise Conflict("decision must be approved or declined")
    if decision == "approved":
        _require_minor_consents(db, provider, row)
    _transition(db, row, decision, {"type": "staff", "id": staff_id})
    record_event(
        db,
        event_type="consult_reviewed",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_request",
        resource_id=row.id,
        payload={
            "decision": decision,
            "note": sanitize_payload({"note": note or ""})["note"] or None,
        },
    )
    return {"request_id": str(row.id), "status": row.status}


def schedule(
    db: Session,
    *,
    request_id: uuid.UUID,
    gynecologist_id: uuid.UUID,
    scheduled_at: datetime,
    modality: str,
    staff_id: uuid.UUID,
) -> dict[str, Any]:
    row = db.get(ConsultRequest, request_id)
    if row is None:
        raise NotFound("consult request not found")
    if modality not in {"video", "audio"}:
        raise Conflict("modality must be video or audio")
    session = ConsultSession(
        id=uuid7(),
        request_id=row.id,
        gynecologist_id=gynecologist_id,
        modality=modality,
        scheduled_at=scheduled_at,
        room_name=uuid7().hex,  # one-time room, never reused
    )
    db.add(session)
    _transition(db, row, "scheduled", {"type": "staff", "id": staff_id})
    db.flush()
    record_event(
        db,
        event_type="consult_scheduled",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_session",
        resource_id=session.id,
        payload={"modality": modality},
    )
    return {"session_id": str(session.id), "room_name": session.room_name, "status": row.status}


def record_consent(
    db: Session,
    *,
    request_id: uuid.UUID,
    kind: str,
    method: str,
    evidence_ref: str | None,
    staff_id: uuid.UUID,
) -> dict[str, Any]:
    if kind not in CONSENT_KINDS:
        raise Conflict(f"unknown consent kind: {kind}")
    if method not in CONSENT_METHODS:
        raise Conflict(f"unknown consent method: {method}")
    if db.get(ConsultRequest, request_id) is None:
        raise NotFound("consult request not found")
    row = ConsultConsent(
        id=uuid7(),
        request_id=request_id,
        kind=kind,
        method=method,
        recorded_by=staff_id,
        text_version=1,
        evidence_ref=evidence_ref,
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="consult_consent_recorded",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_consent",
        resource_id=row.id,
        payload={"kind": kind, "method": method},
    )
    return {"id": str(row.id), "kind": row.kind}


def _require_chaperone(db: Session, provider: DatabaseKeyProvider, session: ConsultSession) -> None:
    request = db.get(ConsultRequest, session.request_id)
    if request is None:
        raise NotFound("consult request not found")
    user = db.get(User, request.user_id)
    if user is None:
        raise NotFound("user not found")
    age = age_of(provider, db, user)
    is_minor = age is not None and age < get_settings().self_consent_age
    if is_minor and request.chaperone_requested:
        kinds = {
            c.kind
            for c in db.execute(
                select(ConsultConsent).where(ConsultConsent.request_id == request.id)
            ).scalars()
        }
        if "chaperone_confirmed" not in kinds:
            raise Conflict("chaperone must be confirmed before starting this session")


def start_session(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    session_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict[str, Any]:
    """scheduled -> in_progress; issues the one-time JWT-gated Jitsi room token
    (contract-level: self-hosting/account provisioning is a human task)."""
    session = db.get(ConsultSession, session_id)
    if session is None:
        raise NotFound("consult session not found")
    if session.status != "scheduled":
        raise Conflict("session already started or closed")
    _require_chaperone(db, provider, session)
    session.status = "in_progress"
    session.started_at = utc_now_naive()
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "aud": settings.jitsi_app_id,
            "iss": settings.jitsi_app_id,
            "sub": "*",
            "room": session.room_name,
            "iat": now,
            "exp": now + timedelta(hours=2),
            "features": {"recording": False, "livestreaming": False},
        },
        settings.jitsi_app_secret,
        algorithm="HS256",
    )
    record_event(
        db,
        event_type="consult_started",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_session",
        resource_id=session.id,
        payload={"room": session.room_name},
    )
    return {
        "session_id": str(session.id),
        "room": session.room_name,
        "domain": settings.jitsi_domain,
        "token": token,
        "join_url": f"https://{settings.jitsi_domain}/{session.room_name}?jwt={token}",
    }


def complete_session(
    db: Session,
    *,
    session_id: uuid.UUID,
    outcome: str,
    staff_id: uuid.UUID,
) -> dict[str, Any]:
    session = db.get(ConsultSession, session_id)
    if session is None:
        raise NotFound("consult session not found")
    if outcome not in {"completed", "no_show"}:
        raise Conflict("outcome must be completed or no_show")
    if session.status != "in_progress":
        raise Conflict("session is not in progress")
    session.status = outcome
    session.completed_at = utc_now_naive()
    request = db.get(ConsultRequest, session.request_id)
    if request is None:
        raise NotFound("consult request not found")
    _transition(
        db,
        request,
        "completed" if outcome == "completed" else "missed",
        {"type": "staff", "id": staff_id},
    )
    record_event(
        db,
        event_type="consult_completed",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="consult_session",
        resource_id=session.id,
        payload={"outcome": outcome},
    )
    return {"session_id": str(session.id), "status": session.status}
