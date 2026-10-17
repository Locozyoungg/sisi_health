"""Rules engine vs the golden parity file (ontology/golden/cases.json). Every case
must produce the same band, indicators, and escalations on-device (Kotlin, Phase 2)
and here — a failing case blocks the merge (non-negotiable 8)."""

import json

import pytest

from app.config import get_settings
from app.core.errors import UnvalidatedRulesError, ValidationError
from app.rules.bands import Band, band_at_least
from app.rules.loader import build_engine

GOLDEN = json.loads(
    (get_settings().ontology_dir / "golden" / "cases.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def engine():
    return build_engine(get_settings().ontology_dir, allow_unvalidated=True)


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["id"])
def test_golden_cases(engine, case):
    result = engine.evaluate(
        age=case["age"], diary_days=case["diary_days"], features=case["features"]
    )
    assert result.band == case["expected_band"], (
        f"{case['id']}: band {result.band} != {case['expected_band']}"
    )
    assert sorted(result.indicators) == sorted(case["expected_indicators"]), case["id"]
    assert result.urgent == case["expected_escalations"]["urgent"], case["id"]
    assert result.safeguarding == case["expected_escalations"]["safeguarding"], case["id"]


def test_age_below_13_rejected(engine):
    with pytest.raises(ValidationError):
        engine.evaluate(age=12, diary_days=30, features={})


def test_unvalidated_rules_refuse_without_flag():
    """The engine refuses to run unvalidated rules unless the dev/demo flag is on."""
    with pytest.raises(UnvalidatedRulesError):
        build_engine(get_settings().ontology_dir, allow_unvalidated=False)


def test_band_at_least_orders_by_severity():
    """band_at_least is the safety floor used by the minor post-coital safeguard:
    ORANGE-or-above must be true at ORANGE and RED, false below."""
    assert band_at_least(Band.RED, Band.ORANGE) is True
    assert band_at_least(Band.ORANGE, Band.ORANGE) is True
    assert band_at_least(Band.YELLOW, Band.ORANGE) is False
    assert band_at_least(Band.GREEN, Band.GREEN) is True


def test_engine_loads_expected_rules(engine):
    assert set(engine.rule_ids) == {
        "anemia-risk-flag",
        "endo-indicator",
        "endo-indicator-adult",
        "fibroid-indicator",
        "pcos-indicator",
        "redflag-heavy-bleeding-dizziness",
        "redflag-severe-acute-pain",
        "redflag-self-harm",
        "redflag-postcoital-bleeding",
        "redflag-intermenstrual-bleeding",
        "redflag-postmenopausal-bleeding",
        "redflag-persistent-discharge",
    }
