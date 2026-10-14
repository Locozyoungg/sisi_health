"""Erasure pipeline (spec 6, assumption A7): deletes diary ciphertexts, evaluations,
per-user data keys, PII fields, devices, refresh tokens, consent events, and DSR
requests. The audit chain is retained — its rows carry only pseudonymous UUIDs and
sanitized payloads, and after the keys and mapping are destroyed they identify
nobody, which is the documented lawful-basis for retention."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.config import Settings
from app.core.ids import uuid7
from app.core.time import utc_now, utc_now_naive
from app.models import (
    ConsentEvent,
    Device,
    DiaryEntry,
    DiaryEntryVersion,
    DsrRequest,
    ErasureJob,
    RefreshToken,
    RuleEvaluation,
    User,
)

ERASURE_WINDOW_HOURS = 24  # processing must stop within 24 hours of revocation


def schedule_erasure(db: Session, user_id: uuid.UUID, requested_via: str) -> ErasureJob:
    settings = Settings()
    job = ErasureJob(
        id=uuid7(),
        user_id=user_id,
        status="pending",
        requested_via=requested_via,
        deadline_at=utc_now_naive() + timedelta(days=settings.dsr_deadline_days),
        created_at=utc_now_naive(),
    )
    db.add(job)
    db.flush()
    return job


def run_erasure(db: Session, user_id: uuid.UUID, provider: Any) -> dict[str, Any]:
    """Execute the erasure for one user. Returns a report of what was destroyed.
    The erasure_jobs row itself is removed on success (it references the user)."""
    user = db.get(User, user_id)
    if user is None:
        return {"erased": False, "reason": "user missing"}

    # 1. Diary ciphertexts, evaluations, and the user's data keys (data destroyed
    #    with the key, not recoverable even from a restored backup).
    entries = db.execute(select(DiaryEntry.id).where(DiaryEntry.user_id == user_id)).scalars().all()
    if entries:
        db.execute(delete(DiaryEntryVersion).where(DiaryEntryVersion.entry_id.in_(entries)))
        db.execute(delete(DiaryEntry).where(DiaryEntry.user_id == user_id))
    db.execute(delete(RuleEvaluation).where(RuleEvaluation.user_id == user_id))
    data_keys_deleted = provider.delete_data_keys(db, "user", user_id)

    # 2. Auth material.
    db.execute(delete(Device).where(Device.user_id == user_id))
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))

    # 3. Consent events and DSR requests (the audit trail keeps pseudonymous evidence).
    db.execute(delete(ConsentEvent).where(ConsentEvent.user_id == user_id))
    db.execute(delete(DsrRequest).where(DsrRequest.user_id == user_id))

    # 4. PII fields redacted; the row survives only as an unlinkable anchor.
    user.phone_encrypted = None
    user.phone_hash = None
    user.birth_date_encrypted = None
    user.pseudonym_id = None
    user.status = "erased"
    user.processing_restricted = False
    user.erased_at = utc_now_naive()

    # 5. Audit (sanitized; counts only) and job cleanup.
    record_event(
        db,
        event_type="erasure_completed",
        actor_type="system",
        actor_id=None,
        actor_role=None,
        resource_type="user",
        resource_id=user_id,
        payload={"diary_entries_removed": len(entries), "data_keys_removed": data_keys_deleted},
    )
    db.execute(delete(ErasureJob).where(ErasureJob.user_id == user_id))
    db.commit()
    return {
        "erased": True,
        "diary_entries_removed": len(entries),
        "data_keys_removed": data_keys_deleted,
        "erased_at": utc_now().isoformat(),
    }
