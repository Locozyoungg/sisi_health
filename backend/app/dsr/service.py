"""Data-subject-rights requests (Kenya DPA 2019, spec 6): access, correction,
portability, erasure, objection — each tracked with a deadline."""

import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.config import Settings
from app.consent.erasure import run_erasure
from app.core.errors import Conflict, NotFound, ValidationError
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.key_provider import DatabaseKeyProvider
from app.diary.service import get_entries
from app.models import DsrRequest, User

TYPES = ("access", "correction", "portability", "erasure", "objection")


class DsrPayload(BaseModel):
    type: str
    payload: dict[str, Any] | None = None


def submit_request(db: Session, user: User, req: DsrPayload, settings: Settings) -> DsrRequest:
    if req.type not in TYPES:
        raise ValidationError("unknown DSR type")
    row = DsrRequest(
        id=uuid7(),
        user_id=user.id,
        type=req.type,
        status="open",
        payload=req.payload,
        deadline_at=utc_now_naive() + timedelta(days=settings.dsr_deadline_days),
        submitted_at=utc_now_naive(),
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="dsr_submitted",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="dsr_request",
        resource_id=row.id,
        payload={"type": req.type, "deadline": row.deadline_at.isoformat()},
    )
    return row


def get_request(db: Session, user: User, request_id: uuid.UUID) -> DsrRequest:
    row = db.get(DsrRequest, request_id)
    if row is None or row.user_id != user.id:
        raise NotFound("request not found")
    return row


def process_request(
    db: Session,
    provider: DatabaseKeyProvider,
    request: DsrRequest,
    handler_id: uuid.UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Fulfil a request. access/portability return the collected data; correction
    applies non-medical profile changes; erasure runs the pipeline; objection
    restricts processing."""
    if request.status != "open":
        raise Conflict("request already processed")
    result: dict[str, Any] = {}
    user = db.get(User, request.user_id)
    if user is None:
        raise NotFound("user missing")
    if request.type in ("access", "portability"):
        from app.users.service import public_view

        result = {
            "profile": public_view(user),
            "diary_entries": get_entries(db, provider, user),
            "format": "json",
        }
    elif request.type == "correction":
        payload = request.payload or {}
        if "language" in payload:
            user.language = (
                payload["language"] if payload["language"] in {"en", "sw"} else user.language
            )
        result = {"corrected": ["language"] if "language" in payload else []}
    elif request.type == "erasure":
        # Erasure deletes DSR rows (including this one): record fulfilment first,
        # then destroy. run_erasure writes its own audit entry and commits.
        request.status = "fulfilled"
        request.completed_at = utc_now_naive()
        request.handler_id = handler_id
        db.flush()
        record_event(
            db,
            event_type="dsr_fulfilled",
            actor_type="staff",
            actor_id=handler_id,
            actor_role=None,
            resource_type="dsr_request",
            resource_id=request.id,
            payload={"type": request.type},
        )
        result = run_erasure(db, user.id, provider)
        return result
    elif request.type == "objection":
        user.processing_restricted = True
        result = {"processing_restricted": True}
    request.status = "fulfilled"
    request.completed_at = utc_now_naive()
    request.handler_id = handler_id
    db.flush()
    record_event(
        db,
        event_type="dsr_fulfilled",
        actor_type="staff",
        actor_id=handler_id,
        actor_role=None,
        resource_type="dsr_request",
        resource_id=request.id,
        payload={"type": request.type},
    )
    return result


def list_requests(db: Session) -> list[DsrRequest]:
    return list(db.execute(select(DsrRequest).order_by(DsrRequest.submitted_at.desc())).scalars())
