"""k-anonymity for school aggregates (spec 3.4, design decision 3.4). ONE shared
module — no other code may compute school aggregates.

Rules:
- any cell with fewer than MIN_K (5) is suppressed, with COMPLEMENTARY
  suppression so subtraction cannot reveal it
- a school reports nothing until MIN_STUDENTS (20) assessments exist in the term
- below threshold the dashboard shows "not enough data yet", never a zero
Property tests (tests/test_k_anon.py) verify differencing resistance."""

from dataclasses import dataclass, field
from typing import Any

MIN_K = 5
MIN_STUDENTS = 20
NOT_ENOUGH = "not_enough_data"


@dataclass(frozen=True)
class Cell:
    key: tuple[Any, ...]
    value: int


@dataclass(frozen=True)
class Suppressed:
    """A published cell: either a real count or a suppressed marker."""

    value: int | None  # None = suppressed
    suppressed: bool = False


@dataclass
class KAnonResult:
    enough_data: bool
    cells: dict[tuple[Any, ...], Suppressed] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        """Serializable form. Suppressed cells render as None; callers must show
        'not enough data yet' when enough_data is False — never a zero."""
        return {
            "enough_data": self.enough_data,
            "message": None if self.enough_data else NOT_ENOUGH,
            "cells": {
                "|".join(str(part) for part in key): (None if cell.suppressed else cell.value)
                for key, cell in sorted(self.cells.items(), key=lambda item: item[0])
            },
        }


def apply_k_anon(total: int, counts: list[Cell]) -> KAnonResult:
    """Suppress cells < MIN_K with complementary suppression.

    total = the denominator the cells partition (e.g., assessments in the term).
    Complementary suppression: if a cell is suppressed, at least one OTHER cell
    is also suppressed, so `total - published_sum` can never isolate a single
    suppressed value."""
    result = KAnonResult(enough_data=total >= MIN_STUDENTS)
    if not result.enough_data:
        return result  # nothing published at all below MIN_STUDENTS

    suppressed_keys: set[tuple[Any, ...]] = set()
    for cell in counts:
        if 0 < cell.value < MIN_K:
            suppressed_keys.add(cell.key)

    # Complementary suppression: ensure at least two suppressed cells (or the
    # published remainder hides everything). If only one small cell exists, we
    # must also suppress the smallest remaining cell so subtraction cannot
    # reveal either value.
    if len(suppressed_keys) == 1:
        visible = [c for c in counts if c.key not in suppressed_keys and c.value > 0]
        if visible:
            smallest = min(visible, key=lambda c: (c.value, c.key))
            suppressed_keys.add(smallest.key)

    for cell in counts:
        if cell.key in suppressed_keys:
            result.cells[cell.key] = Suppressed(value=None, suppressed=True)
        else:
            result.cells[cell.key] = Suppressed(value=cell.value, suppressed=False)
    return result


def differencing_leak(total: int, published: dict[tuple[Any, ...], Suppressed]) -> bool:
    """True if any suppressed cell's value can be derived by subtracting the
    published cells from the total. This is the property the tests attack."""
    published_sum = sum(c.value or 0 for c in published.values() if not c.suppressed)
    suppressed = [c for c in published.values() if c.suppressed]
    if len(suppressed) == 1:
        remainder = total - published_sum
        return 0 < remainder < MIN_K
    return False
