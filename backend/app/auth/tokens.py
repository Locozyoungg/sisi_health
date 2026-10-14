"""JWT access tokens + rotating refresh tokens with device binding. Refresh tokens
are single-use: reuse of a rotated token revokes the whole family."""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import Unauthorized
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import RefreshToken

ALGORITHM = "HS256"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "scope": "user",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def create_staff_access_token(staff_id: uuid.UUID, role: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(staff_id),
            "scope": "staff",
            "role": role,
            "iat": now,
            # Idle timeout (staff_idle_minutes) is enforced per-request against
            # last_active_at; the token itself expires after an hour at most.
            "exp": now + timedelta(minutes=60),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_token(raw: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(raw, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise Unauthorized("invalid or expired token") from exc
    return payload


def issue_refresh(
    db: Session, user_id: uuid.UUID, device_id: uuid.UUID, settings: Settings
) -> tuple[str, RefreshToken]:
    """Create a new refresh-token family head, bound to the device."""
    raw = uuid7().hex
    row = RefreshToken(
        id=uuid7(),
        user_id=user_id,
        family_id=uuid7(),
        token_hash=hash_token(raw),
        device_id=device_id,
        expires_at=utc_now_naive() + timedelta(days=settings.refresh_token_days),
    )
    db.add(row)
    db.flush()
    return raw, row


def rotate_refresh(db: Session, raw: str, settings: Settings) -> tuple[str, RefreshToken]:
    """Single-use rotation. Presenting an already-rotated token revokes the family."""
    token_hash = hash_token(raw)
    row = (
        db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        .scalars()
        .first()
    )
    if row is None:
        raise Unauthorized("unknown refresh token")
    now = utc_now_naive()
    if row.revoked_at is not None or row.expires_at < now:
        raise Unauthorized("refresh token revoked or expired")
    if row.rotated_at is not None:
        family = (
            db.execute(select(RefreshToken).where(RefreshToken.family_id == row.family_id))
            .scalars()
            .all()
        )
        for member in family:
            member.revoked_at = now
        db.flush()
        raise Unauthorized("refresh token reuse detected; family revoked")
    row.rotated_at = now
    new_raw = uuid7().hex
    new_row = RefreshToken(
        id=uuid7(),
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=hash_token(new_raw),
        device_id=row.device_id,
        expires_at=utc_now_naive() + timedelta(days=settings.refresh_token_days),
    )
    db.add(new_row)
    db.flush()
    return new_raw, new_row


def revoke_refresh(db: Session, raw: str) -> None:
    row = (
        db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
        .scalars()
        .first()
    )
    if row is not None:
        row.revoked_at = utc_now_naive()
        db.flush()
