"""bge-reranker-v2-m3, local. Carries more of the pipeline's quality than the embedder — if RAM
gets tight, shrink the embedder, never this.

Uses FlagEmbedding's FlagReranker directly rather than an ONNX-quantized export. CLAUDE.md's
stack table calls for ONNX-quantization (~4x smaller) specifically to mitigate cold starts on a
sleep-after-idle free tier (Hugging Face Spaces). Milestone 7 deployed to Oracle Cloud's Always
Free ARM VM instead, which never sleeps — see config.py's reranker_onnx_quantized note. Revisit
if a sleep-tier host is ever added alongside it.
"""

from FlagEmbedding import FlagReranker

from config import settings
from ingestion.chunk import Chunk

_reranker: FlagReranker | None = None


def _select_device() -> str:
    """MPS is ~1.8x faster than CPU for this model on Apple Silicon, but the deploy targets
    (Hugging Face Spaces / Oracle Cloud) are Linux with no MPS — detect rather than hardcode so
    this stays a free local speedup without breaking the hosted path."""
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def _get_reranker() -> FlagReranker:
    global _reranker
    if _reranker is None:
        _reranker = FlagReranker(settings.reranker_model, use_fp16=True, devices=_select_device())
    return _reranker


def rerank(query: str, candidates: list[Chunk], top_k: int) -> list[Chunk]:
    if not candidates:
        return []
    reranker = _get_reranker()
    pairs = [[query, c.text] for c in candidates]
    scores = reranker.compute_score(pairs, normalize=False)
    if isinstance(scores, float):
        scores = [scores]
    ranked = sorted(zip(scores, candidates, strict=True), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]
