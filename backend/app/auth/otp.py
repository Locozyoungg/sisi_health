"""Phone OTP with rate limiting and brute-force lockout. In dev/demo the code is
returned in the response (assumption A5) because no SMS credentials exist yet;
staging/prod refuse to boot with that flag on."""

import hashlib
import hmac
import secrets
import string
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import Locked, RateLimited, Unauthorized, ValidationError
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import OtpRequest

REQUEST_WINDOW_MINUTES = 10
LOCKOUT_MINUTES = 15


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not (10 <= len(digits) <= 15):
        raise ValidationError("invalid phone number")
    return "+" + digits


def phone_hash(phone: str, settings: Settings) -> str:
    return hmac.new(settings.phone_pepper.encode(), phone.encode(), hashlib.sha256).hexdigest()


def _code_hash(code: str, settings: Settings) -> str:
    return hmac.new(settings.phone_pepper.encode(), code.encode(), hashlib.sha256).hexdigest()


def request_otp(db: Session, phone: str, settings: Settings) -> str | None:
    """Rate-limit per phone hash, then issue a 6-digit code (TTL: otp_ttl_seconds).
    Returns the code when dev-return is on, else None (SMS would carry it)."""
    now = utc_now_naive()
    ph = phone_hash(phone, settings)
    row = db.execute(select(OtpRequest).where(OtpRequest.phone_hash == ph)).scalars().first()
    if row is None:
        row = OtpRequest(id=uuid7(), phone_hash=ph, attempts=0, window_start=now)
        db.add(row)
    if row.locked_until and row.locked_until > now:
        raise Locked("too many failed attempts; try again later")
    window = timedelta(minutes=REQUEST_WINDOW_MINUTES)
    if row.window_start and now - row.window_start > window:
        row.request_count = 0
        row.window_start = now
    if row.request_count >= settings.otp_max_requests_per_window:
        raise RateLimited("too many OTP requests; wait and try again")
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    row.code_hash = _code_hash(code, settings)
    row.attempts = 0
    row.expires_at = now + timedelta(seconds=settings.otp_ttl_seconds)
    row.request_count += 1
    row.last_request_at = now
    db.flush()
    if settings.otp_dev_return and settings.env in {"dev", "demo"}:
        return code
    return None


def verify_otp(db: Session, phone: str, code: str, settings: Settings) -> None:
    """Constant-time verify with attempt counting and lockout."""
    now = utc_now_naive()
    ph = phone_hash(phone, settings)
    row = db.execute(select(OtpRequest).where(OtpRequest.phone_hash == ph)).scalars().first()
    if row is None or row.code_hash is None:
        raise Unauthorized("no OTP requested for this number")
    if row.locked_until and row.locked_until > now:
        raise Locked("too many failed attempts; try again later")
    if row.expires_at is None or row.expires_at < now:
        raise Unauthorized("OTP expired; request a new one")
    if not hmac.compare_digest(row.code_hash, _code_hash(code, settings)):
        row.attempts += 1
        if row.attempts >= settings.otp_max_failures:
            row.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        db.flush()
        raise Unauthorized("incorrect code")
    row.code_hash = None
    row.attempts = 0
    row.expires_at = None
    db.flush()


def device_key_hash(device_id: uuid.UUID, settings: Settings) -> str:
    return hmac.new(
        settings.phone_pepper.encode(), str(device_id).encode(), hashlib.sha256
    ).hexdigest()
