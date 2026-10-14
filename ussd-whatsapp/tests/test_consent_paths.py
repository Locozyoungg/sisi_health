"""Consent paths (spec 3.2/5.3 DoD): adults self-consent at the privacy step;
minors record assent with guardian consent left pending (the nurse completes it
in Phase 4); assessments are stored with the right consent_state."""

from app.models import SchoolAssessment
from sqlalchemy import select


def _complete(flow, phone: str, session_id: str, age: str, answers: list[str]) -> str:
    flow.handle(session_id=session_id, phone=phone, text="")
    flow.handle(session_id=session_id, phone=phone, text="1")
    flow.handle(session_id=session_id, phone=phone, text=age)
    flow.handle(session_id=session_id, phone=phone, text="1")
    for answer in answers:
        flow.handle(session_id=session_id, phone=phone, text=answer)
    return flow.handle(session_id=session_id, phone=phone, text="1")  # exit result


def test_adult_assessment_records_self_consent(flow, db):
    _complete(flow, "+254711200001", "c1", "30", ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"])
    row = db.execute(select(SchoolAssessment)).scalars().first()
    assert row is not None
    assert row.consent_state == "self_granted"
    assert row.age_band == "18+"


def test_minor_assessment_records_assent_with_guardian_pending(flow, db):
    _complete(flow, "+254711200002", "c2", "15", ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"])
    row = db.execute(select(SchoolAssessment)).scalars().first()
    assert row.consent_state == "minor_assent_only"  # guardian grant = Phase 4 nurse flow
    assert row.age_band == "13-17"


def test_minor_privacy_screen_mentions_guardian(flow):
    flow.handle(session_id="c3", phone="+254711200003", text="")
    flow.handle(session_id="c3", phone="+254711200003", text="1")
    privacy_screen = flow.handle(session_id="c3", phone="+254711200003", text="14")
    assert "parent" in privacy_screen or "guardian" in privacy_screen


def test_adult_privacy_screen_offers_self_consent(flow):
    flow.handle(session_id="c4", phone="+254711200004", text="")
    flow.handle(session_id="c4", phone="+254711200004", text="1")
    privacy_screen = flow.handle(session_id="c4", phone="+254711200004", text="40")
    assert "Agree" in privacy_screen


def test_assessment_answers_are_encrypted_at_rest(flow, db):
    _complete(flow, "+254711200005", "c5", "25", ["5", "5", "2", "3", "1", "1", "2", "3", "1", "1"])
    row = db.execute(select(SchoolAssessment)).scalars().first()
    assert b'"answers"' not in row.payload_ciphertext
    assert row.payload_ciphertext != b""
