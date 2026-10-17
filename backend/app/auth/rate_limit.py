"""DB-backed sliding-window auth throttle (CC-6, Phase 8).

Mirrors the failure-counting semantics of `app/auth/otp.py` (window reset, lock
after N failures in the window, lockout expiry) but is keyed by an arbitrary
namespaced credential handle so any auth surface can share it:

    check_and_record(db, staff_login_key(email), max_attempts=..., ...)

Storage is `core.auth_throttle` (migration 0010). The key is a credential
handle — never a secret, and never copied into the audit trail (callers audit
counts only). The counter row must be committed by the caller: a failed login
raises, so an uncommitted session would roll the counter back and the throttle
would never bite (see `app/api/v1/staff_auth.py`).
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Locked, RateLimited
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import AuthThrottle

LOCKED_MESSAGE = "too many failed attempts; try again later"
RATE_LIMITED_MESSAGE = "too many attempts; try again later"


def staff_login_key(email: str) -> str:
    return f"staff_login:{email.strip().lower()}"


def staff_totp_setup_key(email: str) -> str:
    return f"staff_totp_setup:{email.strip().lower()}"


def _get_row(db: Session, key: str) -> AuthThrottle | None:
    return db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().first()


def is_locked(db: Session, key: str) -> bool:
    """True while the key is inside its lockout window."""
    row = _get_row(db, key)
    if row is None or row.locked_until is None:
        return False
    return row.locked_until > utc_now_naive()


def check_and_record(
    db: Session,
    key: str,
    *,
    max_attempts: int,
    window_minutes: int,
    lockout_minutes: int,
) -> None:
    """Record one failed attempt for `key` and raise when the budget is spent.

    - already locked -> `Locked` (the lock is never extended by a further attempt)
    - the window elapsed -> the count restarts at this attempt
    - the count reaches `max_attempts` -> lock for `lockout_minutes` and raise
      `Locked`; with no lockout configured (`lockout_minutes <= 0`) the limiter
      degrades to a per-window rate limit and raises `RateLimited` instead.
    """
    now = utc_now_naive()
    row = _get_row(db, key)
    if row is None:
        row = AuthThrottle(
            id=uuid7(), key=key, window_start=now, count=0, created_at=now, updated_at=now
        )
        db.add(row)
    elif row.locked_until is not None and row.locked_until > now:
        raise Locked(LOCKED_MESSAGE)

    if now - row.window_start > timedelta(minutes=window_minutes):
        row.window_start = now
        row.count = 0
    row.count += 1
    row.updated_at = now
    if row.count >= max_attempts:
        if lockout_minutes > 0:
            row.locked_until = now + timedelta(minutes=lockout_minutes)
            db.flush()
            raise Locked(LOCKED_MESSAGE)
        db.flush()
        raise RateLimited(RATE_LIMITED_MESSAGE)
    db.flush()


def clear(db: Session, key: str) -> None:
    """Reset the key (a successful authentication clears its failure history)."""
    row = _get_row(db, key)
    if row is not None:
        db.delete(row)
        db.flush()
