"""Audit endpoints: read (sanitized, admin only) and chain verification."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.envelope import ok
from app.audit.verifier import verify_chain
from app.auth.deps import require
from app.db import get_db
from app.models import AuditEvent, StaffUser

router = APIRouter()


@router.get("/events")
def events(
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("audit:read"))],
    limit: int = 100,
    offset: int = 0,
) -> dict:
    limit = min(max(limit, 1), 500)
    rows = db.execute(
        select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return ok(
        [
            {
                "seq": r.seq,
                "event_type": r.event_type,
                "actor_type": r.actor_type,
                "actor_role": r.actor_role,
                "resource_type": r.resource_type,
                "payload": r.payload,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    )


@router.post("/verify")
def verify(
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("audit:verify"))],
) -> dict:
    return ok(verify_chain(db))
