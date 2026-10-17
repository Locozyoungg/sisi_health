"""Staff auth: email + password + mandatory TOTP.

Both endpoints are brute-force throttled (CC-6, Phase 8) through the shared
`app/auth/rate_limit.py` limiter, keyed per lowercased email. A failed request
raises — and an uncommitted session rolls back — so the failure path commits the
throttle state explicitly before re-raising.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth import tokens
from app.auth.rate_limit import clear, is_locked, staff_totp_setup_key
from app.auth.staff import login_staff, record_throttle_failure, setup_totp, verify_staff_password
from app.config import get_settings
from app.core.errors import AppError, Locked, Unauthorized
from app.db import get_db
from app.models import StaffUser

router = APIRouter()


class StaffLoginIn(BaseModel):
    email: str
    password: str
    totp_code: str = Field(pattern=r"^\d{6}$")


class StaffTotpSetupIn(BaseModel):
    email: str
    password: str


@router.post("/totp/setup")
def totp_setup(
    body: StaffTotpSetupIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
) -> dict[str, Any]:
    """Provisional TOTP provisioning: email+password identify the staff member; the
    otpauth URI is returned exactly once."""
    settings = get_settings()
    throttle_key = staff_totp_setup_key(body.email)
    if is_locked(db, throttle_key):
        raise Locked("too many failed attempts; try again later")
    staff = (
        db.execute(select(StaffUser).where(StaffUser.email == body.email.strip().lower()))
        .scalars()
        .first()
    )
    if staff is None or staff.disabled or not verify_staff_password(staff, body.password):
        try:
            record_throttle_failure(
                db, throttle_key, settings, event_type="staff_totp_setup_locked"
            )
        finally:
            db.commit()  # the failure count / lock must survive the error response
        raise Unauthorized("invalid credentials")
    clear(db, throttle_key)
    uri = setup_totp(db, provider, staff)
    db.commit()
    return ok({"otpauth_uri": uri})


@router.post("/login")
def login(
    body: StaffLoginIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
) -> dict[str, Any]:
    try:
        staff = login_staff(
            db, provider, email=body.email, password=body.password, totp_code=body.totp_code
        )
    except AppError:
        # The failed-attempt counter (and any lockout) must survive this request:
        # the session is rolled back as the error propagates out of the endpoint.
        db.commit()
        raise
    settings = get_settings()
    access = tokens.create_staff_access_token(staff.id, staff.role, settings)
    db.commit()
    return ok({"access_token": access, "role": staff.role})
