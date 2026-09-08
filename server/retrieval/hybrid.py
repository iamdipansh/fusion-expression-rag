"""Query expansion -> hybrid retrieval (dense + sparse, fused with RRF) -> rerank ->
sufficiency gate -> tiered answer synthesis. See "Answer tiering" and "Retrieval" in CLAUDE.md.

Generation split:
- query expansion + sufficiency check: small local model, no key required
- final answer synthesis: BYOK Claude (session-only key, see app/schemas.py)
- no key present: optional Gemini free-tier fallback, clearly labelled as reduced quality
"""

from typing import TYPE_CHECKING

from config import Sufficiency, settings
from generation.local_llm import classify_sufficiency, rewrite_query
from generation.synthesize import TIER_FOR_SUFFICIENCY, synthesize
from ingestion.chunk import Chunk
from retrieval.store import dense_search, lexical_search, sparse_search

# retrieval.embed and retrieval.rerank are imported lazily inside the hybrid-only functions
# below. Both reach torch, and lexical mode has to import this module on an install that doesn't
# contain it (see config.retrieval_mode).

if TYPE_CHECKING:
    from app.schemas import QueryResponse


def lexical_baseline_retrieve(
    question: str, limit: int = settings.retrieval_candidates
) -> list[Chunk]:
    """Milestone 3: the sparse-only baseline. No query expansion, no dense side, no rerank —
    just raw BM25-style FTS on the question as typed. Everything downstream (milestone 4's
    dense+RRF+rerank) gets measured as a delta against this number."""
    return lexical_search(question, limit)


def lexical_expanded_retrieve(
    question: str, limit: int = settings.retrieval_candidates
) -> list[Chunk]:
    """BM25 plus glossary-only expansion — the whole retrieval path of a model-free stack, since
    neither SQLite FTS5 nor `expand_query_without_model` loads a model. Measured against
    `lexical_baseline_retrieve` (no expansion) and the full hybrid stack, this is what says
    whether ~5.5GB of resident models is buying enough to be worth what it costs to host."""
    from generation.local_llm import expand_query_without_model

    return lexical_search(expand_query_without_model(question), limit)


def expand_query(question: str) -> str:
    """Rewrite user phrasing ("make it bounce") into Fusion manual vocabulary via the local
    no-API-key model (generation/local_llm.py). Milestone 4's eval numbers were measured with
    this as a passthrough — re-run the eval if tuning this meaningfully changes retrieval, per
    the "every retrieval experiment logged" convention in CLAUDE.md."""
    return rewrite_query(question)


def reciprocal_rank_fusion(
    dense_results: list[Chunk], sparse_results: list[Chunk], k: int = settings.rrf_k
) -> list[Chunk]:
    scores: dict[str, float] = {}
    chunks_by_id: dict[str, Chunk] = {}
    for results in (dense_results, sparse_results):
        for rank, chunk in enumerate(results, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk.chunk_id] = chunk
    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [chunks_by_id[cid] for cid in ranked_ids]


async def check_sufficiency(question: str, chunks: list[Chunk]) -> Sufficiency:
    """Lexical mode has no local model to ask, so the gate goes to Gemini there. Hybrid mode
    keeps the local Qwen classifier, which needs no key."""
    if settings.retrieval_mode == "lexical":
        from generation.synthesize import classify_sufficiency_remote

        return await classify_sufficiency_remote(question, chunks)
    return classify_sufficiency(question, chunks)


def retrieve_candidates(question: str, expanded: str | None = None) -> list[Chunk]:
    """Dense + sparse, fused with RRF — the bi-encoder/fusion stage's output, before reranking.
    CLAUDE.md's tuning heuristic is that this stage only has to land the right chunk somewhere
    in the top ~30; separating this from `retrieve()` lets recall@k here be measured on its own,
    independent of whether the reranker then puts it in the final top few."""
    from retrieval.embed import embed_query

    if expanded is None:
        expanded = expand_query(question)
    dense_vector, sparse_vector = embed_query(expanded)
    dense = dense_search(dense_vector, limit=settings.retrieval_candidates)
    sparse = sparse_search(sparse_vector, limit=settings.retrieval_candidates)
    return reciprocal_rank_fusion(dense, sparse)


def retrieve(question: str) -> list[Chunk]:
    """The serving path, dispatched on config.retrieval_mode — see that setting for the measured
    difference between the two (one question on the gold set, for ~5.5GB of resident models)."""
    if settings.retrieval_mode == "lexical":
        return lexical_expanded_retrieve(question, limit=settings.rerank_top_k)

    from retrieval.rerank import rerank

    expanded = expand_query(question)
    candidates = retrieve_candidates(question, expanded=expanded)
    return rerank(expanded, candidates, top_k=settings.rerank_top_k)


async def answer_query(question: str, anthropic_api_key: str | None) -> "QueryResponse":
    from app.schemas import Citation, QueryResponse

    chunks = retrieve(question)
    sufficiency = await check_sufficiency(question, chunks)
    tier = TIER_FOR_SUFFICIENCY[sufficiency]
    answer = await synthesize(question, chunks, tier, anthropic_api_key)
    # UNVERIFIED means nothing relevant was retrieved — citing the (irrelevant) top-k chunks
    # would misrepresent them as having grounded the answer, so it gets none.
    citations = (
        []
        if tier == "UNVERIFIED"
        else [
            Citation(
                breadcrumb=c.breadcrumb,
                page_start=c.page_start,
                page_end=c.page_end,
                content_type=c.content_type,
            )
            for c in chunks
        ]
    )
    return QueryResponse(tier=tier, sufficiency=sufficiency, answer=answer, citations=citations)
