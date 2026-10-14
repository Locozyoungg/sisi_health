"""Consent lifecycle + erasure e2e (Phase 1 DoD): grant -> diary -> revoke ->
erasure destroys data, redacts PII, and leaves the audit chain intact."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.audit.verifier import verify_chain
from app.consent.erasure import run_erasure
from app.consent.service import consent_state, grant_consent, revoke_consent
from app.core.errors import Conflict
from app.diary.service import SyncEntry, get_entries, sync_entries
from app.models import DataKey, DiaryEntry, DiaryEntryVersion, ErasureJob, RuleEvaluation, User
from app.users.service import age_of


def _entry(day_offset: int, **payload) -> SyncEntry:
    base = {
        "date": (date.today() - timedelta(days=day_offset)).isoformat(),
        "pain": 3,
        "bleeding_volume": 1,
        "symptoms": {"fatigue": False},
    }
    base.update(payload)
    return SyncEntry(
        client_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex[:32],
        version=1,
        payload=base,
    )


def test_adult_self_consent_grants_diary_access(db, provider, adult_with_consent):
    state = consent_state(db, adult_with_consent, age_of(provider, db, adult_with_consent))
    assert state["satisfied"] is True
    assert state["required"] == ["self_grant"]


def test_minor_requires_guardian_and_assent(db, provider, make_minor):
    minor = make_minor()
    age = age_of(provider, db, minor)
    with pytest.raises(Conflict, match="guardian"):
        grant_consent(db, minor, event_type="self_grant", method="digital", age=age)
    state = consent_state(db, minor, age)
    assert state["satisfied"] is False
    grant_consent(db, minor, event_type="guardian_grant", method="sms_link", age=age)
    assert consent_state(db, minor, age)["satisfied"] is False  # assent still missing
    grant_consent(db, minor, event_type="minor_assent", method="digital", age=age)
    assert consent_state(db, minor, age)["satisfied"] is True


def test_guardian_grant_rejected_for_adult(db, provider, adult_with_consent):
    with pytest.raises(Conflict, match="minors"):
        grant_consent(
            db,
            adult_with_consent,
            event_type="guardian_grant",
            method="digital",
            age=age_of(provider, db, adult_with_consent),
        )


def test_revocation_schedules_erasure(db, provider, adult_with_consent):
    result = revoke_consent(db, adult_with_consent)
    db.commit()
    assert result["revoked"] >= 1
    job = db.execute(select(ErasureJob)).scalars().first()
    assert job is not None
    assert job.status == "pending"


def test_erasure_e2e_destroys_data_and_keeps_chain(db, provider, adult_with_consent):
    user = adult_with_consent
    sync_entries(
        db,
        provider,
        user,
        [_entry(i, pain=5 if i % 2 else 2) for i in range(20)],
    )
    db.commit()
    assert len(get_entries(db, provider, user)) == 20
    assert db.execute(select(DiaryEntryVersion)).scalars().all()

    report = run_erasure(db, user.id, provider)

    assert report["erased"] is True
    assert report["diary_entries_removed"] == 20
    assert report["data_keys_removed"] >= 1
    assert db.execute(select(DiaryEntry)).scalars().all() == []
    assert db.execute(select(DiaryEntryVersion)).scalars().all() == []
    assert db.execute(select(RuleEvaluation)).scalars().all() == []
    assert db.execute(select(ErasureJob)).scalars().all() == []
    assert db.execute(select(DataKey).where(DataKey.owner_id == user.id)).scalars().all() == []

    erased = db.get(User, user.id)
    assert erased.status == "erased"
    assert erased.phone_encrypted is None
    assert erased.phone_hash is None
    assert erased.birth_date_encrypted is None
    assert erased.pseudonym_id is None

    report_chain = verify_chain(db)
    assert report_chain["ok"] is True
    assert report_chain["events_checked"] > 0


def test_erasure_is_idempotent(db, provider, adult_with_consent):
    user = adult_with_consent
    first = run_erasure(db, user.id, provider)
    second = run_erasure(db, user.id, provider)
    assert first["erased"] is True
    assert second["erased"] is True
    assert second["diary_entries_removed"] == 0
