"""Final answer synthesis — the BYOK half of the generation split (see "Generation: bring your
own key" in CLAUDE.md). Claude does the real composition when the caller supplies a key; Gemini
is an operator-provisioned, reduced-quality fallback for callers who don't, clearly labelled in
the returned text per CLAUDE.md's "Answer tiering" section. Neither key present is a hard error,
not a degraded answer — there is nothing to generate one with.
"""

from config import AnswerTier, Sufficiency, settings
from ingestion.chunk import Chunk

TIER_FOR_SUFFICIENCY: dict[Sufficiency, AnswerTier] = {
    "sufficient": "GROUNDED",
    "partial": "SYNTHESIZED",
    "insufficient": "UNVERIFIED",
}


class NoGenerationKeyError(Exception):
    """Neither a caller-supplied Anthropic key nor an operator-configured Gemini fallback key
    is available — there is nothing to synthesize an answer with."""


_SYSTEM_PROMPTS: dict[AnswerTier, str] = {
    "GROUNDED": (
        "You are grounding Fusion (DaVinci Resolve) expression syntax against the official "
        "manual. The excerpts below directly answer the question. Compose your answer using "
        "ONLY node names, input names, and syntax that appear in the excerpts — never invent a "
        "node or parameter name. Cite the page number(s) for every claim."
    ),
    "SYNTHESIZED": (
        "You are grounding Fusion (DaVinci Resolve) expression syntax against the official "
        "manual. The excerpts below give verified primitives (functions, variables, node/input "
        "names) but not a direct recipe for what the user asked — the manual documents "
        "primitives, not animation recipes. Compose the requested animation math (e.g. a spring "
        "or bounce curve) on top of ONLY the verified primitives in the excerpts, citing page "
        "numbers for each primitive you use. Clearly mark which parts are directly from the "
        "manual and which parts you composed."
    ),
    "UNVERIFIED": (
        "No relevant excerpts from the DaVinci Resolve manual were retrieved for this question. "
        "Answer from general knowledge if you can, but you MUST start your answer with a clear "
        "warning that this is UNVERIFIED against the manual and specific node/parameter names "
        "or syntax may be wrong."
    ),
}


def _build_user_message(question: str, chunks: list[Chunk]) -> str:
    if not chunks:
        return f"Question: {question}\n\n(No manual excerpts were retrieved.)"
    excerpts = "\n\n".join(
        f"--- p.{c.page_start}-{c.page_end} [{c.breadcrumb}] ---\n{c.text}" for c in chunks
    )
    return f"Question: {question}\n\nManual excerpts:\n{excerpts}"


async def _synthesize_with_claude(
    question: str, chunks: list[Chunk], tier: AnswerTier, api_key: str
) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPTS[tier],
        messages=[{"role": "user", "content": _build_user_message(question, chunks)}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


async def _synthesize_with_gemini(question: str, chunks: list[Chunk], tier: AnswerTier) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_fallback_model,
        contents=_build_user_message(question, chunks),
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPTS[tier]),
    )
    warning = (
        "⚠️ Reduced quality: generated with the free Gemini fallback — no Anthropic key was "
        "provided.\n\n"
    )
    return warning + (response.text or "")


async def synthesize(
    question: str, chunks: list[Chunk], tier: AnswerTier, anthropic_api_key: str | None
) -> str:
    if anthropic_api_key:
        return await _synthesize_with_claude(question, chunks, tier, anthropic_api_key)
    if settings.gemini_api_key:
        return await _synthesize_with_gemini(question, chunks, tier)
    raise NoGenerationKeyError(
        "No Anthropic API key was provided and no Gemini fallback is configured on the server."
    )
