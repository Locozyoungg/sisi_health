"""Phase 3 demo: full English and Kiswahili journeys through the real flow
engine, printing every screen — proves the DoD items live (this is
`make ussd-demo`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import get_settings as backend_settings  # noqa: E402
from app.crypto.key_provider import DatabaseKeyProvider  # noqa: E402
from app.rules.loader import build_engine  # noqa: E402

from gateway.config import GatewaySettings  # noqa: E402
from gateway.flows.engine import FlowEngine  # noqa: E402
from gateway.flows.screens import SCREEN_LIMIT, SMS_SUMMARY  # noqa: E402
from gateway.providers.messaging import RecordingProvider  # noqa: E402
from gateway.sessions.store import build_session_store  # noqa: E402


def journey(
    flow: FlowEngine, session_id: str, phone: str, lang: str, age: str, answers: list[str]
) -> str:
    print(f"\n=== {session_id} ({'Kiswahili' if lang == '2' else 'English'}, age {age}) ===")
    steps = [("", "welcome"), (lang, "lang"), (age, "age"), ("1", "privacy")] + [
        (a, f"q{i + 1}") for i, a in enumerate(answers)
    ]
    last = ""
    for text, label in steps:
        screen = flow.handle(session_id=session_id, phone=phone, text=text)
        assert len(screen) <= SCREEN_LIMIT, f"{label}: {len(screen)} chars"
        last = screen
        print(f"[{label:8s}] {screen!r}")
    return last


def main() -> int:
    # Fresh start: clear any sessions left by earlier runs (5-minute TTL would
    # otherwise make journeys resume mid-flow).
    from app.db import SessionLocal
    from sqlalchemy import text as sql_text

    with SessionLocal() as db:
        db.execute(sql_text("DELETE FROM core.ussd_sessions"))
        db.commit()

    backend = backend_settings()
    engine = build_engine(backend.ontology_dir, allow_unvalidated=True)
    recorder = RecordingProvider()
    flow = FlowEngine(
        store=build_session_store(GatewaySettings()),
        settings=GatewaySettings(),
        engine=engine,
        provider=DatabaseKeyProvider(backend),
        sms=recorder,
    )

    journey(
        flow,
        "demo-en",
        "+254700000201",
        "1",
        "24",
        ["3", "2", "1", "2", "2", "2", "1", "1", "2", "2"],
    )
    journey(
        flow,
        "demo-sw",
        "+254700000202",
        "2",
        "15",
        ["4", "3", "2", "1", "1", "2", "2", "2", "1", "2"],
    )
    journey(
        flow,
        "demo-red",
        "+254700000203",
        "1",
        "30",
        ["8", "5", "2", "4", "1", "1", "2", "3", "1", "2"],
    )

    # Timeout/resume proof: a redelivered input (same text, same state) replays
    # the identical screen — the carrier can safely re-POST any callback.
    flow.handle(session_id="demo-replay", phone="+254700000204", text="")
    first_welcome = flow.handle(session_id="demo-replay", phone="+254700000204", text="")
    redelivered = flow.handle(session_id="demo-replay", phone="+254700000204", text="")
    print(f"\n[replay] identical screen on redelivery: {redelivered == first_welcome}")
    assert redelivered == first_welcome

    print("\n[SMS] recorded summaries (generic wording only):")
    for phone, message in recorder.messages:
        assert message == SMS_SUMMARY
        print(f"  -> {phone}: {message!r}")
    print("\nUSSD DEMO PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
