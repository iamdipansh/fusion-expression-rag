"""bge-m3, local. Emits dense + sparse lexical weights in one pass — the sparse side is what
carries exact-token Fusion syntax (Transform1.Center, nTime, Fusion.GetPrevKeyFrame) that a
pure dense embedder would blur. See "Why free is not a compromise" in CLAUDE.md.
"""

from pydantic import BaseModel

from config import settings
from ingestion.chunk import Chunk

_model = None  # lazy singleton — loading bge-m3 takes real time, do it once per process


def _select_device() -> str:
    """MPS is ~2x faster than CPU for this model on Apple Silicon, but the deploy targets
    (Hugging Face Spaces / Oracle Cloud) are Linux with no MPS — detect rather than hardcode so
    this stays a free local speedup without breaking the hosted path."""
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def _get_model():  # type: ignore[no-untyped-def]
    global _model
    if _model is None:
        from FlagEmbedding import BGEM3FlagModel

        _model = BGEM3FlagModel(settings.embedding_model, use_fp16=True, devices=_select_device())
    return _model


class SparseVector(BaseModel):
    # bge-m3's lexical_weights come back as {token_id_str: weight} — keep that shape rather
    # than converting to parallel index/value lists, since sparse_search does dict lookups.
    weights: dict[str, float]


class EmbeddedChunk(BaseModel):
    chunk: Chunk
    dense: list[float]
    sparse: SparseVector


def embed_chunks(chunks: list[Chunk], batch_size: int = 16) -> list[EmbeddedChunk]:
    model = _get_model()
    texts = [c.text for c in chunks]
    output = model.encode(
        texts,
        batch_size=batch_size,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    dense_vecs = output["dense_vecs"]
    sparse_weights = output["lexical_weights"]
    return [
        EmbeddedChunk(
            chunk=chunk,
            dense=dense_vecs[i].tolist(),
            sparse=SparseVector(weights=dict(sparse_weights[i])),
        )
        for i, chunk in enumerate(chunks)
    ]


def embed_query(query: str) -> tuple[list[float], SparseVector]:
    """Returns (dense, sparse) for a single query string."""
    model = _get_model()
    output = model.encode(
        [query], return_dense=True, return_sparse=True, return_colbert_vecs=False
    )
    dense = output["dense_vecs"][0].tolist()
    sparse = SparseVector(weights=dict(output["lexical_weights"][0]))
    return dense, sparse
