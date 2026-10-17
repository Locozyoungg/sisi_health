"""Assessment-mode evaluation (CC-1): same bands and red-flag asymmetry as the
diary engine, without the 14-day window gate. One-time USSD/WhatsApp
assessments must still produce immediate deterministic guidance."""

import pytest

from app.config import get_settings
from app.core.errors import ValidationError
from app.rules.loader import build_engine


def _features(**overrides):
    base = {
        "max_pain_90d": 3,
        "avg_pain_90d": 2.0,
        "cyclical_pain_ratio_90d": None,
        "avg_bleeding_volume_90d": 1,
        "fatigue_ratio_30d": 0.0,
        "cycle_irregularity_90d": None,
        "dyschezia": False,
        "dyspareunia": False,
        "pelvic_pressure": False,
        "urinary_frequency": False,
        "androgenic_symptoms": False,
        "self_harm_signal": False,
        "dizziness_signal": False,
        "postcoital_bleeding_signal": False,
        "intermenstrual_bleeding_signal": False,
        "postmenopausal_bleeding_signal": False,
        "unusual_discharge_days_90d": 0,
    }
    base.update(overrides)
    return base


def _engine():
    return build_engine(get_settings().ontology_dir, allow_unvalidated=True)


def test_assessment_produces_a_band_without_diary_history():
    result = _engine().evaluate_assessment(age=24, features=_features())
    assert result.band == "GREEN"
    assert result.indicators == []


def test_assessment_red_flags_are_urgent():
    result = _engine().evaluate_assessment(
        age=24,
        features=_features(avg_bleeding_volume_90d=3.5, dizziness_signal=True),
    )
    assert result.band == "RED"
    assert result.urgent is True
    assert "redflag-heavy-bleeding-dizziness" in result.indicators


def test_assessment_red_flag_cannot_be_lowered():
    """Safety asymmetry holds in assessment mode: no input combination lowers a
    band when a red-flag symptom is present."""
    result = _engine().evaluate_assessment(
        age=24,
        features=_features(max_pain_90d=9, avg_bleeding_volume_90d=0.0, fatigue_ratio_30d=0.0),
    )
    assert result.band == "RED"


def test_assessment_missing_red_flag_input_matches():
    result = _engine().evaluate_assessment(age=24, features=_features(max_pain_90d=None))
    assert result.band == "RED"


def test_assessment_safeguarding_for_self_harm():
    result = _engine().evaluate_assessment(age=15, features=_features(self_harm_signal=True))
    assert result.band == "RED"
    assert result.safeguarding is True


def test_assessment_age_below_13_rejected():
    """The under-13 block holds on the assessment path too (non-negotiable:
    users under 13 never reach the rules engine)."""
    with pytest.raises(ValidationError):
        _engine().evaluate_assessment(age=12, features=_features())


def test_assessment_age_gating_applies():
    """Age gating still applies: a 15-year-old never matches the 18+ rule."""
    features = _features(cyclical_pain_ratio_90d=0.8, dyspareunia=True)
    minor = _engine().evaluate_assessment(age=15, features=features)
    assert "endo-indicator-adult" not in minor.indicators
    adult = _engine().evaluate_assessment(age=25, features=features)
    assert "endo-indicator-adult" in adult.indicators
