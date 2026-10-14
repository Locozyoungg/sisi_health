"""Export the OpenAPI spec to docs/openapi.yaml — frozen at the end of Phase 1;
later changes go through docs/contract-changes.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> int:
    spec = app.openapi()
    out = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
    try:
        import yaml as _yaml

        out.write_text(_yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except ImportError:
        import json

        out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"[openapi] wrote {out} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
