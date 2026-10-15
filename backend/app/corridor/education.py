"""Cervical screening education + HPV vaccination awareness content (spec 5.4.1).
Content lives in /ontology/content/*.json (CC-BY, single source of truth — same
pattern as rules) and ships clinically_unvalidated with the mandatory screening
disclaimer. No write endpoints: the content CMS arrives with the ops console."""

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.core.errors import PreconditionFailed

DISCLAIMER_SENTENCE = "A normal symptom check does not replace screening."


@lru_cache
def _content_files() -> tuple[dict[str, Any], ...]:
    content_dir = get_settings().ontology_dir / "content"
    if not content_dir.is_dir():
        return ()
    files: list[dict[str, Any]] = []
    for path in sorted(content_dir.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if not item.get("has_screening_disclaimer"):
            raise PreconditionFailed(f"content {path.name} missing the screening disclaimer flag")
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
