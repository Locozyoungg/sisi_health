"""Staff auth: email + password + mandatory TOTP."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth import tokens
from app.auth.staff import login_staff, setup_totp
from app.config import get_settings
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import get_db

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
) -> dict:
    """Provisional TOTP provisioning: email+password identify the staff member; the
    otpauth URI is returned exactly once."""
    from app.auth.staff import _hasher  # noqa: PLC2701

    from sqlalchemy import select

    from app.models import StaffUser

    staff = db.execute(
        select(StaffUser).where(StaffUser.email == body.email.strip().lower())
    ).scalars().first()
    if staff is None or staff.disabled:
        from app.core.errors import Unauthorized

        raise Unauthorized("invalid credentials")
    try:
        _hasher.verify(staff.password_hash, body.password)
    except Exception as exc:  # noqa: BLE001
        from app.core.errors import Unauthorized

        raise Unauthorized("invalid credentials") from exc
    uri = setup_totp(db, provider, staff)
    db.commit()
    return ok({"otpauth_uri": uri})


@router.post("/login")
def login(
    body: StaffLoginIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
) -> dict:
    staff = login_staff(
        db, provider, email=body.email, password=body.password, totp_code=body.totp_code
    )
    settings = get_settings()
    access = tokens.create_staff_access_token(staff.id, staff.role, settings)
    db.commit()
    return ok({"access_token": access, "role": staff.role})
