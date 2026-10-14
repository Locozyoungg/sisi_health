"""The deterministic band engine. Invariants (all under test):
- red flags evaluate FIRST and a red-flag match can never lower the band
- safety asymmetry: a missing/invalid red-flag input counts as matched; for regular
  rules it counts as not matched
- fewer than 14 diary days -> NOT_ENOUGH_DATA, never a band
- users under 13 are rejected (blocked at the age check upstream, enforced again here)
- unvalidated rules refuse to run unless the dev/demo flag is on (non-negotiable 3)"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.errors import UnvalidatedRulesError, ValidationError
from app.core.time import utc_now
from app.rules.bands import NOT_ENOUGH_DATA, Band, max_band
from app.rules.schemas import Evaluation, LogicNode, Rule

MIN_DIARY_DAYS = 14
MIN_AGE = 13


class RuleEngine:
    def __init__(
        self, rules: Sequence[Rule], *, rule_set_version: str, allow_unvalidated: bool
    ) -> None:
        if not allow_unvalidated and any(not r.clinically_validated for r in rules):
            raise UnvalidatedRulesError(
                "one or more rules lack clinician sign-off; refusing to evaluate "
                "(set SISI_ALLOW_UNVALIDATED_RULES=true in dev/demo only)"
            )
        self._rules = sorted(rules, key=lambda r: (r.red_flag, r.priority), reverse=True)
        self._rule_set_version = rule_set_version
        self._allow_unvalidated = allow_unvalidated

    @property
    def rule_ids(self) -> list[str]:
        return [r.id for r in self._rules]

    def evaluate(self, *, age: int, diary_days: int, features: Mapping[str, Any]) -> Evaluation:
        if age < MIN_AGE:
            raise ValidationError("users under 13 are blocked")
        if diary_days < MIN_DIARY_DAYS:
            return Evaluation(
                band=NOT_ENOUGH_DATA,
                indicators=[],
                urgent=False,
                safeguarding=False,
                rule_set_version=self._rule_set_version,
                evaluated_at=utc_now(),
            )
        matches: list[Rule] = []
        for rule in self._rules:
            if age < rule.min_age:
                continue
            if self._eval_node(rule.logic, features, red_flag=rule.red_flag):
                matches.append(rule)
        matched_bands = [m.output_band for m in matches]
        final_band: str = max_band(matched_bands).value if matched_bands else Band.GREEN.value
        return Evaluation(
            band=final_band,
            indicators=sorted(m.id for m in matches),
            urgent=any(m.red_flag for m in matches),
            safeguarding=features.get("self_harm_signal") is True
            or any(m.condition == "self_harm" for m in matches),
            rule_set_version=self._rule_set_version,
            evaluated_at=utc_now(),
        )

    def _eval_node(self, node: LogicNode, features: Mapping[str, Any], *, red_flag: bool) -> bool:
        if node.op in ("and", "or"):
            results = [self._eval_node(c, features, red_flag=red_flag) for c in node.operands or []]
            return all(results) if node.op == "and" else any(results)
        if node.op == "not":
            return not self._eval_node((node.operands or [])[0], features, red_flag=red_flag)
        return self._compare(node, features, red_flag=red_flag)

    def _compare(self, node: LogicNode, features: Mapping[str, Any], *, red_flag: bool) -> bool:
        if node.input is None:
            raise ValidationError("comparison node missing input")
        value = features.get(node.input)
        if value is None:
            # Safety asymmetry: uncertainty on a red-flag input resolves to matched.
            return red_flag
        if isinstance(value, bool) and node.op in ("eq", "neq", "in"):
            return self._compare_scalar(node, value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return self._compare_scalar(node, value)
        return red_flag  # wrong type: uncertain -> matched only for red flags

    def _compare_scalar(self, node: LogicNode, value: float | bool) -> bool:
        op = node.op
        if op == "eq":
            return value == node.value
        if op == "neq":
            return value != node.value
        if op == "in":
            return value in (node.values or [])
        if op == "between" and isinstance(value, (int, float)):
            lo, hi = (node.values or [])[:2]
            return lo <= value <= hi
        if isinstance(value, (int, float)) and node.value is not None:
            other = float(node.value) if isinstance(node.value, (int, float)) else node.value
            if isinstance(other, bool):  # never compare numbers to booleans
                return False
            if op == "gte":
                return value >= other
            if op == "gt":
                return value > other
            if op == "lte":
                return value <= other
            if op == "lt":
                return value < other
        return False
