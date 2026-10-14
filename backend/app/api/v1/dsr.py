"""Data-subject-rights endpoints: submit/track (user), process queue (admin)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import get_current_user, require
from app.config import Settings, get_settings
from app.db import get_db
from app.dsr.service import DsrPayload, get_request, process_request, submit_request
from app.models import StaffUser, User

router = APIRouter()


@router.post("/requests")
def submit(
    body: DsrPayload,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    row = submit_request(db, user, body, settings)
    db.commit()
    return ok(
        {
            "id": str(row.id),
            "type": row.type,
            "status": row.status,
            "deadline_at": row.deadline_at,
        }
    )


@router.get("/requests/{request_id}")
def track(
    request_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    row = get_request(db, user, request_id)
    return ok(
        {
            "id": str(row.id),
            "type": row.type,
            "status": row.status,
            "deadline_at": row.deadline_at,
            "submitted_at": row.submitted_at,
            "completed_at": row.completed_at,
        }
    )


@router.post("/requests/{request_id}/process")
def process(
    request_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: Annotated[StaffUser, Depends(require("dsr:process"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    from app.models import DsrRequest

    request = db.get(DsrRequest, request_id)
    if request is None:
        from app.core.errors import NotFound

        raise NotFound("request not found")
    result = process_request(db, provider, request, staff.id, settings)
    db.commit()
    return ok({"type": request.type, "result": result})
