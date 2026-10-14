"""Property tests for the k-anonymity module (spec 3.4 DoD): differencing
attacks must never reveal a suppressed cell; small cells are suppressed with
complementary suppression; below MIN_STUDENTS nothing is published at all."""

import random

import pytest

from app.k_anon import (
    MIN_K,
    MIN_STUDENTS,
    NOT_ENOUGH,
    Cell,
    apply_k_anon,
    differencing_leak,
)


def _random_cells(rng: random.Random, n: int, cap: int) -> list[Cell]:
    return [Cell(key=(i,), value=rng.randint(0, cap)) for i in range(n)]


def test_below_min_students_publishes_nothing():
    result = apply_k_anon(total=MIN_STUDENTS - 1, counts=[Cell(("a",), 15)])
    assert result.enough_data is False
    assert result.cells == {}
    assert result.public()["message"] == NOT_ENOUGH


def test_at_min_students_publishes():
    result = apply_k_anon(total=MIN_STUDENTS, counts=[Cell(("a",), 20)])
    assert result.enough_data is True
    assert result.cells[("a",)].value == 20


def test_small_cells_are_suppressed_with_complementary_partner():
    """a=3 forces suppression of b=17 too — publishing 17 alone would let
    subtraction reveal 3."""
    counts = [Cell(("a",), 3), Cell(("b",), 17)]
    result = apply_k_anon(total=20, counts=counts)
    assert result.cells[("a",)].suppressed is True
    assert result.cells[("b",)].suppressed is True
    assert not differencing_leak(20, result.cells)


def test_single_small_cell_gets_complementary_suppression():
    """One small cell forces a second suppression so subtraction cannot reveal it."""
    counts = [Cell(("a",), 4), Cell(("b",), 16)]
    result = apply_k_anon(total=20, counts=counts)
    suppressed = [k for k, c in result.cells.items() if c.suppressed]
    assert len(suppressed) == 2
    assert not differencing_leak(20, result.cells)


@pytest.mark.parametrize("seed", range(50))
def test_differencing_attacks_never_reveal(seed):
    rng = random.Random(seed)  # noqa: S311 — property-test generator, not crypto
    for _ in range(20):
        counts = _random_cells(rng, n=rng.randint(2, 10), cap=25)
        total = sum(c.value for c in counts)
        if total < MIN_STUDENTS:
            result = apply_k_anon(total, counts)
            assert result.cells == {}
            continue
        result = apply_k_anon(total, counts)
        assert not differencing_leak(total, result.cells), (
            f"seed={seed} counts={counts} cells={result.cells}"
        )
        # No published cell may be 1..MIN_K-1 (unless suppressed).
        for _key, cell in result.cells.items():
            if not cell.suppressed:
                assert cell.value == 0 or cell.value >= MIN_K


def test_zero_cells_are_published_as_zero():
    """Zeros are fine to publish — they reveal nothing about individuals."""
    result = apply_k_anon(total=20, counts=[Cell(("a",), 0), Cell(("b",), 20)])
    assert result.cells[("a",)].value == 0
    assert result.cells[("a",)].suppressed is False
