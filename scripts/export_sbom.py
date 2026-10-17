#!/usr/bin/env python
"""Software bill of materials + pinned requirement locks (Phase 8, plan §5).

Exports every installed distribution of the project venv (backend/.venv) as a
CycloneDX-style JSON document at docs/sbom.json: ``bomFormat`` "CycloneDX",
``specVersion`` "1.4", and one ``library`` component per distribution with its
name, version, and license when the package metadata provides one.

No new dependencies: everything comes from ``importlib.metadata``. The output is
deterministic (components sorted by name, no timestamps) so the committed file
does not churn on every run.

With ``--locks`` the same command writes backend/requirements.lock,
ussd-whatsapp/requirements.lock, and ai_service/requirements.lock from
``pip freeze`` of the shared venv. The three project packages are editable
installs from this repo and are omitted (the header comment says so).

Usage:
    backend/.venv/Scripts/python.exe scripts/export_sbom.py
    backend/.venv/Scripts/python.exe scripts/export_sbom.py --locks
    backend/.venv/Scripts/python.exe scripts/export_sbom.py --check   # CI freshness
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SBOM = REPO_ROOT / "docs" / "sbom.json"
LOCK_PATHS = (
    REPO_ROOT / "backend" / "requirements.lock",
    REPO_ROOT / "ussd-whatsapp" / "requirements.lock",
    REPO_ROOT / "ai_service" / "requirements.lock",
)
LOCAL_PROJECTS = {"sisi-backend", "sisi-gateway", "sisi-ai"}
LOCK_HEADER = """\
# Shared backend venv freeze (backend/.venv) — Phase 8, plan section 5.
# The same environment serves backend, ussd-whatsapp, and ai_service, so this
# file is identical in all three service directories.
# The three project packages (sisi-backend, sisi-gateway, sisi-ai) are editable
# installs from this repo and are deliberately omitted; install them with:
#   pip install -e backend -e ussd-whatsapp -e ai_service
# CI installs from the pyproject constraints; this file records the verified venv.
"""


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license_name(dist: metadata.Distribution) -> str | None:
    """Best-effort license from package metadata (PEP 639 expression, License
    field, or an OSI classifier). Returns None when metadata has nothing usable."""
    try:
        metadata_fields = dist.metadata
    except Exception:  # noqa: BLE001 — broken metadata must not abort the export
        return None
    expression = (metadata_fields.get("License-Expression") or "").strip()
    if expression:
        return expression
    license_field = (metadata_fields.get("License") or "").strip()
    if license_field and license_field.upper() != "UNKNOWN":
        # Many packages put the full license text here; the first line is the
        # only part that reads as a name. Skip anything absurdly long.
        first_line = license_field.splitlines()[0].strip()
        if first_line and len(first_line) <= 100:
            return first_line
    for classifier in metadata_fields.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.rsplit("::", 1)[-1].strip()
    return None


def _components() -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dist in metadata.distributions():
        raw_name = dist.metadata.get("Name")
        version = dist.version
        if not raw_name or not version:
            continue
        key = _canonical(raw_name)
        if key in seen:
            continue
        seen.add(key)
        component: dict[str, Any] = {
            "type": "library",
            "name": raw_name,
            "version": version,
        }
        license_name = _license_name(dist)
        if license_name:
            component["licenses"] = [{"license": {"name": license_name}}]
        components.append(component)
    components.sort(key=lambda component: _canonical(component["name"]))
    return components


def build_sbom() -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "sisi-health",
                "version": "0.1.0",
            }
        },
        "components": _components(),
    }


def _frozen_requirements() -> list[str]:
    completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-m", "pip", "freeze"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    requirements: list[str] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-e "):
            continue
        name = re.split(r"==| @ ", stripped, maxsplit=1)[0]
        if _canonical(name) in LOCAL_PROJECTS:
            continue
        requirements.append(stripped)
    return requirements


def write_locks() -> None:
    body = "\n".join(_frozen_requirements()) + "\n"
    for path in LOCK_PATHS:
        path.write_text(LOCK_HEADER + body, encoding="utf-8")
        print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export CycloneDX SBOM and/or lock files")
    parser.add_argument("--output", type=Path, default=DEFAULT_SBOM)
    parser.add_argument("--locks", action="store_true", help="also write the three *.lock files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the committed SBOM differs from a fresh export",
    )
    args = parser.parse_args()

    sbom = build_sbom()
    rendered = json.dumps(sbom, indent=2, sort_keys=True) + "\n"
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"SBOM is stale: {args.output}; re-run scripts/export_sbom.py")
            return 1
        print(f"SBOM is current: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output} ({len(sbom['components'])} components)")

    if args.locks:
        write_locks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
