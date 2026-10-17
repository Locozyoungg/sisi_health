"""Mutation sweep over the 12 shipped rule JSONs (Phase 8, plan section 5).

The golden suite proves the shipped rules produce the expected answers; it does
not prove the suite would notice if a rule changed. This sweep mutates every
logic node of every shipped rule — comparison operators swapped for a sibling
(gte <-> gt <-> lte <-> lt, eq <-> neq), numeric thresholds shifted by +/-1, and
boolean values flipped — rebuilds a single-rule engine from the mutant, and
compares its indicator set against the unmutated rule's.

A mutant is KILLED when any observation differs. The observation set is:

1. all 37 golden cases, evaluated through ``evaluate_assessment`` so the
   14-diary-day gate (an orthogonal diary rule) cannot mask rule logic; and
2. a deterministic boundary grid derived from the rule itself: every declared
   numeric input gets {threshold - 1, threshold, threshold + 1} and every
   boolean input gets {False, True}, combined exhaustively at the rule's
   ``min_age``.

The grid is what makes operator mutations observable at the exact boundary:
``gte -> gt`` only differs when an input equals the threshold, and the golden
cases happen not to hit every threshold exactly. Without it those mutants would
survive for an uninteresting reason (untested boundary) rather than because the
rule is equivalent. Mutants that survive are listed in the failure message —
the sweep asserts 100% killed, so any survivor is a test-coverage gap.

No new dependencies; deterministic; no database.
"""

from __future__ import annotations

import copy
import itertools
import json
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.rules.engine import RuleEngine
from app.rules.schemas import Rule

RULES_DIR = get_settings().ontology_dir / "rules"
GOLDEN = json.loads(
    (get_settings().ontology_dir / "golden" / "cases.json").read_text(encoding="utf-8")
)
EXPECTED_RULE_COUNT = 12

# Same arity groups: an operator is only replaced by a sibling that accepts the
# same node shape, so every mutant stays a valid rule.
COMPARISON_SIBLINGS: dict[str, tuple[str, ...]] = {
    "gte": ("gt", "lte", "lt"),
    "gt": ("gte", "lte", "lt"),
    "lte": ("gte", "gt", "lt"),
    "lt": ("gte", "gt", "lte"),
    "eq": ("neq",),
    "neq": ("eq",),
}


def _walk(node: dict[str, Any], path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    yield path, node
    for index, child in enumerate(node.get("operands") or []):
        yield from _walk(child, f"{path}.operands[{index}]")


def _node_at(rule_dict: dict[str, Any], path: str) -> dict[str, Any]:
    """Resolve a dotted/indexed path ("logic.operands[0].operands[1]")."""
    node: Any = rule_dict
    for part in path.split("."):
        match = re.fullmatch(r"([^\[\]]+)((?:\[\d+\])*)", part)
        assert match is not None, f"bad node path: {path}"
        node = node[match.group(1)]
        for index in re.findall(r"\[(\d+)\]", match.group(2)):
            node = node[int(index)]
    return node


def _iter_mutants(rule_dict: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """One mutation per yield: (mutant id, cloned rule dict)."""
    rule_id = rule_dict["id"]
    for path, node in _walk(rule_dict["logic"], "logic"):
        op = node["op"]
        for sibling in COMPARISON_SIBLINGS.get(op, ()):
            mutant = copy.deepcopy(rule_dict)
            _node_at(mutant, path)["op"] = sibling
            yield f"{rule_id}:{path}:op {op}->{sibling}", mutant

        value = node.get("value")
        if isinstance(value, bool):
            mutant = copy.deepcopy(rule_dict)
            _node_at(mutant, path)["value"] = not value
            yield f"{rule_id}:{path}:value {value}->{not value}", mutant
        elif isinstance(value, (int, float)):
            for delta in (1, -1):
                mutant = copy.deepcopy(rule_dict)
                _node_at(mutant, path)["value"] = value + delta
                yield f"{rule_id}:{path}:value {value}->{value + delta}", mutant

        # "in"/"between" value lists: keep the sweep honest if a future rule uses
        # them (the 12 shipped rules do not). Booleans inside a list are not
        # shifted; they are covered by the boolean flip above only for scalars.
        for index, entry in enumerate(node.get("values") or []):
            if isinstance(entry, bool) or not isinstance(entry, (int, float)):
                continue
            for delta in (1, -1):
                mutant = copy.deepcopy(rule_dict)
                _node_at(mutant, path)["values"][index] = entry + delta
                yield (
                    f"{rule_id}:{path}.values[{index}]:{entry}->{entry + delta}",
                    mutant,
                )


def _thresholds(rule_dict: dict[str, Any]) -> tuple[dict[str, set[float]], dict[str, set[bool]]]:
    numeric: dict[str, set[float]] = {}
    boolean: dict[str, set[bool]] = {}
    for _, node in _walk(rule_dict["logic"], "logic"):
        name = node.get("input")
        value = node.get("value")
        if name is None:
            continue
        if isinstance(value, bool):
            boolean.setdefault(name, set()).update({False, True})
        elif isinstance(value, (int, float)):
            numeric.setdefault(name, set()).update({value - 1, value, value + 1})
    return numeric, boolean


def _boundary_features(rule_dict: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Exhaustive boundary grid over the rule's declared inputs."""
    numeric, boolean = _thresholds(rule_dict)
    names: list[str] = []
    domains: list[list[Any]] = []
    for entry in rule_dict["inputs"]:
        name = entry["name"]
        names.append(name)
        if entry["type"] == "boolean":
            domains.append([False, True])
        else:
            thresholds = numeric.get(name)
            domains.append(sorted(thresholds) if thresholds else [0])
    for combination in itertools.product(*domains):
        yield dict(zip(names, combination, strict=False))


def _observation_inputs(rule_dict: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Fixed (age, features) list for one rule — shared by every mutant.

    Built from the UNMUTATED rule: if a mutant's own thresholds were used to
    build the grid, the two observation lists would be aligned against different
    inputs and the comparison would be meaningless.
    """
    inputs = [(case["age"], case["features"]) for case in GOLDEN["cases"]]
    inputs.extend(
        (rule_dict["min_age"], features) for features in _boundary_features(rule_dict)
    )
    return inputs


def _observations(
    rule: Rule, observation_inputs: list[tuple[int, dict[str, Any]]]
) -> list[frozenset[str]]:
    """Indicator set for every golden case plus every boundary-grid assignment."""
    engine = RuleEngine([rule], rule_set_version="mutation", allow_unvalidated=True)
    return [
        frozenset(engine.evaluate_assessment(age=age, features=features).indicators)
        for age, features in observation_inputs
    ]


def _rule_dicts() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(RULES_DIR.glob("*.json"))
    ]


@lru_cache(maxsize=1)
def sweep() -> tuple[int, list[str]]:
    """Run the whole sweep once. Returns (total mutants, surviving mutant ids)."""
    total = 0
    survivors: list[str] = []
    for rule_dict in _rule_dicts():
        base_rule = Rule.model_validate(rule_dict)
        observation_inputs = _observation_inputs(rule_dict)
        baseline = _observations(base_rule, observation_inputs)
        mutants = list(_iter_mutants(rule_dict))
        assert mutants, f"{rule_dict['id']}: no logic nodes to mutate"
        for mutant_id, mutant_dict in mutants:
            total += 1
            mutant_rule = Rule.model_validate(mutant_dict)
            if _observations(mutant_rule, observation_inputs) == baseline:
                survivors.append(mutant_id)
    return total, survivors


def test_sweep_covers_every_shipped_rule():
    assert len(_rule_dicts()) == EXPECTED_RULE_COUNT


def test_every_logic_mutant_is_killed():
    total, survivors = sweep()
    assert total > 0
    assert not survivors, (
        f"{len(survivors)}/{total} rule mutants survived (indicator set unchanged on "
        f"all 37 golden cases and the boundary grid): {survivors}"
    )
