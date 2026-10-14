"""The 10-question symptom assessment (spec 5.3: pain, bleeding, school-days-
missed) and its deterministic mapping into rules-engine features. The engine —
never an LLM — assigns the band (non-negotiable 1). q10 is age-gated: sexual-
health questions are never shown to minors (spec 5.1)."""

from typing import Any

from app.core.errors import ValidationError
from app.rules.engine import RuleEngine
from app.rules.schemas import Evaluation


# (state key, question key, parser, validator) — q10 is chosen by age.
def _int_0_10(value: str) -> Any:
    parsed = int(value)
    if not 0 <= parsed <= 10:
        raise ValidationError("out of range")
    return parsed


def _int_0_60(value: str) -> Any:
    parsed = int(value)
    if not 0 <= parsed <= 60:
        raise ValidationError("out of range")
    return parsed


def _menu(choices: set[str], mapping: dict[str, Any]) -> Any:
    def parse(value: str) -> Any:
        if value not in choices:
            raise ValidationError("invalid choice")
        return mapping[value]

    return parse


Q2 = _menu({"1", "2", "3", "4", "5"}, {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4})
Q3 = _menu({"1", "2", "3"}, {"1": "regular", "2": "irregular", "3": "unsure"})
Q_YES_NO = _menu({"1", "2"}, {"1": True, "2": False})
Q_YES_NO_PREFER = _menu({"1", "2", "3"}, {"1": True, "2": False, "3": None})

QUESTIONS: list[dict[str, Any]] = [
    {"key": "pain", "screen": "q1", "parse": _int_0_10},
    {"key": "bleeding_volume", "screen": "q2", "parse": Q2},
    {"key": "bleeding_pattern", "screen": "q3", "parse": Q3},
    {"key": "days_missed", "screen": "q4", "parse": _int_0_60},
    {"key": "dizziness", "screen": "q5", "parse": Q_YES_NO},
    {"key": "fatigue", "screen": "q6", "parse": Q_YES_NO},
    {"key": "cycle_regular", "screen": "q7", "parse": Q3},
    {
        "key": "duration",
        "screen": "q8",
        "parse": _menu({"1", "2", "3"}, {"1": "lt3m", "2": "3to6m", "3": "gt6m"}),
    },
    {"key": "pain_stops_activities", "screen": "q9", "parse": Q_YES_NO},
]


def question_count() -> int:
    return len(QUESTIONS) + 1  # q10 always asked, variant chosen by age


def question_for(index: int, age: int) -> dict[str, Any]:
    """index is 0-based over the 10 questions; q10 is age-gated."""
    if index < len(QUESTIONS):
        return QUESTIONS[index]
    return {
        "key": "dyspareunia" if age >= 18 else "dyschezia",
        "screen": "q10_adult" if age >= 18 else "q10_minor",
        "parse": Q_YES_NO_PREFER,
    }


def features_from_answers(answers: dict[str, Any], age: int) -> dict[str, Any]:
    """Deterministic mapping to the rule-schema input names. Every key is set
    explicitly: self_harm_signal is False because it is never asked over USSD
    (missing would trigger the red-flag asymmetry and force RED for everyone)."""
    cycle = str(answers.get("cycle_regular") or "unsure")
    return {
        "max_pain_90d": float(answers["pain"]),
        "avg_pain_90d": float(answers["pain"]),
        "cyclical_pain_ratio_90d": None,
        "avg_bleeding_volume_90d": float(answers["bleeding_volume"]),
        "fatigue_ratio_30d": 1.0 if answers.get("fatigue") is True else 0.0,
        "cycle_irregularity_90d": {"regular": 2.0, "irregular": 9.0, "unsure": None}[cycle],
        "dyschezia": answers.get("dyschezia") is True,
        "dyspareunia": answers.get("dyspareunia") is True,
        "pelvic_pressure": False,
        "urinary_frequency": False,
        "androgenic_symptoms": False,
        "self_harm_signal": False,  # not asked over USSD; never left missing
        "dizziness_signal": answers.get("dizziness") is True,
    }


def evaluate_assessment(engine: RuleEngine, answers: dict[str, Any], age: int) -> Evaluation:
    return engine.evaluate_assessment(age=age, features=features_from_answers(answers, age))
