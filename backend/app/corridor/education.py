"""Education content serving (spec 5.4.1 + 5.2). Content lives in
/ontology/content/*.json (CC-BY, single source of truth — same pattern as
rules) and ships clinically_unvalidated. SCREENING content must carry the
mandatory screening disclaimer ("A normal symptom check does not replace
screening."); non-screening topics (Phase 6: endo/PCOS/fibroids/period health)
carry the flag set to false. No write endpoints: the content CMS arrives with
the ops console."""

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.core.errors import PreconditionFailed

DISCLAIMER_SENTENCE = "A normal symptom check does not replace screening."
SCREENING_SLUG_PREFIXES = ("cervical-screening", "hpv-vaccination")


@lru_cache
def _content_files() -> tuple[dict[str, Any], ...]:
    content_dir = get_settings().ontology_dir / "content"
    if not content_dir.is_dir():
        return ()
    files: list[dict[str, Any]] = []
    for path in sorted(content_dir.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("has_screening_disclaimer") is None:
            raise PreconditionFailed(f"content {path.name} missing the screening disclaimer flag")
        slug = str(item.get("slug", ""))
        if slug.startswith(SCREENING_SLUG_PREFIXES) and not item["has_screening_disclaimer"]:
            raise PreconditionFailed(
                f"screening content {path.name} must set has_screening_disclaimer true"
            )
        files.append(item)
    return tuple(files)


def list_content(language: str | None = None, audience: str | None = None) -> list[dict[str, Any]]:
    out = []
    for item in _content_files():
        if language and item.get("language") != language:
            continue
        if audience and item.get("audience") != audience:
            continue
        out.append(
            {
                "slug": item["slug"],
                "language": item["language"],
                "audience": item["audience"],
                "title": item["title"],
                "body": item["body"],
                "sources": item.get("sources", []),
                "clinically_validated": item.get("clinically_validated", False),
            }
        )
    return out
