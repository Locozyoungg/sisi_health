"""Cervical screening & navigation red-flag rules (spec 5.4.1). DoD requires at
least 25 cases including thresholds and age gating, plus a test that no band is
ever lowered when a red flag is present. All four rules ship
clinically_validated=false; a minor reporting post-coital bleeding is a
safeguarding signal and the band is floored at ORANGE (hazard C5)."""

import random

from app.config import get_settings
from app.core.errors import ValidationError
from app.rules.bands import SEVERITY
from app.rules.loader import build_engine


def _features(**overrides):
    base = {
        "max_pain_90d": 3,
        "avg_pain_90d": 1.0,
        "cyclical_pain_ratio_90d": 0.2,
        "avg_bleeding_volume_90d": 1.0,
        "fatigue_ratio_30d": 0.1,
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


def _eval(age: int, **features):
    return _engine().evaluate(age=age, diary_days=60, features=_features(**features))


# --- Post-coital bleeding (min_age 18, ORANGE) ---


def test_postcoital_adult_matches_orange():
    result = _eval(age=25, postcoital_bleeding_signal=True)
    assert result.band == "ORANGE"
    assert result.indicators == ["redflag-postcoital-bleeding"]
    assert result.urgent is True
    assert result.safeguarding is False


def test_postcoital_min_age_boundary_18():
    result = _eval(age=18, postcoital_bleeding_signal=True)
    assert "redflag-postcoital-bleeding" in result.indicators
    assert result.safeguarding is False  # exactly 18 is not a minor


def test_postcoital_minor_floors_to_orange_with_safeguarding():
    result = _eval(age=17, postcoital_bleeding_signal=True)
    assert result.band == "ORANGE"  # floor, not a rule match
    assert result.indicators == []
    assert result.urgent is False
    assert result.safeguarding is True


def test_postcoital_minor_13_floors():
    result = _eval(age=13, postcoital_bleeding_signal=True)
    assert result.band == "ORANGE"
    assert result.safeguarding is True


def test_postcoital_minor_floor_never_lowers_red():
    """Floor raises GREEN->ORANGE but never lowers an existing RED."""
    result = _eval(age=17, postcoital_bleeding_signal=True, max_pain_90d=9)
    assert result.band == "RED"
    assert result.indicators == ["redflag-severe-acute-pain"]
    assert result.safeguarding is True


def test_postcoital_minor_with_self_harm_is_red():
    result = _eval(age=17, postcoital_bleeding_signal=True, self_harm_signal=True)
    assert result.band == "RED"
    assert result.indicators == ["redflag-self-harm"]
    assert result.safeguarding is True


def test_postcoital_missing_input_matches_via_asymmetry():
    result = _eval(age=25, postcoital_bleeding_signal=None)
    assert result.band == "ORANGE"
    assert "redflag-postcoital-bleeding" in result.indicators


def test_postcoital_wrong_type_matches_via_asymmetry():
    result = _eval(age=25, postcoital_bleeding_signal="yes")  # type: ignore[arg-type]
    assert result.band == "ORANGE"
    assert "redflag-postcoital-bleeding" in result.indicators


def test_minor_without_postcoital_has_no_floor():
    result = _eval(age=17)
    assert result.band == "GREEN"
    assert result.safeguarding is False


# --- Intermenstrual bleeding (min_age 13, ORANGE) ---


def test_intermenstrual_adult_matches_orange():
    result = _eval(age=24, intermenstrual_bleeding_signal=True)
    assert result.band == "ORANGE"
    assert result.indicators == ["redflag-intermenstrual-bleeding"]
    assert result.urgent is True
    assert result.safeguarding is False


def test_intermenstrual_min_age_boundary_13():
    result = _eval(age=13, intermenstrual_bleeding_signal=True)
    assert "redflag-intermenstrual-bleeding" in result.indicators
    assert result.safeguarding is False


def test_intermenstrual_false_is_control():
    result = _eval(age=24)
    assert "redflag-intermenstrual-bleeding" not in result.indicators
    assert result.band == "GREEN"


def test_intermenstrual_missing_input_matches_via_asymmetry():
    result = _eval(age=24, intermenstrual_bleeding_signal=None)
    assert result.band == "ORANGE"
    assert "redflag-intermenstrual-bleeding" in result.indicators


# --- Post-menopausal bleeding (min_age 45, ORANGE) ---


def test_postmenopausal_boundary_45_matches():
    result = _eval(age=45, postmenopausal_bleeding_signal=True)
    assert result.band == "ORANGE"
    assert result.indicators == ["redflag-postmenopausal-bleeding"]
    assert result.urgent is True


def test_postmenopausal_gated_at_44():
    result = _eval(age=44, postmenopausal_bleeding_signal=True)
    assert "redflag-postmenopausal-bleeding" not in result.indicators
    assert result.band == "GREEN"


def test_postmenopausal_adult_matches():
    result = _eval(age=60, postmenopausal_bleeding_signal=True)
    assert "redflag-postmenopausal-bleeding" in result.indicators
    assert result.safeguarding is False


def test_postmenopausal_missing_input_matches_via_asymmetry():
    result = _eval(age=50, postmenopausal_bleeding_signal=None)
    assert result.band == "ORANGE"
    assert "redflag-postmenopausal-bleeding" in result.indicators


# --- Persistent discharge (>=5 days in 90, ORANGE) ---


def test_discharge_at_threshold_5_matches():
    result = _eval(age=24, unusual_discharge_days_90d=5)
    assert result.band == "ORANGE"
    assert result.indicators == ["redflag-persistent-discharge"]
    assert result.urgent is True


def test_discharge_below_threshold_4_does_not_match():
    result = _eval(age=24, unusual_discharge_days_90d=4)
    assert "redflag-persistent-discharge" not in result.indicators
    assert result.band == "GREEN"


def test_discharge_above_threshold_matches():
    result = _eval(age=24, unusual_discharge_days_90d=10)
    assert "redflag-persistent-discharge" in result.indicators


def test_discharge_minor_matches_without_safeguarding():
    result = _eval(age=16, unusual_discharge_days_90d=5)
    assert "redflag-persistent-discharge" in result.indicators
    assert result.safeguarding is False


def test_discharge_missing_input_matches_via_asymmetry():
    result = _eval(age=25, unusual_discharge_days_90d=None)
    assert result.band == "ORANGE"
    assert "redflag-persistent-discharge" in result.indicators


def test_discharge_wrong_type_matches_via_asymmetry():
    result = _eval(age=25, unusual_discharge_days_90d="five")  # type: ignore[arg-type]
    assert result.band == "ORANGE"
    assert "redflag-persistent-discharge" in result.indicators


# --- Combinations and escalation ---


def test_postcoital_plus_heavy_bleeding_dizziness_is_red():
    """Spec 5.4.1: combined with heavy bleeding + dizziness the existing urgent
    rule applies."""
    result = _eval(
        age=25,
        postcoital_bleeding_signal=True,
        avg_bleeding_volume_90d=3.5,
        dizziness_signal=True,
    )
    assert result.band == "RED"
    assert "redflag-heavy-bleeding-dizziness" in result.indicators
    assert "redflag-postcoital-bleeding" in result.indicators


def test_minor_postcoital_plus_heavy_bleeding_dizziness_is_red_and_safeguarding():
    result = _eval(
        age=17,
        postcoital_bleeding_signal=True,
        avg_bleeding_volume_90d=3.5,
        dizziness_signal=True,
    )
    assert result.band == "RED"
    assert result.safeguarding is True


def test_all_four_cervical_signals_at_50():
    result = _eval(
        age=50,
        postcoital_bleeding_signal=True,
        intermenstrual_bleeding_signal=True,
        postmenopausal_bleeding_signal=True,
        unusual_discharge_days_90d=8,
    )
    assert result.band == "ORANGE"
    assert set(result.indicators) == {
        "redflag-postcoital-bleeding",
        "redflag-intermenstrual-bleeding",
        "redflag-postmenopausal-bleeding",
        "redflag-persistent-discharge",
    }


def test_cervical_signals_with_insufficient_data():
    """The 14-day gate still applies first (documented behavior, consistent with
    self-harm handling)."""
    result = _engine().evaluate(
        age=17, diary_days=10, features=_features(postcoital_bleeding_signal=True)
    )
    assert result.band == "NOT_ENOUGH_DATA"


def test_age_12_rejected_even_with_cervical_signals():
    import pytest

    with pytest.raises(ValidationError):
        _engine().evaluate(
            age=12, diary_days=60, features=_features(intermenstrual_bleeding_signal=True)
        )


# --- Property: adding a red-flag signal never lowers the band ---

CERVICAL_RED_FLAG_TRIGGERS = [
    ("postcoital_bleeding_signal", True),
    ("intermenstrual_bleeding_signal", True),
    ("postmenopausal_bleeding_signal", True),
    ("unusual_discharge_days_90d", 5),
]


def _random_mild_features(rng: random.Random) -> dict:
    features = _features()
    features["max_pain_90d"] = rng.randint(0, 6)
    features["avg_pain_90d"] = round(rng.uniform(0, 4), 1)
    features["avg_bleeding_volume_90d"] = round(rng.uniform(0, 2.5), 1)
    features["fatigue_ratio_30d"] = round(rng.uniform(0, 0.6), 1)
    features["cyclical_pain_ratio_90d"] = round(rng.uniform(0, 0.5), 1)
    features["unusual_discharge_days_90d"] = rng.randint(0, 4)
    return features


def test_adding_cervical_red_flag_never_lowers_band():
    """Property sweep: for random mild inputs and ages, turning on any cervical
    red-flag signal can never lower the band (safety asymmetry, spec 7)."""
    engine = _engine()
    for seed in range(50):
        rng = random.Random(seed)  # noqa: S311 — property-test generator, not crypto
        age = rng.randint(13, 60)
        base = _random_mild_features(rng)
        before = engine.evaluate(age=age, diary_days=60, features=base).band
        for key, trigger in CERVICAL_RED_FLAG_TRIGGERS:
            triggered = dict(base)
            triggered[key] = trigger
            after = engine.evaluate(age=age, diary_days=60, features=triggered).band
            assert SEVERITY[after] >= SEVERITY[before], (
                f"seed={seed} age={age} key={key}: band lowered {before} -> {after}"
            )


def test_minor_postcoital_band_floor_across_random_bases():
    """Property sweep: a minor with a post-coital signal always gets >= ORANGE."""
    engine = _engine()
    for seed in range(50):
        rng = random.Random(seed)  # noqa: S311 — property-test generator, not crypto
        age = rng.randint(13, 17)
        base = _random_mild_features(rng)
        base["postcoital_bleeding_signal"] = True
        result = engine.evaluate(age=age, diary_days=60, features=base)
        assert SEVERITY[result.band] >= SEVERITY["ORANGE"], f"seed={seed}: {result.band}"
        assert result.safeguarding is True
