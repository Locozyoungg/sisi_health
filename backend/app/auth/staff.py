"""Staff accounts: email + password (argon2id) + mandatory TOTP."""

import uuid

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unauthorized, ValidationError
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import StaffUser

_hasher = PasswordHasher()


def verify_staff_password(staff: StaffUser, password: str) -> bool:
    try:
        return _hasher.verify(staff.password_hash, password)
    except VerifyMismatchError:
        return False


def create_staff(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    email: str,
    password: str,
    role: str,
) -> StaffUser:
    email = email.strip().lower()
    if db.execute(select(StaffUser).where(StaffUser.email == email)).scalars().first():
        raise Conflict("email already registered")
    if len(password) < 12:
        raise ValidationError("staff password must be at least 12 characters")
    staff = StaffUser(
        id=uuid7(),
        email=email,
        password_hash=_hasher.hash(password),
        totp_secret_encrypted=None,
        totp_confirmed=False,
        role=role,
        created_at=utc_now_naive(),
    )
    db.add(staff)
    db.flush()
    return staff


def setup_totp(db: Session, provider: DatabaseKeyProvider, staff: StaffUser) -> str:
    """Issue the TOTP secret once; returns the otpauth URI."""
    if staff.totp_confirmed:
        raise Conflict("TOTP already confirmed")
    secret = pyotp.random_base32()
    blob, _key_id = _seal_totp(provider, db, staff.id, secret)
    staff.totp_secret_encrypted = blob
    db.flush()
    return pyotp.TOTP(secret).provisioning_uri(name=staff.email, issuer_name="SISI Health")


def _seal_totp(
    provider: DatabaseKeyProvider, db: Session, staff_id: uuid.UUID, secret: str
) -> tuple[bytes, uuid.UUID]:
    import json

    data_key = provider.get_or_create_data_key(db, "staff", staff_id)
    return provider.wrap(json.dumps({"totp": secret}).encode("utf-8")), data_key.id


def _open_totp(provider: DatabaseKeyProvider, db: Session, staff: StaffUser) -> str:
    import json
    from typing import Any, cast

    data_key = provider.get_data_key(db, "staff", staff.id)
    if data_key is None or staff.totp_secret_encrypted is None:
        raise Unauthorized("TOTP not provisioned")
    payload = cast(
        dict[str, Any], json.loads(provider.unwrap(staff.totp_secret_encrypted).decode("utf-8"))
    )
    return cast(str, payload["totp"])


def verify_totp(provider: DatabaseKeyProvider, db: Session, staff: StaffUser, code: str) -> bool:
    if not staff.totp_confirmed:
        # First successful check confirms the secret.
        secret = _open_totp(provider, db, staff)
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            staff.totp_confirmed = True
            db.flush()
            return True
        return False
    return pyotp.TOTP(_open_totp(provider, db, staff)).verify(code, valid_window=1)


def login_staff(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    email: str,
    password: str,
    totp_code: str,
) -> StaffUser:
    staff = (
        db.execute(select(StaffUser).where(StaffUser.email == email.strip().lower()))
        .scalars()
        .first()
    )
    if staff is None or staff.disabled:
        raise Unauthorized("invalid credentials")
    if not verify_staff_password(staff, password):
        raise Unauthorized("invalid credentials")
    if not verify_totp(provider, db, staff, totp_code):
        # First successful check confirms the secret; failure stays generic.
        raise Unauthorized("invalid TOTP code")
    staff.last_active_at = utc_now_naive()
    db.flush()
    return staff


def touch_activity(db: Session, staff: StaffUser) -> None:
    staff.last_active_at = utc_now_naive()
    db.flush()
