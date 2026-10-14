"""Timeout and resume semantics (spec 5.3): sessions resume within 5 minutes;
replaying the same input at the same state reproduces the same screen; after
expiry the user restarts with no residual data shown."""

from datetime import timedelta

from app.models import UssdSession
from sqlalchemy import select

from gateway.sessions.store import SESSION_TTL_SECONDS


def test_replay_is_idempotent(flow):
    phone = "+254711100001"
    first = flow.handle(session_id="s1", phone=phone, text="")
    replay = flow.handle(session_id="s1", phone=phone, text="")
    assert replay == first


def test_same_input_at_same_state_does_not_advance_twice(flow):
    """A redelivered input (same text at the same state) replays the stored
    screen instead of being processed twice."""
    phone = "+254711100002"
    flow.handle(session_id="s2", phone=phone, text="")
    flow.handle(session_id="s2", phone=phone, text="1")  # English -> age screen
    blocked = flow.handle(session_id="s2", phone=phone, text="5")  # age 5 -> blocked
    replay = flow.handle(session_id="s2", phone=phone, text="5")  # redelivered
    assert replay == blocked


def test_consecutive_identical_answers_advance(flow):
    """Two identical answers to two different questions must both count."""
    phone = "+254711100007"
    flow.handle(session_id="s7", phone=phone, text="")
    flow.handle(session_id="s7", phone=phone, text="1")
    flow.handle(session_id="s7", phone=phone, text="24")
    flow.handle(session_id="s7", phone=phone, text="1")  # privacy -> q1
    q2 = flow.handle(session_id="s7", phone=phone, text="2")  # q1 answer -> q2
    q3 = flow.handle(session_id="s7", phone=phone, text="2")  # q2 answer -> q3
    assert "How heavy is your bleeding" in q2
    assert "How is your bleeding pattern" in q3


def test_back_and_exit_available_on_every_screen(flow):
    phone = "+254711100003"
    screens = [
        flow.handle(session_id="s3", phone=phone, text=""),  # welcome
        flow.handle(session_id="s3", phone=phone, text="1"),  # lang -> age
        flow.handle(session_id="s3", phone=phone, text="24"),  # age -> privacy
        flow.handle(session_id="s3", phone=phone, text="1"),  # privacy -> q1
        flow.handle(session_id="s3", phone=phone, text="3"),  # q1 -> q2
    ]
    for screen in screens:
        assert "0 Back" in screen and "00 Exit" in screen


def test_zero_steps_back(flow):
    phone = "+254711100004"
    flow.handle(session_id="s4", phone=phone, text="")
    flow.handle(session_id="s4", phone=phone, text="1")  # en -> age
    flow.handle(session_id="s4", phone=phone, text="24")  # age -> privacy
    flow.handle(session_id="s4", phone=phone, text="1")  # privacy -> q1
    back_to_privacy = flow.handle(session_id="s4", phone=phone, text="0")
    assert "SISI keeps your answers private" in back_to_privacy


def test_double_zero_exits_and_clears(flow, db):
    from app.auth.otp import phone_hash
    from app.config import get_settings

    phone = "+254711100005"
    flow.handle(session_id="s5", phone=phone, text="")
    flow.handle(session_id="s5", phone=phone, text="1")
    exit_screen = flow.handle(session_id="s5", phone=phone, text="00")
    assert "Session ended" in exit_screen
    # This phone's session is cleared server-side.
    p_hash = phone_hash(phone, get_settings())
    rows = db.execute(select(UssdSession).where(UssdSession.phone_hash == p_hash)).scalars().all()
    assert rows == []


def test_session_expiry_restarts_flow(flow, db):
    phone = "+254711100006"
    flow.handle(session_id="s6", phone=phone, text="")
    flow.handle(session_id="s6", phone=phone, text="1")  # choose English -> age screen
    # Force expiry of the stored session (simulating the 5-minute window passing).
    row = db.execute(select(UssdSession)).scalars().first()
    assert row is not None
    row.expires_at = row.expires_at - timedelta(seconds=SESSION_TTL_SECONDS + 10)
    db.commit()
    # Next callback: session expired -> fresh welcome with no residual data shown.
    screen = flow.handle(session_id="s6", phone=phone, text="")
    assert "Welcome to SISI" in screen  # fresh welcome, no residual answers
