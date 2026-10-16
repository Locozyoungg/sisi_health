"""Export the AI service OpenAPI spec to docs/openapi-ai.yaml (spec 5.2, D7).

Mirrors backend/scripts/export_openapi.py: the spec is the frozen contract for the
internal `/v1/ai/*` surface, so a route or schema change shows up as a diff here.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AI_SERVICE_DIR = SCRIPT_DIR.parent
REPO_ROOT = AI_SERVICE_DIR.parent

if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from ai_service.main import create_app  # noqa: E402


def main() -> int:
    spec = create_app().openapi()
    out = REPO_ROOT / "docs" / "openapi-ai.yaml"
    try:
        import yaml as _yaml

        out.write_text(
            _yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    except ImportError:
        import json

        out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"[openapi-ai] wrote {out} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
