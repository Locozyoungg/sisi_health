"""Audit service. Chain hashing happens in the DB trigger (migration 0001); this
service guarantees the content policy: audit payloads never contain names, phone
numbers, diary content, or symptom narratives (spec 6, non-negotiable 5)."""

import re
import uuid
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import AuditEvent

# Keys whose values are stripped no matter how deeply nested.
FORBIDDEN_KEYS = {
    "phone",
    "phone_number",
    "name",
    "names",
    "first_name",
    "last_name",
    "email",
    "symptoms",
    "notes",
    "diary",
    "content",
    "text",
    "message",
    "answers",
    "narrative",
    "reason_text",
}

# Runs of 9+ digits look like phone numbers and are stripped from any string value.
_PHONE_LIKE = re.compile(r"(?<!\d)\d{9,}(?!\d)")

REDACTED = "[REDACTED]"


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip forbidden keys and phone-like digit runs. Returns a new dict."""

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: REDACTED if k.lower() in FORBIDDEN_KEYS else scrub(v) for k, v in value.items()
            }
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            return _PHONE_LIKE.sub(REDACTED, value)
        return value

    return cast(dict[str, Any], scrub(payload))


def record_event(
    db: Session,
    *,
    event_type: str,
    actor_type: str,
    actor_id: uuid.UUID | None,
    actor_role: str | None,
    resource_type: str,
    resource_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one audit event. The DB trigger computes prev_hash/row_hash."""
    event = AuditEvent(
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_role=actor_role,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=sanitize_payload(payload or {}),
    )
    db.add(event)
    db.flush()
    return event
