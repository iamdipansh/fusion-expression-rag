"""API request/response contracts. Kept stable so the client can be built against them
before the retrieval pipeline behind them exists."""

from pydantic import BaseModel

from config import AnswerTier, ContentType, Sufficiency


class QueryRequest(BaseModel):
    question: str
    anthropic_api_key: str | None = None  # BYOK, session-only — never persisted or logged


class Citation(BaseModel):
    breadcrumb: str
    page_start: int
    page_end: int
    content_type: ContentType


class QueryResponse(BaseModel):
    tier: AnswerTier
    sufficiency: Sufficiency
    answer: str
    citations: list[Citation]


class HealthResponse(BaseModel):
    status: str
    index_loaded: bool
    retrieval_mode: str
    # Counts and versions only, never chunk text — `index_loaded` alone proved useless on the
    # first Render deploy, reporting true while every query retrieved nothing.
    index: dict[str, object] = {}
