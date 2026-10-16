"""Retrieval (spec 5.2, decisions D3/D4/D5, CC-4).

Content lives in /ontology as JSON docs; `chunk_content` splits a doc into
deterministic `{slug}#{n}` chunks (1-based, in document order). Embeddings are
written ONLY through raw SQL with an explicit cast — `CAST(:emb AS vector)` on a
pgvector server, `CAST(:emb AS jsonb)` on the fallback — so one code path serves
both modes (D3). Mode is detected at runtime from `pg_extension` (D4). The JSONB
path searches by brute-force cosine in pure Python: the library is ~120 chunks and
this path exists only for servers without pgvector (D5, A32).

Search is language-filtered with a documented fallback to English: Sheng is
code-switched Kiswahili/English and has no content library of its own, so a Sheng
question is served from the English library rather than refused for lack of chunks.
"""

import json
import math
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.errors import ValidationError
from app.core.ids import uuid7
from sqlalchemy import Engine, create_engine, text

from ai_service.config import AISettings
from ai_service.providers.embeddings import EmbeddingProvider

PGVECTOR_MODE = "pgvector"
JSONB_MODE = "jsonb"
FALLBACK_LANGUAGE = "en"

_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")

DEFAULT_CHUNKS_TABLE = "ai.content_chunks"
DEFAULT_EMBEDDINGS_TABLE = "ai.chunk_embeddings"

_UPSERT_CHUNK_SQL = """
INSERT INTO {chunks_table}
    (id, chunk_id, slug, language, audience, title, text, sources, created_at)
VALUES
    (:id, :chunk_id, :slug, :language, :audience, :title, :text, CAST(:sources AS json), now())
ON CONFLICT (chunk_id) DO UPDATE SET
    slug = EXCLUDED.slug,
    language = EXCLUDED.language,
    audience = EXCLUDED.audience,
    title = EXCLUDED.title,
    text = EXCLUDED.text,
    sources = EXCLUDED.sources
RETURNING id
"""

_UPSERT_EMBEDDING_SQL = """
INSERT INTO {embeddings_table} (id, chunk_id, model, dim, embedding)
VALUES (:id, :chunk_id, :model, :dim, CAST(:emb AS {cast}))
ON CONFLICT (chunk_id, model) DO UPDATE SET
    dim = EXCLUDED.dim,
    embedding = EXCLUDED.embedding
"""

_SEARCH_SQL = """
SELECT
    c.chunk_id, c.slug, c.title, c.text, c.language, c.audience,
    1 - (e.embedding <=> CAST(:query AS vector)) AS score
FROM {embeddings_table} e
JOIN {chunks_table} c ON c.id = e.chunk_id
WHERE c.language = :language AND e.model = :model
ORDER BY e.embedding <=> CAST(:query AS vector)
LIMIT :top_k
"""

_LOAD_SQL = """
SELECT c.chunk_id, c.slug, c.title, c.text, c.language, c.audience, e.embedding
FROM {embeddings_table} e
JOIN {chunks_table} c ON c.id = e.chunk_id
WHERE c.language = :language AND e.model = :model
"""


@dataclass(frozen=True)
class Chunk:
    """One indexable unit of ontology content."""

    chunk_id: str
    slug: str
    language: str
    audience: str
    title: str
    text: str
    sources: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    slug: str
    title: str
    text: str
    language: str
    audience: str
    score: float


class EmbeddingStore(Protocol):
    """Storage for content chunks + their embeddings, in either server mode."""

    @property
    def mode(self) -> str: ...

    def upsert(self, chunk: Chunk, *, model: str, dim: int, embedding: Sequence[float]) -> None: ...

    def search(
        self, query: Sequence[float], *, language: str, model: str, top_k: int
    ) -> list[SearchHit]: ...

    def delete_all(self) -> int: ...


def _require_table(name: str) -> str:
    """Table names are code-level constants (tests may point a store at a scratch
    table); validate anyway so an f-string never builds SQL from arbitrary input."""
    if not _TABLE_RE.match(name):
        raise ValueError(f"invalid table name: {name!r}")
    return name


def _languages_to_try(language: str) -> list[str]:
    if language == FALLBACK_LANGUAGE:
        return [language]
    return [language, FALLBACK_LANGUAGE]


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in embedding) + "]"


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Pure-Python cosine similarity (D5: no numpy dependency)."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for left, right in zip(a, b, strict=True):
        dot += left * right
        norm_a += left * left
        norm_b += right * right
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class PgvectorStore:
    """Store for servers with the `vector` extension (D3/D4)."""

    def __init__(self, engine: Engine, *, chunks_table: str = DEFAULT_CHUNKS_TABLE,
                 embeddings_table: str = DEFAULT_EMBEDDINGS_TABLE) -> None:
        self._engine = engine
        self._chunks_table = _require_table(chunks_table)
        self._embeddings_table = _require_table(embeddings_table)

    @property
    def mode(self) -> str:
        return PGVECTOR_MODE

    def upsert(self, chunk: Chunk, *, model: str, dim: int, embedding: Sequence[float]) -> None:
        with self._engine.begin() as conn:
            chunk_pk: uuid.UUID = conn.execute(
                text(
                    _UPSERT_CHUNK_SQL.format(chunks_table=self._chunks_table)  # noqa: S608
                ),
                {
                    "id": uuid7(),
                    "chunk_id": chunk.chunk_id,
                    "slug": chunk.slug,
                    "language": chunk.language,
                    "audience": chunk.audience,
                    "title": chunk.title,
                    "text": chunk.text,
                    "sources": json.dumps(list(chunk.sources)),
                },
            ).scalar_one()
            conn.execute(
                text(
                    _UPSERT_EMBEDDING_SQL.format(  # noqa: S608
                        embeddings_table=self._embeddings_table, cast="vector"
                    )
                ),
                {
                    "id": uuid7(),
                    "chunk_id": chunk_pk,
                    "model": model,
                    "dim": dim,
                    "emb": _vector_literal(embedding),
                },
            )

    def search(
        self, query: Sequence[float], *, language: str, model: str, top_k: int
    ) -> list[SearchHit]:
        params = {
            "query": _vector_literal(query),
            "model": model,
            "top_k": top_k,
        }
        with self._engine.connect() as conn:
            for candidate in _languages_to_try(language):
                rows = conn.execute(
                    text(
                        _SEARCH_SQL.format(  # noqa: S608
                            chunks_table=self._chunks_table,
                            embeddings_table=self._embeddings_table,
                        )
                    ),
                    {**params, "language": candidate},
                ).mappings().all()
                if rows:
                    return [
                        SearchHit(
                            chunk_id=row["chunk_id"],
                            slug=row["slug"],
                            title=row["title"],
                            text=row["text"],
                            language=row["language"],
                            audience=row["audience"],
                            score=float(row["score"]),
                        )
                        for row in rows
                    ]
        return []

    def delete_all(self) -> int:
        with self._engine.begin() as conn:
            deleted = conn.execute(
                text(f"DELETE FROM {self._embeddings_table}")  # noqa: S608
            ).rowcount
            conn.execute(text(f"DELETE FROM {self._chunks_table}"))  # noqa: S608
        return int(deleted)


class JsonbStore:
    """Fallback store for servers without pgvector: `jsonb` column plus
    brute-force cosine in Python (D5). Table names are parameters so tests can
    exercise this path on a scratch table even where the real column is vector(768)."""

    def __init__(self, engine: Engine, *, chunks_table: str = DEFAULT_CHUNKS_TABLE,
                 embeddings_table: str = DEFAULT_EMBEDDINGS_TABLE) -> None:
        self._engine = engine
        self._chunks_table = _require_table(chunks_table)
        self._embeddings_table = _require_table(embeddings_table)

    @property
    def mode(self) -> str:
        return JSONB_MODE

    def upsert(self, chunk: Chunk, *, model: str, dim: int, embedding: Sequence[float]) -> None:
        with self._engine.begin() as conn:
            chunk_pk: uuid.UUID = conn.execute(
                text(
                    _UPSERT_CHUNK_SQL.format(chunks_table=self._chunks_table)  # noqa: S608
                ),
                {
                    "id": uuid7(),
                    "chunk_id": chunk.chunk_id,
                    "slug": chunk.slug,
                    "language": chunk.language,
                    "audience": chunk.audience,
                    "title": chunk.title,
                    "text": chunk.text,
                    "sources": json.dumps(list(chunk.sources)),
                },
            ).scalar_one()
            conn.execute(
                text(
                    _UPSERT_EMBEDDING_SQL.format(  # noqa: S608
                        embeddings_table=self._embeddings_table, cast="jsonb"
                    )
                ),
                {
                    "id": uuid7(),
                    "chunk_id": chunk_pk,
                    "model": model,
                    "dim": dim,
                    "emb": json.dumps(list(float(value) for value in embedding)),
                },
            )

    def search(
        self, query: Sequence[float], *, language: str, model: str, top_k: int
    ) -> list[SearchHit]:
        with self._engine.connect() as conn:
            for candidate in _languages_to_try(language):
                rows = conn.execute(
                    text(_LOAD_SQL.format(  # noqa: S608
                        chunks_table=self._chunks_table,
                        embeddings_table=self._embeddings_table,
                    )),
                    {"language": candidate, "model": model},
                ).mappings().all()
                if not rows:
                    continue
                hits: list[SearchHit] = []
                for row in rows:
                    stored = row["embedding"]
                    if isinstance(stored, str):
                        stored = json.loads(stored)
                    hits.append(
                        SearchHit(
                            chunk_id=row["chunk_id"],
                            slug=row["slug"],
                            title=row["title"],
                            text=row["text"],
                            language=row["language"],
                            audience=row["audience"],
                            score=_cosine(query, [float(value) for value in stored]),
                        )
                    )
                hits.sort(key=lambda hit: hit.score, reverse=True)
                return hits[:top_k]
        return []

    def delete_all(self) -> int:
        with self._engine.begin() as conn:
            deleted = conn.execute(
                text(f"DELETE FROM {self._embeddings_table}")  # noqa: S608
            ).rowcount
            conn.execute(text(f"DELETE FROM {self._chunks_table}"))  # noqa: S608
        return int(deleted)


def detect_vector_mode(engine: Engine) -> str:
    """Runtime mode detection (D4): the pgvector *extension* being installed is
    what makes `CAST(.. AS vector)` valid — not what the migration would have done."""
    with engine.connect() as conn:
        installed = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")
        ).scalar()
    return PGVECTOR_MODE if installed else JSONB_MODE


def build_store(settings: AISettings) -> EmbeddingStore:
    """Store for the configured database, in whatever mode that server supports."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    if detect_vector_mode(engine) == PGVECTOR_MODE:
        return PgvectorStore(engine)
    return JsonbStore(engine)


def load_content_docs(ontology_dir: Path, *, language: str | None = None) -> list[dict[str, Any]]:
    """Load content documents from /ontology/content (the single source of truth)."""
    content_dir = ontology_dir / "content"
    if not content_dir.is_dir():
        raise ValidationError(f"ontology content dir missing: {content_dir}")
    docs: list[dict[str, Any]] = []
    for path in sorted(content_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if language is not None and doc.get("language") != language:
            continue
        docs.append(doc)
    return docs


def chunk_content(doc: dict[str, Any], *, max_chunk_chars: int = 2400) -> list[Chunk]:
    """Split a content doc on blank lines. Chunk ids are `{slug}#{n}` (1-based) and
    stable across runs; an over-long paragraph is a content defect, not a silent
    truncation (the service refuses to index it)."""
    slug = str(doc["slug"])
    body = str(doc.get("body", ""))
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n")]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    chunks: list[Chunk] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        chunk_id = f"{slug}#{index}"
        if len(paragraph) > max_chunk_chars:
            raise ValidationError(
                f"content chunk too long: {chunk_id} is {len(paragraph)} chars "
                f"(limit {max_chunk_chars}); split it in the source file"
            )
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                slug=slug,
                language=str(doc["language"]),
                audience=str(doc.get("audience", "patient")),
                title=str(doc.get("title", slug)),
                text=paragraph,
                sources=tuple(doc.get("sources", [])),
            )
        )
    return chunks


def index_content(
    store: EmbeddingStore,
    embedder: EmbeddingProvider,
    ontology_dir: Path,
    model: str | None = None,
    dim: int | None = None,
    *,
    language: str | None = None,
    max_chunk_chars: int = 2400,
) -> int:
    """Chunk + embed + store the ontology library; returns the chunk count.

    Without a language filter the store is rebuilt from scratch (`delete_all`), so
    content removed from /ontology disappears from retrieval. A language-filtered
    run upserts only that language (chunk ids are unique, so it is idempotent)."""
    docs = load_content_docs(ontology_dir, language=language)
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_content(doc, max_chunk_chars=max_chunk_chars))
    if not chunks:
        return 0
    model = model or embedder.model
    dim = dim or embedder.dim
    vectors = embedder.embed([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValidationError("embedding provider returned the wrong number of vectors")
    if language is None:
        store.delete_all()
    for chunk, vector in zip(chunks, vectors, strict=True):
        store.upsert(chunk, model=model, dim=dim, embedding=vector)
    return len(chunks)


def chunk_ids(text_value: str) -> list[str]:
    """Chunk ids cited in `text_value`, in order of first appearance."""
    seen: list[str] = []
    for match in re.finditer(r"\b([a-z0-9][a-z0-9-]*#\d+)\b", text_value):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def hits_by_id(hits: Iterable[SearchHit]) -> dict[str, SearchHit]:
    return {hit.chunk_id: hit for hit in hits}
