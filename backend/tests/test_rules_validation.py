"""Rule validation: schema + semantic checks catch broken rules before the engine."""

import json

import pytest

from app.config import get_settings
from app.rules.validator import RuleValidationError, validate_rule_dict


def _load(rule_id: str) -> dict:
    return json.loads((get_settings().ontology_dir / "rules" / f"{rule_id}.json").read_text())


def test_all_shipped_rules_validate():
    for path in sorted((get_settings().ontology_dir / "rules").glob("*.json")):
        validate_rule_dict(json.loads(path.read_text()))  # must not raise


def test_missing_evidence_rejected():
    data = _load("anemia-risk-flag")
    del data["evidence"]
    with pytest.raises(RuleValidationError):
        validate_rule_dict(data)


def test_unknown_operator_rejected():
    data = _load("anemia-risk-flag")
    data["logic"] = {"op": "sqrt", "input": "max_pain_90d"}
    with pytest.raises(RuleValidationError):
        validate_rule_dict(data)


def test_undeclared_input_rejected():
    data = _load("anemia-risk-flag")
    data["inputs"] = [{"name": "avg_bleeding_volume_90d", "type": "numeric"}]
    with pytest.raises(RuleValidationError, match="undeclared"):
        validate_rule_dict(data)


def test_combinator_without_operands_rejected():
    data = _load("anemia-risk-flag")
    data["logic"] = {"op": "and"}
    with pytest.raises(RuleValidationError):
        validate_rule_dict(data)


def test_bad_version_format_rejected():
    data = _load("anemia-risk-flag")
    data["version"] = "v1"
    with pytest.raises(RuleValidationError):
        validate_rule_dict(data)
