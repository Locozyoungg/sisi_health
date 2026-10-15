"""Red-flag asymmetry (spec 7): no input combination lowers a band when a red-flag
symptom is present; uncertainty on red-flag inputs resolves to matched."""

from app.config import get_settings
from app.rules.loader import build_engine


def _features(**overrides):
    base = {
        "max_pain_90d": 1,
        "avg_pain_90d": 0.5,
        "cyclical_pain_ratio_90d": 0.1,
        "avg_bleeding_volume_90d": 0.5,
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


def test_missing_red_flag_input_counts_as_matched():
    """Safety asymmetry: if a red-flag input is missing, the rule matches (higher band)."""
    features = _features(max_pain_90d=None)
    result = _engine().evaluate(age=24, diary_days=30, features=features)
    assert result.band == "RED"
    assert "redflag-severe-acute-pain" in result.indicators
    assert result.urgent is True


def test_wrong_type_red_flag_input_counts_as_matched():
    features = _features(max_pain_90d="ten")  # type: ignore[arg-type]
    result = _engine().evaluate(age=24, diary_days=30, features=features)
    assert result.band == "RED"


def test_missing_regular_input_does_not_match():
    """Uncertainty on regular (non-red-flag) inputs resolves to not matched."""
    features = _features(avg_bleeding_volume_90d=3.0, fatigue_ratio_30d=None)
    result = _engine().evaluate(age=24, diary_days=30, features=features)
    assert "anemia-risk-flag" not in result.indicators
    # PCOS: irregularity missing -> rule cannot confirm
    pcos = _features(cycle_irregularity_90d=None, androgenic_symptoms=True)
    assert (
        "pcos-indicator" not in _engine().evaluate(age=24, diary_days=30, features=pcos).indicators
    )


def test_red_flag_dominates_green_pattern():
    """gc-12 invariant, direct: mild pattern + severe pain -> RED, never lower."""
    result = _engine().evaluate(age=24, diary_days=30, features=_features(max_pain_90d=9))
    assert result.band == "RED"


def test_red_flag_rule_band_cannot_be_green():
    """Validator rejects red-flag rules below ORANGE."""
    import json

    import pytest

    from app.rules.validator import RuleValidationError, validate_rule_dict

    rule = json.loads(
        (get_settings().ontology_dir / "rules" / "redflag-self-harm.json").read_text()
    )
    rule["output_band"] = "GREEN"
    with pytest.raises(RuleValidationError, match="ORANGE or RED"):
        validate_rule_dict(rule)


def test_threshold_boundaries():
    """Boundary cases at every threshold: gte is inclusive."""
    engine = _engine()
    # anemia: bleeding >= 3 and fatigue >= 0.5 — exactly at threshold matches
    at = _features(avg_bleeding_volume_90d=3.0, fatigue_ratio_30d=0.5)
    assert "anemia-risk-flag" in engine.evaluate(age=24, diary_days=30, features=at).indicators
    below = _features(avg_bleeding_volume_90d=2.9, fatigue_ratio_30d=0.5)
    assert (
        "anemia-risk-flag" not in engine.evaluate(age=24, diary_days=30, features=below).indicators
    )
    # severe pain: NRS 9 matches, 8 does not
    assert (
        "redflag-severe-acute-pain"
        in engine.evaluate(age=24, diary_days=30, features=_features(max_pain_90d=9)).indicators
    )
    assert (
        "redflag-severe-acute-pain"
        not in engine.evaluate(age=24, diary_days=30, features=_features(max_pain_90d=8)).indicators
    )
