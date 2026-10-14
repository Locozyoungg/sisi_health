"""Consent endpoints: state, grants (guardian/assent/self), revocation."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import get_current_user
from app.consent import service as consent_service
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import get_db
from app.models import User
from app.users.service import age_of

router = APIRouter()


class GrantIn(BaseModel):
    event_type: str = Field(pattern=r"^(guardian_grant|minor_assent|self_grant)$")
    method: str = Field(pattern=r"^(digital|sms_link|paper|voice)$")
    evidence_ref: str | None = None


@router.get("/grants/state")
def state(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return ok(consent_service.consent_state(db, user, age_of(provider, db, user)))


@router.post("/grants")
def grant(
    body: GrantIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    event = consent_service.grant_consent(
        db,
        user,
        event_type=body.event_type,
        method=body.method,
        age=age_of(provider, db, user),
        evidence_ref=body.evidence_ref,
    )
    db.commit()
    return ok(
        {
            "grant_type": event.event_type,
            "captured_at": event.captured_at,
            "state": consent_service.consent_state(db, user, age_of(provider, db, user)),
        }
    )


@router.post("/revoke")
def revoke(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    result = consent_service.revoke_consent(db, user)
    db.commit()
    return ok(result)
