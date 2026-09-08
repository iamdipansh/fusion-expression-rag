"""LanceDB: vectors + metadata + full-text index in one file. Shipped as a static prebuilt
artifact — the manual never changes, so ingestion/embedding is a one-time local job and the
server only embeds a query and reranks at request time.

Milestone 3 (sparse-only baseline) uses `lexical_search`: classic BM25-style full-text search
via LanceDB's built-in FTS index — no embedding model needed. This is deliberately a different
mechanism from milestone 4's `sparse_search`, which will use bge-m3's *learned* sparse vectors
(see "bge-m3 supplies both dense and sparse" in CLAUDE.md) — conflating the two under one name
would make the eventual hybrid RRF fusion (dense + bge-m3-sparse) hard to reason about, and
lexical_search stays useful afterward too as the "cheap cross-check" CLAUDE.md calls for.
"""

import json

import lancedb
from lancedb.index import FTS

from config import settings
from ingestion.chunk import Chunk
from retrieval.embed import EmbeddedChunk, SparseVector

SPARSE_WEIGHTS_PATH = settings.lancedb_uri.parent / "sparse_weights.json"

_sparse_weights_cache: dict[str, dict[str, float]] | None = None
_chunk_by_id_cache: dict[str, Chunk] | None = None


def _connect() -> lancedb.DBConnection:
    settings.lancedb_uri.parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(settings.lancedb_uri))


def _row_to_chunk(r: dict) -> Chunk:
    return Chunk(
        chunk_id=r["chunk_id"],
        breadcrumb=r["breadcrumb"],
        page_start=r["page_start"],
        page_end=r["page_end"],
        content_type=r["content_type"],
        has_expression_syntax=r["has_expression_syntax"],
        text=r["text"],
    )


def write_chunks_lexical_only(chunks: list[Chunk]) -> None:
    db = _connect()
    data = [
        {
            "chunk_id": c.chunk_id,
            "breadcrumb": c.breadcrumb,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "content_type": c.content_type,
            "has_expression_syntax": c.has_expression_syntax,
            "text": c.text,
        }
        for c in chunks
    ]
    tbl = db.create_table(settings.lancedb_table, data=data, mode="overwrite")
    tbl.create_index("text", config=FTS())


def lexical_search(query: str, limit: int) -> list[Chunk]:
    db = _connect()
    tbl = db.open_table(settings.lancedb_table)
    rows = tbl.search(query, query_type="fts").limit(limit).to_list()
    return [_row_to_chunk(r) for r in rows]


def write_chunks(chunks: list[EmbeddedChunk]) -> None:
    """Writes dense vectors + metadata + text into LanceDB (with an FTS index, so this table
    also serves lexical_search), and bge-m3's sparse lexical weights into a side JSON file —
    LanceDB doesn't have a native sparse-vector column type suited to bge-m3's per-token weight
    dicts, and a flat in-memory dot-product scan is the right amount of engineering for a
    ~6,000-chunk corpus (an inverted index would be the kind of thing CLAUDE.md's intro warns
    costs more than it gives at this scale)."""
    db = _connect()
    data = [
        {
            "chunk_id": ec.chunk.chunk_id,
            "breadcrumb": ec.chunk.breadcrumb,
            "page_start": ec.chunk.page_start,
            "page_end": ec.chunk.page_end,
            "content_type": ec.chunk.content_type,
            "has_expression_syntax": ec.chunk.has_expression_syntax,
            "text": ec.chunk.text,
            "vector": ec.dense,
        }
        for ec in chunks
    ]
    tbl = db.create_table(settings.lancedb_table, data=data, mode="overwrite")
    tbl.create_index("text", config=FTS())

    sparse_weights = {ec.chunk.chunk_id: ec.sparse.weights for ec in chunks}
    SPARSE_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPARSE_WEIGHTS_PATH.write_text(json.dumps(sparse_weights))

    global _sparse_weights_cache, _chunk_by_id_cache
    _sparse_weights_cache = sparse_weights
    _chunk_by_id_cache = {ec.chunk.chunk_id: ec.chunk for ec in chunks}


def dense_search(query_vector: list[float], limit: int) -> list[Chunk]:
    db = _connect()
    tbl = db.open_table(settings.lancedb_table)
    rows = tbl.search(query_vector).limit(limit).to_list()
    return [_row_to_chunk(r) for r in rows]


def _load_sparse_index() -> tuple[dict[str, dict[str, float]], dict[str, Chunk]]:
    global _sparse_weights_cache, _chunk_by_id_cache
    if _sparse_weights_cache is None:
        _sparse_weights_cache = json.loads(SPARSE_WEIGHTS_PATH.read_text())
    if _chunk_by_id_cache is None:
        db = _connect()
        tbl = db.open_table(settings.lancedb_table)
        rows = tbl.to_pandas().to_dict("records")
        _chunk_by_id_cache = {r["chunk_id"]: _row_to_chunk(r) for r in rows}
    return _sparse_weights_cache, _chunk_by_id_cache


def sparse_search(query_sparse: SparseVector, limit: int) -> list[Chunk]:
    """bge-m3 learned sparse vector search: dot product between the query's sparse weights and
    each chunk's, iterating over the (short) query weight dict against each chunk's dict rather
    than the reverse — cheap at this corpus size, no ANN structure needed."""
    weights_by_chunk, chunks_by_id = _load_sparse_index()
    query_weights = query_sparse.weights

    scores: list[tuple[float, str]] = []
    for chunk_id, chunk_weights in weights_by_chunk.items():
        score = sum(qw * chunk_weights.get(tok, 0.0) for tok, qw in query_weights.items())
        if score > 0:
            scores.append((score, chunk_id))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [chunks_by_id[chunk_id] for _, chunk_id in scores[:limit]]


def index_diagnostics() -> dict[str, object]:
    """What `/health` reports about the index beyond "the directory exists".

    Added after a deploy where `index_loaded: true` was true and retrieval still returned zero
    chunks for every query — the path existed, but the FTS index wasn't usable in that
    environment. Path existence is not a useful health signal on its own; whether a search
    actually returns rows is. Returns only counts and versions, never chunk text.
    """
    info: dict[str, object] = {"lancedb_version": getattr(lancedb, "__version__", "unknown")}
    try:
        db = _connect()
        info["tables"] = db.table_names()
        tbl = db.open_table(settings.lancedb_table)
        info["rows"] = tbl.count_rows()
        try:
            info["indices"] = [str(i) for i in tbl.list_indices()]
        except Exception as e:
            info["indices"] = f"list_indices failed: {type(e).__name__}: {e}"
        try:
            hits = tbl.search("transform", query_type="fts").limit(3).to_list()
            info["fts_probe_hits"] = len(hits)
        except Exception as e:
            info["fts_probe_hits"] = f"{type(e).__name__}: {e}"
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return info
