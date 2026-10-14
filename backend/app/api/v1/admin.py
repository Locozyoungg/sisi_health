"""Admin views: users (pseudonyms + status only, never medical data) and the DSR queue."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.envelope import ok
from app.auth.deps import require
from app.db import get_db
from app.models import DsrRequest, StaffUser, User
from app.users.service import public_view

router = APIRouter()


@router.get("/users")
def users(
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("admin:users"))],
    limit: int = 100,
    offset: int = 0,
) -> dict:
    limit = min(max(limit, 1), 500)
    rows = db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return ok([public_view(u) for u in rows])


@router.get("/dsr")
def dsr_queue(
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("admin:dsr"))],
) -> dict:
    rows = db.execute(
        select(DsrRequest).order_by(DsrRequest.submitted_at.desc())
    ).scalars().all()
    return ok(
        [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "type": r.type,
                "status": r.status,
                "deadline_at": r.deadline_at,
                "submitted_at": r.submitted_at,
            }
            for r in rows
        ]
    )
