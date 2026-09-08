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


# Zero-shot instructions don't get vocabulary translation out of a 0.5B model — it paraphrases
# instead ("how do I make a layer bounce like a rubber ball" -> "How can I create a layer that
# bounces like a rubber ball in DaVinci Resolve?", which retrieves nothing useful). The examples
# below carry the target vocabulary themselves, which is what a model this size can actually copy.
_REWRITE_PROMPT = """You translate a user's question into the vocabulary of DaVinci Resolve's \
Fusion manual so it can be matched against the manual's text. The manual documents primitives — \
the `time` variable, sin/cos/iif functions, SimpleExpressions, modifiers, and per-node parameter \
tables. It never uses casual wording like "bounce" or "wiggle". Replace casual wording with the \
manual's terms. Output only the rewritten query, on one line.

Question: how do I make something bounce
Rewritten: SimpleExpression driving a parameter from the time variable using sin and cos for \
decaying oscillation

Question: add a wiggle to my text
Rewritten: Perturb modifier applied to a Text+ node's Center parameter for random noise animation

Question: {question}
Rewritten:"""

# Deterministic vocabulary for the handful of concepts this tool exists to serve (CLAUDE.md names
# spring, bounce, squash-and-stretch by name). The manual never uses these words, so a query
# containing them has near-zero lexical overlap with the corpus — measured: the correct chunk for
# a bounce question scored -6.81 on the raw phrasing versus +0.85 once the query carried this
# vocabulary instead. Terms are drawn only from what's verified in the fusion-expressions skill's
# references/node-inputs.md and math-patterns.md — never invent an input name here.
_CONCEPT_VOCABULARY: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("bounce", "bouncing", "rubber ball", "dropped"),
        "SimpleExpression time variable sin cos abs decaying oscillation Transform Center",
    ),
    (
        ("spring", "springy", "overshoot", "settle", "follow-through"),
        "SimpleExpression time variable damped oscillator exp cos decay Transform Center",
    ),
    (
        ("wiggle", "jitter", "shake", "handheld", "random"),
        "Perturb modifier Modify With noise SimpleExpression time Center",
    ),
    (
        ("ease", "easing", "smooth", "interpolation"),
        "SimpleExpression iif normalized time Spline Editor interpolation Smooth keyframe",
    ),
    (
        ("squash", "stretch"),
        "Transform node Size Aspect Use Size and Aspect XScale YScale SimpleExpression sqrt",
    ),
    (
        ("rotate", "rotating", "spin", "spinning"),
        "Transform node Angle SimpleExpression time degrees",
    ),
)


# Expansion helps procedural requests ("how do I make it bounce") and hurts factual lookups
# ("what are the three options on the Background node's Repeat menu"), which the manual answers
# verbatim and where an exact query is already optimal. That split is what the v3 eval measured:
# composed_animation — almost entirely procedural — rose 0.615 -> 0.923, while node_lookup and
# parameter_lookup collapsed to ~0.35. A glossary hit alone doesn't separate them, since lookup
# questions legitimately contain words like "shake" and "noise"; the question's grammatical form
# does.
_PROCEDURAL_OPENERS: tuple[str, ...] = (
    "how do i",
    "how do you",
    "how can i",
    "how would i",
    "how to",
    "write a",
    "write an",
    "make ",
    "add ",
    "create ",
    "animate ",
    "drive ",
)


def _is_procedural(question: str) -> bool:
    lowered = question.strip().lower()
    return lowered.startswith(_PROCEDURAL_OPENERS)


def _glossary_terms(question: str) -> str:
    """Manual vocabulary for every concept the question mentions, deduplicated in order."""
    lowered = question.lower()
    seen: dict[str, None] = {}
    for triggers, vocabulary in _CONCEPT_VOCABULARY:
        if any(trigger in lowered for trigger in triggers):
            for term in vocabulary.split():
                seen.setdefault(term, None)
    return " ".join(seen)


def rewrite_query(question: str) -> str:
    """Expand only the questions that need it — a glossary match is the signal that the question
    is phrased in casual physical metaphor ("make it bounce") rather than the manual's own
    vocabulary, and so has little lexical overlap with the corpus.

    Expanding unconditionally measurably backfires. Run hybrid-reranked-v3 (expand everything)
    against v2 (expand nothing): composed_animation recall@10 rose 0.615 -> 0.923, but
    node_lookup fell 1.000 -> 0.357 and parameter_lookup 1.000 -> 0.350, dropping overall
    recall@10 from 0.925 to 0.627. Lookup questions ("what are the exact names of the Transform
    node's two inputs?") already use manual vocabulary, so paraphrasing them through a 0.5B model
    and appending glossary terms only corrupts an already-optimal query. No match here means the
    question passes through untouched, byte-identical to the v2 behaviour those scores came from.
    """
    if not _is_procedural(question):
        return question
    glossary = _glossary_terms(question)
    if not glossary:
        return question
    try:
        rewritten = _generate(_REWRITE_PROMPT.format(question=question), max_new_tokens=64)
        rewritten = rewritten.splitlines()[0].strip() if rewritten else ""
        rewritten = rewritten if rewritten else question
    except Exception:
        rewritten = question
    return f"{rewritten} {glossary}"


# Kept deliberately close to the plain original wording. Two attempts at tightening this to stop
# it over-claiming "sufficient" both backfired — a 0.5B model swings hard on small prompt edits,
# and it started calling genuinely-relevant primitives "insufficient". The over-claiming it was
# meant to patch turned out to be caused by garbage retrieval upstream (see _CONCEPT_VOCABULARY),
# not by this prompt. Fix the input, not the judge.
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
