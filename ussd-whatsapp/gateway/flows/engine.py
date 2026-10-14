"""The USSD flow state machine. Deterministic: same session + same input always
reproduces the same screen (idempotent — carrier redelivery is expected). "0"
steps back and "00" exits on every screen; sessions resume within 5 minutes;
after timeout the user restarts with no residual data shown (spec 5.3).
The phone number is used only within the live callback (never stored in the
session store — sessions are keyed by phone hash per spec)."""

from typing import Any, Protocol

from app.audit.service import record_event
from app.auth.otp import phone_hash
from app.config import get_settings
from app.core.errors import ValidationError
from app.core.ids import uuid7
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.models import SchoolAssessment
from app.rules.engine import RuleEngine

from gateway.config import GatewaySettings
from gateway.flows import assessment as assessment_flow
from gateway.flows.screens import FOOTER_EN, FOOTER_SW, SCREENS, SMS_SUMMARY
from gateway.sessions.store import SESSION_TTL_SECONDS, SessionStore

BACK = "0"
EXIT = "00"

# Final screens carry no footer (the flow is over).
FOOTERED_STATES = {
    "welcome",
    "lang",
    "age",
    "privacy",
    "q1",
    "q2",
    "q3",
    "q4",
    "q5",
    "q6",
    "q7",
    "q8",
    "q9",
    "q10",
}

STATE_ORDER = ["welcome", "lang", "age", "privacy"] + [f"q{i}" for i in range(1, 11)]


class SmsSender(Protocol):
    def send_sms(self, phone: str, message: str) -> None: ...


class FlowEngine:
    def __init__(
        self,
        store: SessionStore,
        settings: GatewaySettings,
        engine: RuleEngine,
        provider: DatabaseKeyProvider,
        sms: SmsSender,
    ) -> None:
        self._store = store
        self._settings = settings
        self._engine = engine
        self._provider = provider
        self._sms = sms

    def handle(self, *, session_id: str, phone: str, text: str, channel: str = "ussd") -> str:
        """One callback. session_id is ignored for state (sessions are keyed by
        phone hash per spec); it exists for provider observability."""
        p_hash = phone_hash(phone, get_settings())
        if text.strip() == EXIT:
            self._store.delete(p_hash)
            return self._screen("exit", self._lang(p_hash) or "en")

        session = self._store.get(p_hash)
        if session is None:
            session = {
                "state": "welcome",
                "lang": None,
                "age": None,
                "answers": {},
                "last_input": None,
            }
            welcome_screen = self._render("welcome", session)
            session["last_input"] = text
            session["last_output"] = welcome_screen
            session["answered"] = {}
            self._store.put(p_hash, session, ttl_seconds=SESSION_TTL_SECONDS)
            return welcome_screen

        # Idempotent replay (carrier redelivery): the same input for the SAME
        # state returns the stored output. Consecutive identical answers to
        # different questions are normal and advance (the state differs).
        answered = session.get("answered", {})
        if answered.get(session["state"]) == text:
            return session.get("last_output") or self._render(session["state"], session)

        input_state = session["state"]
        session["last_input"] = text
        output = self._advance(session, text.strip(), channel, phone)
        session["last_output"] = output
        answered[input_state] = text
        session["answered"] = answered
        self._store.put(p_hash, session, ttl_seconds=SESSION_TTL_SECONDS)
        return output

    # ---- internals ---------------------------------------------------------

    def _lang(self, p_hash: str) -> str | None:
        session = self._store.get(p_hash)
        return session.get("lang") if session else None

    def _screen(self, key: str, lang: str) -> str:
        return SCREENS.get(lang, SCREENS["en"]).get(key, SCREENS["en"][key])

    def _render(self, state: str, session: dict[str, Any]) -> str:
        lang = session.get("lang") or "en"
        if state == "q10":
            body = self._screen(assessment_flow.question_for(9, session["age"])["screen"], lang)
        elif state == "privacy":
            key = (
                "privacy_minor"
                if session["age"] < get_settings().self_consent_age
                else "privacy_adult"
            )
            body = self._screen(key, lang)
        elif state == "result":
            band = session.get("band", "GREEN")
            body = self._screen(f"result_{band.lower()}", lang)
        else:
            body = self._screen(state, lang)
        if state in FOOTERED_STATES:
            body += "\n" + (FOOTER_SW if lang == "sw" else FOOTER_EN)
        return body

    def _advance(self, session: dict[str, Any], text: str, channel: str, phone: str) -> str:
        state = session["state"]
        lang = session.get("lang") or "en"

        if text == BACK:
            return self._go_back(session)

        if state in {"welcome", "lang"}:
            # The welcome screen IS the language select: the subscriber's first
            # input chooses the language directly.
            if text in {"1", "2"}:
                session["lang"] = "en" if text == "1" else "sw"
                session["state"] = "age"
            else:
                return self._render(state, session)
        elif state == "age":
            try:
                age = int(text)
            except ValueError:
                return self._render("age", session)
            if age < 13:
                return self._screen("age_blocked", lang)  # flow ends; nothing stored
            session["age"] = age
            session["state"] = "privacy"
        elif state == "privacy":
            if text != "1":
                return self._render("privacy", session)
            session["consent"] = (
                "self_granted"
                if session["age"] >= get_settings().self_consent_age
                else "minor_assent_only"
            )
            session["question_index"] = 0
            session["state"] = "q1"
        elif state.startswith("q") and state != "q10":
            index = int(state[1:]) - 1
            question = assessment_flow.question_for(index, session["age"])
            try:
                session["answers"][question["key"]] = question["parse"](text)
            except (ValidationError, ValueError):
                return self._render(state, session)
            if index + 1 < assessment_flow.question_count():
                session["state"] = f"q{index + 2}"
            else:
                return self._finish(session, channel, phone)
        elif state == "q10":
            question = assessment_flow.question_for(9, session["age"])
            try:
                session["answers"][question["key"]] = question["parse"](text)
            except (ValidationError, ValueError):
                return self._render(state, session)
            return self._finish(session, channel, phone)
        elif state == "result":
            session["state"] = "done"
            return self._screen("exit", lang)
        else:  # done / unknown: restart safely with no residual data shown
            session["state"] = "welcome"
            session["answers"] = {}
        return self._render(session["state"], session)

    def _go_back(self, session: dict[str, Any]) -> str:
        state = session["state"]
        index = STATE_ORDER.index(state) if state in STATE_ORDER else 0
        session["state"] = STATE_ORDER[max(index - 1, 0)]
        return self._render(session["state"], session)

    def _finish(self, session: dict[str, Any], channel: str, phone: str) -> str:
        age = session["age"]
        lang = session.get("lang") or "en"
        evaluation = assessment_flow.evaluate_assessment(self._engine, session["answers"], age)
        consent_state = session.get("consent", "none")
        session["band"] = evaluation.band
        assessment_id = uuid7()

        with SessionLocal() as db:
            ciphertext, key_id = self._seal(db, session, evaluation, age, lang, assessment_id)
            assessment_row = SchoolAssessment(
                id=assessment_id,  # same id owns the data key (erasure finds it)
                phone_hash=phone_hash(phone, get_settings()),
                age_band="13-17" if age < get_settings().self_consent_age else "18+",
                language=lang,
                consent_state=consent_state,
                payload_ciphertext=ciphertext,
                key_id=key_id,
                channel=channel,
            )
            db.add(assessment_row)
            db.flush()
            record_event(
                db,
                event_type="school_assessment_completed",
                actor_type="user",
                actor_id=None,
                actor_role=None,
                resource_type="school_assessment",
                resource_id=assessment_row.id,
                payload={"channel": channel, "consent_state": consent_state},  # counts only
            )
            db.commit()

        session["state"] = "result"
        self._sms.send_sms(phone, SMS_SUMMARY)
        return self._render("result", session)

    def _seal(
        self,
        db: Any,
        session: dict[str, Any],
        evaluation: Any,
        age: int,
        lang: str,
        assessment_id: Any,
    ) -> tuple[bytes, Any]:
        import json as json_lib

        payload = {
            "answers": session["answers"],
            "band": evaluation.band,
            "indicators": evaluation.indicators,
            "urgent": evaluation.urgent,
            "safeguarding": evaluation.safeguarding,
            "age": age,
            "language": lang,
            "rule_set_version": evaluation.rule_set_version,
        }
        data_key = self._provider.get_or_create_data_key(db, "assessment", assessment_id)
        ciphertext = self._provider.wrap(
            json_lib.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        return ciphertext, data_key.id
