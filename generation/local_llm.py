"""Query expansion + the sufficiency gate — the no-API-key-required half of the generation split
(see "Generation: bring your own key" in CLAUDE.md). Both are cheap, structured tasks a small
instruct model handles reliably; neither needs the quality (or memory) of the reranker's
cross-encoder, let alone a hosted LLM.
"""

import re

from config import Sufficiency, settings
from ingestion.chunk import Chunk

_tokenizer = None
_model = None  # lazy singleton — same rationale as retrieval/embed.py's model


def _select_device() -> str:
    """MPS is meaningfully faster on Apple Silicon; the deploy targets (Hugging Face Spaces /
    Oracle Cloud) are Linux with no MPS — detect rather than hardcode so this stays a free local
    speedup without breaking the hosted path (see retrieval/embed.py's identical note)."""
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def _get_model():  # type: ignore[no-untyped-def]
    global _tokenizer, _model
    if _model is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = _select_device()
        # fp16 CPU matmul isn't reliably accelerated (and errors on some torch/op combos) — only
        # use it on MPS, where it's a real win; CPU gets fp32 (still small at 0.5B params).
        dtype = torch.float16 if device == "mps" else torch.float32
        _tokenizer = AutoTokenizer.from_pretrained(settings.local_expansion_model)
        _model = AutoModelForCausalLM.from_pretrained(
            settings.local_expansion_model, dtype=dtype
        ).to(device)
        _model.eval()
    return _tokenizer, _model


def _generate(prompt: str, max_new_tokens: int) -> str:
    import torch

    tokenizer, model = _get_model()
    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_dict=True, return_tensors="pt"
    ).to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output[0][inputs["input_ids"].shape[1] :]
    return str(tokenizer.decode(generated, skip_special_tokens=True)).strip()


_REWRITE_PROMPT = """Rewrite the following user question using the exact terminology of \
DaVinci Resolve's Fusion manual: node names (Transform, Merge, Background, Custom Tool), \
parameter names, and expression-scripting terms (SimpleExpression, time, iif, GetValue). \
Output only the rewritten question on one line, nothing else.

Question: {question}
Rewritten:"""


def rewrite_query(question: str) -> str:
    """Best-effort query expansion — falls back to the original question on any failure, since
    this is an optimization the retrieval pipeline shouldn't hard-depend on."""
    try:
        rewritten = _generate(_REWRITE_PROMPT.format(question=question), max_new_tokens=64)
        rewritten = rewritten.splitlines()[0].strip() if rewritten else ""
        return rewritten if rewritten else question
    except Exception:
        return question


_SUFFICIENCY_PROMPT = """A user asked a question about DaVinci Resolve's Fusion page. Below are \
manual excerpts retrieved for it. Classify how well they answer the question:
- sufficient: the excerpts directly answer the question
- partial: the excerpts give relevant primitives or context but not a direct answer
- insufficient: the excerpts are not relevant to the question

Question: {question}

Excerpts:
{excerpts}

Answer with exactly one word: sufficient, partial, or insufficient."""

_SUFFICIENCY_LABELS: tuple[Sufficiency, ...] = ("sufficient", "partial", "insufficient")


def classify_sufficiency(question: str, chunks: list[Chunk]) -> Sufficiency:
    """Fails closed to "insufficient" on any error or unparseable output — matching CLAUDE.md's
    "an answer that admits it's unverified beats a confident wrong one"."""
    if not chunks:
        return "insufficient"
    try:
        excerpts = "\n\n".join(f"[{c.breadcrumb}] {c.text[:300]}" for c in chunks[:5])
        prompt = _SUFFICIENCY_PROMPT.format(question=question, excerpts=excerpts)
        raw = _generate(prompt, max_new_tokens=8).lower()
        for label in _SUFFICIENCY_LABELS:
            if re.search(rf"\b{label}\b", raw):
                return label
        return "insufficient"
    except Exception:
        return "insufficient"
