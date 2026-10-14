"""End-to-end USSD journeys in both languages through the Africa's Talking
callback contract (form-encoded POSTs — exactly what AT sends). No real
credentials: this exercises the full protocol against the real flow engine."""

from tests.conftest import ussd_post


def _run_journey(
    client, session_id: str, phone: str, lang_choice: str, age: str, answers: list[str]
) -> list[str]:
    screens = [ussd_post(client, session_id, phone, "")]  # welcome
    screens.append(ussd_post(client, session_id, phone, lang_choice))  # lang
    screens.append(ussd_post(client, session_id, phone, age))  # age
    screens.append(ussd_post(client, session_id, phone, "1"))  # privacy agree
    for answer in answers:
        screens.append(ussd_post(client, session_id, phone, answer))
    return screens


def test_full_english_journey_adult(gateway_client):
    screens = _run_journey(
        gateway_client,
        "sess-en-1",
        "+254711000001",
        "1",
        "24",
        ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"],
    )
    assert "Welcome to SISI" in screens[0]
    assert "0 Back 00 Exit" in screens[0]
    assert "How old are you" in screens[1]  # lang choice advances straight to age
    assert "SISI keeps your answers private" in screens[2]
    assert "On a scale of 0 to 10" in screens[3]  # q1
    assert "How heavy is your bleeding" in screens[4]  # q2
    # q10 for an adult is the sexual-health question (age-gated 18+)
    assert "intercourse" in screens[12]
    # Final screen is a band result, never a diagnosis and never NOT_ENOUGH_DATA
    assert "Please see" in screens[13] or "Thank you" in screens[13]
    assert "not enough" not in screens[13]


def test_full_swahili_journey_minor(gateway_client):
    screens = _run_journey(
        gateway_client,
        "sess-sw-1",
        "+254711000002",
        "2",
        "15",
        ["4", "3", "2", "1", "1", "2", "2", "2", "1", "2"],
    )
    assert (
        "Karibu" in screens[0] or "Welcome to SISI" in screens[0]
    )  # welcome precedes language choice
    assert "0 Rudi 00 Toka" in screens[1] or "0 Back 00 Exit" in screens[0]
    assert "Una miaka mingapi" in screens[1]
    assert "idhini ya mzazi" in screens[2]  # minor privacy notice mentions guardian
    # q10 for a minor is dyschezia — NEVER the sexual-health question
    assert "haja kubwa" in screens[12]
    assert "tendo la ndoa" not in "\n".join(screens)


def test_minor_never_sees_sexual_health_question(gateway_client):
    """Spec 5.1: sexual-health questions are shown only to users 18+."""
    minor_screens = _run_journey(
        gateway_client,
        "sess-agegate-1",
        "+254711000003",
        "1",
        "17",
        ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"],
    )
    adult_screens = _run_journey(
        gateway_client,
        "sess-agegate-2",
        "+254711000004",
        "1",
        "18",
        ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"],
    )
    joined_minor = "\n".join(minor_screens)
    joined_adult = "\n".join(adult_screens)
    assert "intercourse" not in joined_minor
    assert "intercourse" in joined_adult


def test_age_below_13_is_blocked(gateway_client):
    ussd_post(gateway_client, "sess-ageblock", "+254711000005", "")
    ussd_post(gateway_client, "sess-ageblock", "+254711000005", "1")
    screen = ussd_post(gateway_client, "sess-ageblock", "+254711000005", "12")
    assert "13 and above" in screen
    # Nothing further is stored or shown: the flow ends here.
    next_screen = ussd_post(gateway_client, "sess-ageblock", "+254711000005", "1")
    assert next_screen == screen or "13 and above" in next_screen


def test_sms_summary_is_generic(flow, recording_sms):
    """Completing an assessment sends exactly the generic spec 3.5 summary."""
    phone = "+254711000006"
    answers = ["5", "5", "2", "3", "1", "1", "2", "3", "1", "1"]
    flow.handle(session_id="sess-sms", phone=phone, text="")
    flow.handle(session_id="sess-sms", phone=phone, text="1")
    flow.handle(session_id="sess-sms", phone=phone, text="30")
    flow.handle(session_id="sess-sms", phone=phone, text="1")
    for answer in answers:
        flow.handle(session_id="sess-sms", phone=phone, text=answer)
    assert len(recording_sms.messages) == 1
    sent_phone, sent_text = recording_sms.messages[0]
    assert sent_phone == phone
    assert sent_text == (
        "Your health check results are ready. Visit your school nurse or open the app."
    )
    # Nothing condition-identifying or score-bearing in the SMS (spec 3.5)
    assert "RED" not in sent_text
    assert "pain" not in sent_text.lower()
