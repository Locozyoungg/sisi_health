"""Engine operator coverage: every DSL operator branch in the band/red-flag path."""

from app.rules.bands import Band
from app.rules.engine import RuleEngine
from app.rules.schemas import ChangelogEntry, Evidence, LogicNode, Rule, RuleInput


def _rule(rule_id: str, logic: LogicNode, output_band: Band, red_flag: bool = False) -> Rule:
    return Rule(
        id=rule_id,
        version="1.0.0",
        condition="test_indicator",
        min_age=13,
        red_flag=red_flag,
        priority=50,
        inputs=[RuleInput(name="x", type="numeric"), RuleInput(name="flag", type="boolean")],
        logic=logic,
        output_band=output_band,
        evidence=[Evidence(title="test", source_type="other")],
        clinically_validated=False,
        changelog=[ChangelogEntry(version="1.0.0", note="test")],
    )


def _eval(rule: Rule, features: dict, red_flag: bool | None = None) -> bool:
    engine = RuleEngine([rule], rule_set_version="test", allow_unvalidated=True)
    result = engine.evaluate(age=20, diary_days=30, features=features)
    return rule.id in result.indicators


def test_op_in():
    rule = _rule("t-in", LogicNode(op="in", input="x", values=[1, 2, 3]), Band.YELLOW)
    assert _eval(rule, {"x": 2}) is True
    assert _eval(rule, {"x": 9}) is False


def test_op_between():
    rule = _rule("t-between", LogicNode(op="between", input="x", values=[3, 7]), Band.YELLOW)
    assert _eval(rule, {"x": 3}) is True
    assert _eval(rule, {"x": 7}) is True
    assert _eval(rule, {"x": 8}) is False


def test_op_neq_and_boolean_eq():
    neq = _rule("t-neq", LogicNode(op="neq", input="flag", value=True), Band.YELLOW)
    assert _eval(neq, {"flag": False}) is True
    assert _eval(neq, {"flag": True}) is False
    eq_false = _rule("t-eq-false", LogicNode(op="eq", input="flag", value=False), Band.YELLOW)
    assert _eval(eq_false, {"flag": False}) is True


def test_op_gt_lt():
    gt = _rule("t-gt", LogicNode(op="gt", input="x", value=5), Band.YELLOW)
    assert _eval(gt, {"x": 6}) is True
    assert _eval(gt, {"x": 5}) is False
    lt = _rule("t-lt", LogicNode(op="lt", input="x", value=5), Band.YELLOW)
    assert _eval(lt, {"x": 4}) is True
    lte = _rule("t-lte", LogicNode(op="lte", input="x", value=5), Band.YELLOW)
    assert _eval(lte, {"x": 5}) is True


def test_numeric_never_compares_to_boolean():
    weird = _rule("t-weird", LogicNode(op="gte", input="x", value=True), Band.YELLOW)
    assert _eval(weird, {"x": 3}) is False


def test_wrong_type_input_on_red_flag_matches():
    rf = _rule(
        "t-rf",
        LogicNode(op="gte", input="x", value=5),
        Band.RED,
        red_flag=True,
    )
    engine = RuleEngine([rf], rule_set_version="test", allow_unvalidated=True)
    result = engine.evaluate(age=20, diary_days=30, features={"x": "not-a-number"})
    assert result.band == "RED"
    assert result.urgent is True


def test_boolean_input_wrong_op_returns_unmatched_or_redflag():
    rule = _rule("t-boolop", LogicNode(op="gte", input="flag", value=1), Band.YELLOW)
    assert _eval(rule, {"flag": True}) is False  # boolean under a numeric op: unmatched


def test_engine_rule_ids_property():
    rule = _rule("t-ids", LogicNode(op="gte", input="x", value=1), Band.YELLOW)
    engine = RuleEngine([rule], rule_set_version="test", allow_unvalidated=True)
    assert engine.rule_ids == ["t-ids"]


def test_comparison_missing_input_raises():
    import pytest

    from app.core.errors import ValidationError

    rule = _rule("t-noinput", LogicNode(op="gte", input=None, value=1), Band.YELLOW)  # type: ignore[arg-type]
    engine = RuleEngine([rule], rule_set_version="test", allow_unvalidated=True)
    with pytest.raises(ValidationError, match="missing input"):
        engine.evaluate(age=20, diary_days=30, features={"x": 1})


def test_comparison_without_value_is_unmatched():
    rule = _rule("t-novalue", LogicNode(op="gte", input="x", value=None), Band.YELLOW)
    assert _eval(rule, {"x": 3}) is False


def test_not_and_or_combinators():
    n = _rule(
        "t-not",
        LogicNode(op="not", operands=[LogicNode(op="eq", input="flag", value=True)]),
        Band.YELLOW,
    )
    assert _eval(n, {"flag": False}) is True
    o = _rule(
        "t-or",
        LogicNode(
            op="or",
            operands=[
                LogicNode(op="gte", input="x", value=9),
                LogicNode(op="eq", input="flag", value=True),
            ],
        ),
        Band.ORANGE,
    )
    assert _eval(o, {"x": 2, "flag": True}) is True
    assert _eval(o, {"x": 2, "flag": False}) is False
