"""Final answer synthesis — the BYOK half of the generation split (see "Generation: bring your
own key" in CLAUDE.md). Claude does the real composition when the caller supplies a key; Gemini
is an operator-provisioned, reduced-quality fallback for callers who don't, clearly labelled in
the returned text per CLAUDE.md's "Answer tiering" section. Neither key present is a hard error,
not a degraded answer — there is nothing to generate one with.
"""

import asyncio
import logging
import re

from config import AnswerTier, Sufficiency, settings
from ingestion.chunk import Chunk

logger = logging.getLogger(__name__)

TIER_FOR_SUFFICIENCY: dict[Sufficiency, AnswerTier] = {
    "sufficient": "GROUNDED",
    "partial": "SYNTHESIZED",
    "insufficient": "UNVERIFIED",
}


class NoGenerationKeyError(Exception):
    """Neither a caller-supplied Anthropic key nor an operator-configured Gemini fallback key
    is available — there is nothing to synthesize an answer with."""


class GenerationUnavailableError(Exception):
    """The generation provider refused the request — free-tier quota exhausted, most likely.

    Distinct from NoGenerationKeyError: a key exists and the request was well-formed, so this is
    temporary and the caller should be told to retry rather than to go find a key. Raised instead
    of letting the provider's exception surface as a bare 500, which tells a reader nothing."""


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


def _gate_unavailable(chunks: list[Chunk]) -> Sufficiency:
    """What to answer when the gate couldn't reach a judgement at all.

    Not "insufficient". That word means "the excerpts are not relevant", and a rate-limited or
    erroring API call establishes nothing of the sort. Answering it anyway was actively
    misleading: UNVERIFIED drops the citations, while `synthesize` still receives the chunks and
    grounds the answer in them — so the deployed app was returning manual-grounded answers while
    telling the reader nothing relevant had been found and hiding the pages it used.

    With chunks in hand, "partial" is the honest reading: the manual supplied something, and
    SYNTHESIZED already instructs the model to mark what it composed versus what it cited. It
    keeps the provenance visible without claiming the stronger GROUNDED. With no chunks there is
    genuinely nothing, and "insufficient" is correct.
    """
    return "partial" if chunks else "insufficient"


async def classify_sufficiency_remote(question: str, chunks: list[Chunk]) -> Sufficiency:
    """The sufficiency gate for lexical retrieval mode, which loads no local model to ask.

    Uses the same prompt as generation/local_llm.py's local classifier, so the two gates ask one
    question of different models rather than drifting apart.

    A judgement of "insufficient" is only ever returned when the model actually says so, or when
    there is nothing to judge. Everything else — rate limits, errors, unparseable replies — goes
    through `_gate_unavailable`, which explains why that distinction matters.
    """
    from generation.local_llm import SUFFICIENCY_LABELS, build_sufficiency_prompt

    if not chunks:
        return "insufficient"
    if not settings.gemini_api_key:
        logger.warning("sufficiency gate: no Gemini key configured")
        return _gate_unavailable(chunks)

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = build_sufficiency_prompt(question, chunks)
    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=settings.gemini_fallback_model, contents=prompt
            )
            raw = (response.text or "").lower()
            for label in SUFFICIENCY_LABELS:
                if re.search(rf"\b{label}\b", raw):
                    return label
            logger.warning("sufficiency gate: unparseable reply %r", raw[:120])
            return _gate_unavailable(chunks)
        except Exception:
            # The free tier's per-minute limit is easy to trip at two calls per question, and it
            # clears in seconds — so one short retry is worth it before giving up.
            if attempt == 0:
                logger.warning("sufficiency gate: call failed, retrying once")
                await asyncio.sleep(3)
                continue
            logger.exception("sufficiency gate: call failed twice")
            return _gate_unavailable(chunks)
    return _gate_unavailable(chunks)


async def synthesize(
    question: str, chunks: list[Chunk], tier: AnswerTier, anthropic_api_key: str | None
) -> str:
    if anthropic_api_key:
        try:
            return await _synthesize_with_claude(question, chunks, tier, anthropic_api_key)
        except Exception as e:
            logger.exception("Claude synthesis failed")
            raise GenerationUnavailableError(
                "Claude rejected the request — check that the API key is valid and has credit."
            ) from e
    if settings.gemini_api_key:
        try:
            return await _synthesize_with_gemini(question, chunks, tier)
        except Exception as e:
            logger.exception("Gemini synthesis failed")
            raise GenerationUnavailableError(
                "The free Gemini fallback is temporarily unavailable, most likely its daily "
                "quota. Add your own Anthropic API key to bypass the shared limit, or try again "
                "later."
            ) from e
    raise NoGenerationKeyError(
        "No Anthropic API key was provided and no Gemini fallback is configured on the server."
    )
