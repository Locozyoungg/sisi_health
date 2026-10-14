"""User auth: OTP request/verify, token rotation, device management."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth import tokens
from app.auth.deps import get_current_user
from app.auth.otp import device_key_hash, normalize_phone, request_otp, verify_otp
from app.config import get_settings
from app.core.errors import NotFound, Unauthorized
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.db import get_db
from app.models import Device, User
from app.users.service import create_user, get_by_phone

router = APIRouter()


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=10, max_length=16)


class OtpVerifyIn(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    code: str = Field(pattern=r"^\d{6}$")
    device_id: uuid.UUID
    birth_date: str | None = None  # ISO date, required at first registration
    language: str = "en"


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/otp/request")
def otp_request(body: OtpRequestIn, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    phone = normalize_phone(body.phone)
    code = request_otp(db, phone, get_settings())
    data: dict[str, Any] = {"status": "sent"}
    if code is not None:
        data["dev_otp"] = code  # dev/demo only (settings guard; never in staging/prod)
    return ok(data)


@router.post("/otp/verify")
def otp_verify(
    body: OtpVerifyIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
) -> dict[str, Any]:
    settings = get_settings()
    phone = normalize_phone(body.phone)
    verify_otp(db, phone, body.code, settings)
    user = get_by_phone(db, phone, settings)
    if user is None:
        if body.birth_date is None:
            raise Unauthorized("new account: birth_date required")
        from datetime import date

        user = create_user(
            db,
            provider,
            phone=phone,
            birth_date=date.fromisoformat(body.birth_date),
            language=body.language,
            settings=settings,
        )
    db.commit()
    device = (
        db.execute(
            select(Device).where(
                Device.device_key_hash == device_key_hash(body.device_id, settings)
            )
        )
        .scalars()
        .first()
    )
    if device is None:
        device = Device(
            id=uuid7(), user_id=user.id, device_key_hash=device_key_hash(body.device_id, settings)
        )
        db.add(device)
        db.flush()
    access = tokens.create_access_token(user.id, settings)
    refresh_raw, _ = tokens.issue_refresh(db, user.id, device.id, settings)
    db.commit()
    return ok({"access_token": access, "refresh_token": refresh_raw, "user_id": str(user.id)})


@router.post("/refresh")
def refresh(body: RefreshIn, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    settings = get_settings()
    new_raw, row = tokens.rotate_refresh(db, body.refresh_token, settings)
    access = tokens.create_access_token(row.user_id, settings)
    db.commit()
    return ok({"access_token": access, "refresh_token": new_raw})


@router.post("/logout")
def logout(
    body: RefreshIn,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    tokens.revoke_refresh(db, body.refresh_token)
    db.commit()
    return ok({"revoked": True})


@router.get("/devices")
def list_devices(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    devices = db.execute(select(Device).where(Device.user_id == user.id)).scalars().all()
    return ok(
        [
            {
                "id": str(d.id),
                "created_at": d.created_at,
                "revoked": d.revoked_at is not None,
            }
            for d in devices
        ]
    )


@router.delete("/devices/{device_id}")
def revoke_device(
    device_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise NotFound("device not found")
    device.revoked_at = utc_now_naive()
    db.commit()
    return ok({"revoked": True})
