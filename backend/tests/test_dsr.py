"""DSR requests: deadlines, fulfilment types, and the admin processing path."""

import uuid
from datetime import timedelta

from app.config import get_settings
from app.core.time import utc_now_naive
from app.dsr.service import DsrPayload, process_request, submit_request
from app.models import DsrRequest, User


def test_submit_sets_deadline(db, adult_with_consent):
    row = submit_request(db, adult_with_consent, DsrPayload(type="access"), get_settings())
    db.commit()
    assert row.status == "open"
    expected = utc_now_naive() + timedelta(days=get_settings().dsr_deadline_days)
    assert abs((row.deadline_at - expected).total_seconds()) < 60


def test_access_returns_collected_data(db, provider, adult_with_consent):
    row = submit_request(db, adult_with_consent, DsrPayload(type="access"), get_settings())
    db.commit()
    result = process_request(db, provider, row, handler_id=uuid.uuid4(), settings=get_settings())
    db.commit()
    assert "profile" in result
    assert "diary_entries" in result
    assert db.get(DsrRequest, row.id).status == "fulfilled"


def test_correction_applies_language(db, provider, adult_with_consent):
    row = submit_request(
        db,
        adult_with_consent,
        DsrPayload(type="correction", payload={"language": "sw"}),
        get_settings(),
    )
    db.commit()
    process_request(db, provider, row, handler_id=uuid.uuid4(), settings=get_settings())
    db.commit()
    assert db.get(User, adult_with_consent.id).language == "sw"


def test_objection_restricts_processing(db, provider, adult_with_consent):
    row = submit_request(db, adult_with_consent, DsrPayload(type="objection"), get_settings())
    db.commit()
    result = process_request(db, provider, row, handler_id=uuid.uuid4(), settings=get_settings())
    db.commit()
    assert result["processing_restricted"] is True
    assert db.get(User, adult_with_consent.id).processing_restricted is True


def test_erasure_via_dsr(db, provider, adult_with_consent):
    row = submit_request(db, adult_with_consent, DsrPayload(type="erasure"), get_settings())
    db.commit()
    result = process_request(db, provider, row, handler_id=uuid.uuid4(), settings=get_settings())
    db.commit()
    assert result["erased"] is True
    assert db.get(User, adult_with_consent.id).status == "erased"


def test_unknown_type_rejected(db, adult_with_consent):
    import pytest

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        submit_request(db, adult_with_consent, DsrPayload(type="delete"), get_settings())
