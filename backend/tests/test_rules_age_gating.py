"""Age gating and the clinically_validated sign-off protocol (non-negotiable 3)."""

import json

import pytest

from app.config import get_settings
from app.rules.loader import build_engine
from app.rules.validator import RuleValidationError, validate_rule_dict


def _features(cyclical: float | None, dyschezia: bool, dyspareunia: bool):
    return {
        "max_pain_90d": 7,
        "avg_pain_90d": 4.0,
        "cyclical_pain_ratio_90d": cyclical,
        "avg_bleeding_volume_90d": 2.0,
        "fatigue_ratio_30d": 0.4,
        "cycle_irregularity_90d": None,
        "dyschezia": dyschezia,
        "dyspareunia": dyspareunia,
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


def test_minor_never_matches_adult_rule():
    """Same features: a 15-year-old matches only the all-ages endo rule even when a
    dyspareunia signal is present in the feature dict; an adult matches both."""
    engine = build_engine(get_settings().ontology_dir, allow_unvalidated=True)
    minor = engine.evaluate(age=15, diary_days=75, features=_features(0.8, True, True))
    adult = engine.evaluate(age=25, diary_days=75, features=_features(0.8, True, True))
    assert minor.indicators == ["endo-indicator"]
    assert sorted(adult.indicators) == ["endo-indicator", "endo-indicator-adult"]


def test_rule_min_age_boundary():
    """min_age is inclusive: a rule with min_age 18 applies at exactly 18."""
    engine = build_engine(get_settings().ontology_dir, allow_unvalidated=True)
    features = _features(0.8, False, True)
    at18 = engine.evaluate(age=18, diary_days=60, features=features)
    assert "endo-indicator-adult" in at18.indicators


def test_validator_rejects_min_age_below_13():
    data = json.loads((get_settings().ontology_dir / "rules" / "anemia-risk-flag.json").read_text())
    data["min_age"] = 12
    with pytest.raises(RuleValidationError):
        validate_rule_dict(data)


def test_validated_requires_signoff_fields():
    data = json.loads((get_settings().ontology_dir / "rules" / "anemia-risk-flag.json").read_text())
    data["clinically_validated"] = True
    with pytest.raises(RuleValidationError, match="reviewer"):
        validate_rule_dict(data)
    data["reviewer_name"] = "Dr. Placeholder"
    data["reviewer_registration_no"] = "KMPDC/0000"
    data["signed_at"] = "2026-10-14T00:00:00Z"
    validate_rule_dict(data)  # passes


def test_unvalidated_must_have_empty_signoff():
    data = json.loads((get_settings().ontology_dir / "rules" / "anemia-risk-flag.json").read_text())
    data["reviewer_name"] = "Dr. Placeholder"
    with pytest.raises(RuleValidationError, match="empty sign-off"):
        validate_rule_dict(data)


def test_all_shipped_rules_are_unvalidated():
    """Every rule in /ontology ships clinically_validated=false with empty sign-off."""
    for path in sorted((get_settings().ontology_dir / "rules").glob("*.json")):
        data = json.loads(path.read_text())
        assert data["clinically_validated"] is False, path.name
        assert data["reviewer_name"] is None, path.name
        assert data["reviewer_registration_no"] is None, path.name
        assert data["signed_at"] is None, path.name
        assert data["evidence"], path.name
