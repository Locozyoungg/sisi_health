"""Assessment band semantics: the rules engine (never an LLM) assigns bands;
red flags are urgent and can never be lowered (spec 7 safety asymmetry)."""

from gateway.flows.assessment import evaluate_assessment, features_from_answers, question_for


def _engine():
    from app.config import get_settings
    from app.rules.loader import build_engine

    return build_engine(get_settings().ontology_dir, allow_unvalidated=True)


def _answers(**overrides):
    base = {
        "pain": 3,
        "bleeding_volume": 1,
        "bleeding_pattern": "regular",
        "days_missed": 0,
        "dizziness": False,
        "fatigue": False,
        "cycle_regular": "regular",
        "duration": "lt3m",
        "pain_stops_activities": False,
        "dyspareunia": False,
        "dyschezia": False,
    }
    base.update(overrides)
    return base


def test_mild_answers_band_green():
    result = evaluate_assessment(_engine(), _answers(), age=24)
    assert result.band == "GREEN"


def test_heavy_bleeding_with_dizziness_is_urgent():
    result = evaluate_assessment(_engine(), _answers(bleeding_volume=4, dizziness=True), age=24)
    assert result.band == "RED"
    assert result.urgent is True
    assert "redflag-heavy-bleeding-dizziness" in result.indicators


def test_severe_pain_is_urgent():
    result = evaluate_assessment(_engine(), _answers(pain=9), age=24)
    assert result.band == "RED"


def test_red_flag_cannot_be_lowered():
    """No input combination lowers a band when a red-flag symptom is present."""
    result = evaluate_assessment(
        _engine(),
        _answers(pain=9, bleeding_volume=0, dizziness=False, fatigue=False),
        age=24,
    )
    assert result.band == "RED"


def test_heavy_bleeding_and_fatigue_flags_anemia_band():
    result = evaluate_assessment(_engine(), _answers(bleeding_volume=4, fatigue=True), age=24)
    assert result.band == "ORANGE"
    assert "anemia-risk-flag" in result.indicators


def test_age_gated_question_mapping():
    """q10 maps to dyspareunia for adults, dyschezia for minors (spec 5.1)."""
    assert question_for(9, age=25)["key"] == "dyspareunia"
    assert question_for(9, age=15)["key"] == "dyschezia"


def test_features_mapping_is_complete_and_explicit():
    """Every rule-schema input is present; self_harm and the cervical signals are
    explicitly False/0 (never left missing — missing would trigger the red-flag
    asymmetry for everyone)."""
    features = features_from_answers(_answers(), age=24)
    expected_keys = {
        "max_pain_90d",
        "avg_pain_90d",
        "cyclical_pain_ratio_90d",
        "avg_bleeding_volume_90d",
        "fatigue_ratio_30d",
        "cycle_irregularity_90d",
        "dyschezia",
        "dyspareunia",
        "pelvic_pressure",
        "urinary_frequency",
        "androgenic_symptoms",
        "self_harm_signal",
        "dizziness_signal",
        "postcoital_bleeding_signal",
        "intermenstrual_bleeding_signal",
        "postmenopausal_bleeding_signal",
        "unusual_discharge_days_90d",
    }
    assert set(features.keys()) == expected_keys
    assert features["self_harm_signal"] is False
    assert features["dizziness_signal"] is False
    assert features["postcoital_bleeding_signal"] is False
    assert features["intermenstrual_bleeding_signal"] is False
    assert features["postmenopausal_bleeding_signal"] is False
    assert features["unusual_discharge_days_90d"] == 0
    assert features["max_pain_90d"] == 3.0


def test_assessment_never_returns_not_enough_data():
    """A one-time assessment always produces a band — the 14-day gate is a
    diary-pattern rule, not an assessment rule (CC-1)."""
    result = evaluate_assessment(_engine(), _answers(), age=24)
    assert result.band in {"GREEN", "YELLOW", "ORANGE", "RED"}
