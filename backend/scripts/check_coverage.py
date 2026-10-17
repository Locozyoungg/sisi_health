#!/usr/bin/env python
"""Rules coverage gate (Phase 8, plan section 5).

Runs the rules-related test files under the coverage plugin and enforces the
safety-critical floors:

- ``app/rules`` as a package: >= 80% line coverage
- ``app/rules/engine.py``, ``app/rules/bands.py``, ``app/rules/redflags.py``:
  100% line coverage each (band assignment and red-flag matching are safety
  invariants, not "best effort" code)

The run is scoped to the rules test files on purpose: the shared test database is
single-owner, and this gate must stay fast and deterministic in CI. Exit code 0
means every floor passed; anything else fails the build.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
COVERAGE_JSON = BACKEND_DIR / "coverage.json"

TEST_FILES = (
    "tests/test_rules_age_gating.py",
    "tests/test_rules_bands.py",
    "tests/test_rules_cervical.py",
    "tests/test_rules_ops.py",
    "tests/test_rules_redflags.py",
    "tests/test_rules_service.py",
    "tests/test_rules_validation.py",
    "tests/test_redflag_patterns.py",
    "tests/test_assessment_mode.py",
)

PACKAGE_PREFIX = "app/rules/"
PACKAGE_MIN_PERCENT = 80.0
REQUIRED_100 = (
    "app/rules/engine.py",
    "app/rules/bands.py",
    "app/rules/redflags.py",
)


def _normalise(path: str) -> str:
    """Coverage JSON uses OS-native separators; the gate compares POSIX paths."""
    return path.replace("\\", "/")


def _run_pytest() -> int:
    COVERAGE_JSON.unlink(missing_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        *TEST_FILES,
        "--cov=app",
        "--cov=app.rules",
        "--cov-report=json",
        "-q",
    ]
    # Fixed argv, no shell: the test file list is a module constant.
    completed = subprocess.run(command, cwd=BACKEND_DIR, check=False)  # noqa: S603
    return completed.returncode


def _load_files() -> dict[str, dict]:
    if not COVERAGE_JSON.exists():
        raise SystemExit(f"coverage report missing: {COVERAGE_JSON}")
    report = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    return {_normalise(path): data for path, data in report["files"].items()}


def _percent(summary: dict) -> float:
    statements = summary["num_statements"]
    if statements == 0:
        return 100.0
    return 100.0 * summary["covered_lines"] / statements


def main() -> int:
    pytest_code = _run_pytest()
    if pytest_code != 0:
        print(f"\nFAIL: rules pytest run exited {pytest_code}; coverage gate not evaluated")
        return pytest_code

    files = _load_files()
    failures: list[str] = []

    package_files = [data for path, data in files.items() if path.startswith(PACKAGE_PREFIX)]
    package_statements = sum(data["summary"]["num_statements"] for data in package_files)
    package_covered = sum(data["summary"]["covered_lines"] for data in package_files)
    package_percent = (
        100.0 * package_covered / package_statements if package_statements else 0.0
    )

    print("\nRules coverage gate")
    print(f"  app/rules package: {package_percent:.1f}% "
          f"(required >= {PACKAGE_MIN_PERCENT:.0f}%)")
    if package_percent < PACKAGE_MIN_PERCENT:
        failures.append(
            f"app/rules package coverage {package_percent:.1f}% < {PACKAGE_MIN_PERCENT:.0f}%"
        )

    for required in REQUIRED_100:
        data = files.get(required)
        if data is None:
            failures.append(f"{required}: not present in coverage report")
            print(f"  {required}: MISSING")
            continue
        percent = _percent(data["summary"])
        missing = data["summary"]["missing_lines"]
        detail = "" if not missing else f" — missing lines {missing}"
        print(f"  {required}: {percent:.1f}% (required 100%){detail}")
        if missing or percent < 100.0:
            failures.append(f"{required}: {percent:.1f}% < 100%{detail}")

    if failures:
        print("\nFAIL: rules coverage floors not met:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nPASS: rules coverage floors met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
