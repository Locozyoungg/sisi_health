"""Consent lifecycle. Legal rules (spec 3.2, config-driven, never hard-coded):
- users under 13 are blocked at the age check (users service)
- users under SISI_SELF_CONSENT_AGE (default 18, assumption A1) need a guardian
  grant AND the minor's own assent, both recorded
- adults self-consent
- revocation deactivates every grant and triggers the erasure pipeline
Guardians NEVER read a minor's diary or answers; nothing here grants that."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.config import Settings
from app.consent.erasure import schedule_erasure
from app.core.errors import Conflict, NotFound, ValidationError
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import ConsentEvent, ConsentText, User

GRANT_TYPES = ("guardian_grant", "minor_assent", "self_grant")
METHODS = ("digital", "sms_link", "paper", "voice")


def ensure_consent_texts(db: Session) -> None:
    """Seed the versioned consent texts (idempotent)."""
    import hashlib

    from app.consent.texts import CONSENT_TEXTS

    existing = set(db.execute(select(ConsentText.key, ConsentText.language)).all())
    for spec in CONSENT_TEXTS:
        if (spec.key, spec.language) in existing:
            continue
        db.add(
            ConsentText(
                id=uuid7(),
                key=spec.key,
                version=1,
                language=spec.language,
                title=spec.title,
                body_text=spec.body,
                content_hash=hashlib.sha256(spec.body.encode("utf-8")).hexdigest(),
                active=True,
                created_at=utc_now_naive(),
            )
        )
    db.flush()


def _active_grants(db: Session, user_id: uuid.UUID) -> list[ConsentEvent]:
    return list(
        db.execute(
            select(ConsentEvent).where(
                ConsentEvent.user_id == user_id, ConsentEvent.active.is_(True)
            )
        ).scalars()
    )


def consent_state(db: Session, user: User, age: int | None) -> dict[str, Any]:
    """Current state: which grants are required and whether they are satisfied."""
    settings = Settings()  # cached singleton
    grants = {e.event_type for e in _active_grants(db, user.id) if e.event_type != "revoke"}
    if age is not None and age < settings.self_consent_age:
        required = ["guardian_grant", "minor_assent"]
    else:
        required = ["self_grant"]
    satisfied = all(r in grants for r in required)
    return {
        "age": age,
        "self_consent_age": settings.self_consent_age,
        "required": required,
        "held": sorted(grants),
        "satisfied": satisfied,
    }


def grant_consent(
    db: Session,
    user: User,
    *,
    event_type: str,
    method: str,
    age: int | None,
    recorded_by: uuid.UUID | None = None,
    evidence_ref: str | None = None,
) -> ConsentEvent:
    """Record one grant. Enforces the age rules and consent-text versioning."""
    settings = Settings()
    if event_type not in GRANT_TYPES:
        raise ValidationError("unknown consent grant type")
    if method not in METHODS:
        raise ValidationError("unknown consent capture method")
    if age is None:
        raise ValidationError("age required before consent")
    is_minor = age < settings.self_consent_age
    if event_type == "self_grant" and is_minor:
        raise Conflict(
            f"self-consent requires age {settings.self_consent_age}+; "
            "a guardian grant plus the minor's assent are required"
        )
    if event_type in ("guardian_grant", "minor_assent") and not is_minor:
        raise Conflict("guardian/assent grants apply only to minors")
    for existing in _active_grants(db, user.id):
        if existing.event_type == event_type:
            return existing  # idempotent: an active grant of this type already exists

    text = (
        db.execute(
            select(ConsentText)
            .where(ConsentText.key == _text_key(event_type), ConsentText.language == user.language)
            .order_by(ConsentText.version.desc())
        )
        .scalars()
        .first()
    )
    if text is None:
        raise NotFound("consent text missing; run ensure_consent_texts")

    event = ConsentEvent(
        id=uuid7(),
        user_id=user.id,
        event_type=event_type,
        text_id=text.id,
        method=method,
        recorded_by=recorded_by,
        evidence_ref=evidence_ref,
        active=True,
        captured_at=utc_now_naive(),
    )
    db.add(event)
    db.flush()
    record_event(
        db,
        event_type="consent_granted",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="consent_event",
        resource_id=event.id,
        payload={"grant_type": event_type, "method": method, "text_version": text.version},
    )
    return event


def _text_key(event_type: str) -> str:
    return {
        "guardian_grant": "guardian_consent",
        "minor_assent": "minor_assent",
        "self_grant": "self_consent",
    }[event_type]


def revoke_consent(db: Session, user: User) -> dict[str, Any]:
    """Withdraw consent: deactivate all grants, then schedule the erasure pipeline
    (spec 6: processing stops within 24 hours; erasure within the legal window)."""
    grants = _active_grants(db, user.id)
    for grant in grants:
        if grant.event_type == "revoke":
            continue
        grant.active = False
    if grants:
        db.add(
            ConsentEvent(
                id=uuid7(),
                user_id=user.id,
                event_type="revoke",
                text_id=None,
                method="digital",
                recorded_by=None,
                evidence_ref=None,
                active=True,
                captured_at=utc_now_naive(),
            )
        )
        db.flush()
        record_event(
            db,
            event_type="consent_revoked",
            actor_type="user",
            actor_id=user.id,
            actor_role=None,
            resource_type="user",
            resource_id=user.id,
            payload={"grants_deactivated": len(grants)},
        )
    job = schedule_erasure(db, user.id, requested_via="revocation")
    return {
        "revoked": len(grants),
        "erasure_job_id": str(job.id),
        "erasure_deadline": job.deadline_at,
    }


def effective_consent(db: Session, user: User, age: int | None) -> bool:
    """Raise-free check used before processing diary data."""
    return bool(consent_state(db, user, age)["satisfied"])


def require_consent(db: Session, user: User, age: int | None) -> None:
    if not effective_consent(db, user, age):
        raise Conflict("consent required before this action; see /users/me/consent")
