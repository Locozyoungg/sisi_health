"""RAG (D3/D4/D5, CC-4): chunking stability, both storage modes, language-filtered
search with the documented English fallback for Sheng, and the indexer.

The JSONB store is exercised against an in-test scratch table with a jsonb column,
so the fallback path is covered even on a pgvector server where the real column is
vector(768). PgvectorStore tests skip when the extension is not installed.
"""

import pytest
from app.core.errors import ValidationError
from sqlalchemy import Engine, text

from ai_service.config import AISettings
from ai_service.providers.embeddings import StubEmbeddingProvider
from ai_service.rag import (
    JSONB_MODE,
    PGVECTOR_MODE,
    Chunk,
    JsonbStore,
    PgvectorStore,
    SearchHit,
    build_store,
    chunk_content,
    chunk_ids,
    detect_vector_mode,
    hits_by_id,
    index_content,
    load_content_docs,
)

SCRATCH_CHUNKS = "ai.ai_jsonb_test_chunks"
SCRATCH_EMBEDDINGS = "ai.ai_jsonb_test_embeddings"
# table names are constants, never caller input (the real store validates them too)
N_CHUNKS = f"SELECT count(*) FROM {SCRATCH_CHUNKS}"  # noqa: S608
N_EMBEDDINGS = f"SELECT count(*) FROM {SCRATCH_EMBEDDINGS}"  # noqa: S608

SCRATCH_DDL = (
    f"CREATE TABLE {SCRATCH_CHUNKS} (LIKE ai.content_chunks INCLUDING ALL)",
    f"""CREATE TABLE {SCRATCH_EMBEDDINGS} (
        id uuid PRIMARY KEY,
        chunk_id uuid NOT NULL,
        model varchar(64) NOT NULL,
        dim integer NOT NULL,
        embedding jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_ai_jsonb_test_chunk_model UNIQUE (chunk_id, model)
    )""",
)

DOC = {
    "slug": "test-content-en",
    "language": "en",
    "audience": "patient",
    "title": "Test content",
    "body": "First paragraph about period pain.\n\nSecond paragraph about discharge.",
    "sources": [{"title": "WHO", "organization": "WHO"}],
}


@pytest.fixture()
def scratch_jsonb_store(test_engine: Engine) -> JsonbStore:
    with test_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {SCRATCH_EMBEDDINGS}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {SCRATCH_CHUNKS}"))
        for ddl in SCRATCH_DDL:
            conn.execute(text(ddl))
    store = JsonbStore(
        test_engine, chunks_table=SCRATCH_CHUNKS, embeddings_table=SCRATCH_EMBEDDINGS
    )
    yield store
    with test_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {SCRATCH_EMBEDDINGS}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {SCRATCH_CHUNKS}"))


# --- chunking ----------------------------------------------------------------------


def test_chunk_content_is_deterministic_and_1_based() -> None:
    chunks = chunk_content(DOC, max_chunk_chars=2400)
    assert [chunk.chunk_id for chunk in chunks] == ["test-content-en#1", "test-content-en#2"]
    assert chunks[0].text == "First paragraph about period pain."
    assert chunks[1].text == "Second paragraph about discharge."
    assert all(chunk.slug == "test-content-en" for chunk in chunks)
    assert all(chunk.language == "en" for chunk in chunks)
    assert chunks[0].sources == ({"title": "WHO", "organization": "WHO"},)
    assert chunk_content(DOC, max_chunk_chars=2400) == chunks  # stable across runs


def test_chunk_content_ignores_blank_paragraphs() -> None:
    doc = dict(DOC, body="One.\n\n\n\nTwo.\n\n   \n\nThree.")
    assert [chunk.text for chunk in chunk_content(doc)] == ["One.", "Two.", "Three."]


def test_chunk_content_rejects_an_oversized_paragraph() -> None:
    doc = dict(DOC, body="short\n\n" + "x" * 50)
    with pytest.raises(ValidationError, match="content chunk too long: test-content-en#2"):
        chunk_content(doc, max_chunk_chars=40)


def test_every_ontology_content_file_chunks_within_the_limit(settings: AISettings) -> None:
    docs = load_content_docs(settings.ontology_dir)
    # six topics — cervical screening, HPV vaccination, endometriosis, PCOS, fibroids
    # and period health — each in en and sw
    assert len(docs) == 12
    for doc in docs:
        chunks = chunk_content(doc, max_chunk_chars=settings.ai_rag_max_chunk_chars)
        assert chunks, f"{doc['slug']} produced no chunks"
        for chunk in chunks:
            assert len(chunk.text) <= settings.ai_rag_max_chunk_chars
            assert chunk.chunk_id.startswith(f"{doc['slug']}#")


def test_load_content_docs_filters_by_language(settings: AISettings) -> None:
    sw_docs = load_content_docs(settings.ontology_dir, language="sw")
    assert sw_docs
    assert all(doc["language"] == "sw" for doc in sw_docs)
    assert load_content_docs(settings.ontology_dir, language="sheng") == []


def _hit(chunk_id: str) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        slug=chunk_id.split("#")[0],
        title="t",
        text="x",
        language="en",
        audience="patient",
        score=1.0,
    )


def test_chunk_ids_and_hits_by_id_helpers() -> None:
    assert chunk_ids("see [a#1] and [b-2#10], again [a#1]") == ["a#1", "b-2#10"]
    hits = [_hit("a#1"), _hit("b#2")]
    assert set(hits_by_id(hits)) == {"a#1", "b#2"}


# --- mode detection + factory ------------------------------------------------------


def test_detect_vector_mode_matches_the_installed_extension(test_engine: Engine) -> None:
    installed = bool(
        test_engine.connect()
        .execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
        .scalar()
    )
    assert detect_vector_mode(test_engine) == (PGVECTOR_MODE if installed else JSONB_MODE)


def test_build_store_returns_the_class_for_the_server_mode(
    settings: AISettings, test_engine: Engine
) -> None:
    store = build_store(settings)
    expected = PgvectorStore if detect_vector_mode(test_engine) == PGVECTOR_MODE else JsonbStore
    assert isinstance(store, expected)
    assert store.mode == detect_vector_mode(test_engine)


# --- real store round trip ---------------------------------------------------------


def test_real_store_round_trip_finds_the_identical_chunk(
    seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    docs = load_content_docs(settings.ontology_dir, language="en")
    target = chunk_content(docs[0], max_chunk_chars=settings.ai_rag_max_chunk_chars)[1]
    hits = seeded_store.search(
        embedder.embed([target.text])[0], language="en", model=embedder.model, top_k=4
    )
    assert hits, "the seeded store must return hits"
    assert hits[0].chunk_id == target.chunk_id
    assert hits[0].score > 0.99  # the stub embedding of identical text is a perfect match
    assert all(hit.language == "en" for hit in hits)


def test_real_store_search_is_language_filtered_and_falls_back_to_english(
    seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    sw_doc = load_content_docs(settings.ontology_dir, language="sw")[0]
    sw_chunk = chunk_content(sw_doc, max_chunk_chars=settings.ai_rag_max_chunk_chars)[0]
    query = embedder.embed([sw_chunk.text])[0]

    english = seeded_store.search(query, language="en", model=embedder.model, top_k=4)
    assert english and all(hit.language == "en" for hit in english)
    assert sw_chunk.chunk_id not in {hit.chunk_id for hit in english}

    # Sheng has no content library of its own: the documented fallback serves English
    sheng = seeded_store.search(query, language="sheng", model=embedder.model, top_k=3)
    assert sheng and all(hit.language == "en" for hit in sheng)

    swahili = seeded_store.search(query, language="sw", model=embedder.model, top_k=4)
    assert swahili[0].chunk_id == sw_chunk.chunk_id


def test_index_content_counts_chunks_and_is_idempotent(
    test_engine: Engine, seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    expected = sum(
        len(chunk_content(doc, max_chunk_chars=settings.ai_rag_max_chunk_chars))
        for doc in load_content_docs(settings.ontology_dir)
    )
    count = index_content(
        seeded_store, embedder, settings.ontology_dir, embedder.model, embedder.dim
    )
    assert count == expected
    again = index_content(
        seeded_store, embedder, settings.ontology_dir, embedder.model, embedder.dim
    )
    assert again == expected
    with test_engine.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM ai.content_chunks")).scalar()
        embeddings = conn.execute(text("SELECT count(*) FROM ai.chunk_embeddings")).scalar()
    assert rows == expected
    assert embeddings == expected  # re-indexing upserts, never duplicates


def test_index_content_language_filter_keeps_the_other_language(
    test_engine: Engine, seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    full = index_content(
        seeded_store, embedder, settings.ontology_dir, embedder.model, embedder.dim
    )
    sw_count = index_content(
        seeded_store,
        embedder,
        settings.ontology_dir,
        embedder.model,
        embedder.dim,
        language="sw",
    )
    assert 0 < sw_count < full
    with test_engine.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM ai.content_chunks")).scalar()
    assert rows == full  # an en-only rebuild was not triggered


def test_delete_all_clears_chunks_and_embeddings(
    test_engine: Engine, seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    count = index_content(
        seeded_store, embedder, settings.ontology_dir, embedder.model, embedder.dim
    )
    assert seeded_store.delete_all() == count
    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ai.content_chunks")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM ai.chunk_embeddings")).scalar() == 0


def test_index_content_reports_no_content_for_an_unknown_language(
    seeded_store, embedder: StubEmbeddingProvider, settings: AISettings
) -> None:
    assert (
        index_content(
            seeded_store,
            embedder,
            settings.ontology_dir,
            embedder.model,
            embedder.dim,
            language="sheng",
        )
        == 0
    )


# --- JSONB fallback store on a scratch table ---------------------------------------


def test_jsonb_store_upsert_search_and_delete(
    scratch_jsonb_store: JsonbStore, embedder: StubEmbeddingProvider, test_engine: Engine
) -> None:
    store = scratch_jsonb_store
    assert store.mode == JSONB_MODE
    en_chunk = Chunk(
        chunk_id="scratch-en#1",
        slug="scratch-en",
        language="en",
        audience="patient",
        title="Scratch EN",
        text="Period pain is common in the first days.",
        sources=({"title": "WHO"},),
    )
    sw_chunk = Chunk(
        chunk_id="scratch-sw#1",
        slug="scratch-sw",
        language="sw",
        audience="patient",
        title="Scratch SW",
        text="Maumivu ya hedhi ni ya kawaida siku za kwanza.",
    )
    for chunk in (en_chunk, sw_chunk):
        store.upsert(
            chunk,
            model=embedder.model,
            dim=embedder.dim,
            embedding=embedder.embed([chunk.text])[0],
        )
    # upsert is keyed by chunk_id+model: a re-upsert must not duplicate
    store.upsert(
        en_chunk,
        model=embedder.model,
        dim=embedder.dim,
        embedding=embedder.embed([en_chunk.text])[0],
    )
    with test_engine.connect() as conn:
        assert conn.execute(text(N_CHUNKS)).scalar() == 2  # noqa: S608
        assert conn.execute(text(N_EMBEDDINGS)).scalar() == 2  # noqa: S608

    hits = store.search(
        embedder.embed([en_chunk.text])[0], language="en", model=embedder.model, top_k=4
    )
    assert [hit.chunk_id for hit in hits] == ["scratch-en#1"]
    assert hits[0].score > 0.99
    assert hits[0].title == "Scratch EN"
    assert hits[0].audience == "patient"

    # no sheng rows and no english rows left for that language -> english fallback
    sheng = store.search(
        embedder.embed(["periods"]), language="sheng", model=embedder.model, top_k=4
    )
    assert [hit.chunk_id for hit in sheng] == ["scratch-en#1"]

    assert store.delete_all() == 2
    with test_engine.connect() as conn:
        assert conn.execute(text(N_EMBEDDINGS)).scalar() == 0  # noqa: S608
        assert conn.execute(text(N_CHUNKS)).scalar() == 0  # noqa: S608


def test_jsonb_store_search_is_empty_when_nothing_is_indexed(
    scratch_jsonb_store: JsonbStore, embedder: StubEmbeddingProvider
) -> None:
    assert (
        scratch_jsonb_store.search(
            embedder.embed(["damu"])[0], language="en", model=embedder.model, top_k=4
        )
        == []
    )
    assert scratch_jsonb_store.delete_all() == 0


def test_jsonb_store_skips_rows_from_another_embedding_model(
    scratch_jsonb_store: JsonbStore, embedder: StubEmbeddingProvider
) -> None:
    chunk = Chunk(
        chunk_id="scratch-model#1",
        slug="scratch-model",
        language="en",
        audience="patient",
        title="Other model",
        text="Text indexed by a different embedding model.",
    )
    scratch_jsonb_store.upsert(
        chunk, model="other-model", dim=embedder.dim, embedding=embedder.embed([chunk.text])[0]
    )
    assert (
        scratch_jsonb_store.search(
            embedder.embed([chunk.text])[0], language="en", model=embedder.model, top_k=4
        )
        == []
    )


def test_jsonb_store_rejects_invalid_table_names(test_engine: Engine) -> None:
    with pytest.raises(ValueError, match="invalid table name"):
        JsonbStore(test_engine, chunks_table="ai.content_chunks; DROP TABLE ai.content_chunks")


def test_jsonb_cosine_of_a_zero_vector_is_zero() -> None:
    from ai_service.rag import _cosine

    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0], [1.0, 1.0]) == 0.0  # dimension mismatch is not a crash


# --- pgvector store (skipped where the extension is absent) ------------------------


def test_pgvector_store_round_trip(store, embedder: StubEmbeddingProvider) -> None:
    if store.mode != PGVECTOR_MODE:
        pytest.skip("pgvector extension is not installed on this server (JSONB branch)")
    assert isinstance(store, PgvectorStore)
    chunk = Chunk(
        chunk_id="pgv#1",
        slug="pgv",
        language="en",
        audience="patient",
        title="pgvector round trip",
        text="Cervical screening is a short test done at a health facility.",
    )
    store.upsert(
        chunk, model=embedder.model, dim=embedder.dim, embedding=embedder.embed([chunk.text])[0]
    )
    hits = store.search(
        embedder.embed([chunk.text])[0], language="en", model=embedder.model, top_k=1
    )
    assert hits and hits[0].chunk_id == "pgv#1"
    assert hits[0].score > 0.99
    assert store.delete_all() >= 1


def test_embedding_dim_matches_the_column(settings: AISettings) -> None:
    # migration 0007 creates vector(768); a different configured dim must be a
    # deliberate change, not a silent mismatch
    assert settings.ai_embedding_dim == 768
