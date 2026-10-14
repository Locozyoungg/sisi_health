"""Auth dependencies: current user (JWT scope user), current staff (scope staff,
RBAC permission, 15-minute idle timeout)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import tokens
from app.auth.rbac import PermissionDenied, has_permission
from app.config import get_settings
from app.core.errors import Unauthorized
from app.core.time import utc_now_naive
from app.db import get_db
from app.models import StaffUser, User

_bearer = HTTPBearer(auto_error=False)


def _credentials(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> HTTPAuthorizationCredentials:
    if creds is None:
        raise Unauthorized("missing bearer token")
    return creds


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_credentials)],
) -> User:
    payload = tokens.decode_token(creds.credentials, get_settings())
    if payload.get("scope") != "user":
        raise Unauthorized("wrong token scope")
    user = db.get(User, payload["sub"])
    if user is None or user.status != "active":
        raise Unauthorized("user not found or erased")
    return user


def get_current_staff(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_credentials)],
) -> StaffUser:
    settings = get_settings()
    payload = tokens.decode_token(creds.credentials, settings)
    if payload.get("scope") != "staff":
        raise Unauthorized("wrong token scope")
    staff = db.get(StaffUser, payload["sub"])
    if staff is None or staff.disabled:
        raise Unauthorized("staff account not found or disabled")
    if staff.last_active_at is None:
        raise Unauthorized("staff session expired")
    idle = utc_now_naive() - staff.last_active_at
    if idle > timedelta(minutes=settings.staff_idle_minutes):
        raise Unauthorized("staff session idle timeout; log in again")
    from app.auth.staff import touch_activity

    touch_activity(db, staff)
    return staff


def require(permission: str) -> Callable[..., StaffUser]:
    """Dependency factory: staff must hold the permission."""

    def _check(staff: Annotated[StaffUser, Depends(get_current_staff)]) -> StaffUser:
        if not has_permission(staff.role, permission):
            raise PermissionDenied(staff.role, permission)
        return staff
    return _check
