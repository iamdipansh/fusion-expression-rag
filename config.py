"""Single source of configuration. No constants scattered elsewhere."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_ROOT = Path(__file__).resolve().parent
DATA_DIR = SERVER_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"
INDEX_DIR = DATA_DIR / "index"

ContentType = Literal["prose", "table", "parameter_reference", "code_example", "ui_description"]
AnswerTier = Literal["GROUNDED", "SYNTHESIZED", "UNVERIFIED"]
Sufficiency = Literal["sufficient", "partial", "insufficient"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FUSION_RAG_", env_file=".env")

    # Manual identity — locked per the "ask before assuming" note in CLAUDE.md.
    manual_version: str = "21"
    manual_pdf_path: Path = RAW_DIR / "DaVinci Resolve Manual.pdf"

    # Ingestion / chunking (CLAUDE.md: structure-aware, 400-800 tokens, ~15% overlap)
    parsed_pages_path: Path = PARSED_DIR / "pages.jsonl"
    chunks_path: Path = PARSED_DIR / "chunks.jsonl"
    chunk_target_tokens: int = 600
    chunk_min_tokens: int = 400
    chunk_max_tokens: int = 800
    chunk_overlap_ratio: float = 0.15

    # Embedding + rerank (local, free — see "Why free is not a compromise")
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_onnx_quantized: bool = True

    # Retrieval — hybrid, non-negotiable
    lancedb_uri: Path = INDEX_DIR / "fusion_manual.lancedb"
    lancedb_table: str = "chunks"
    rrf_k: int = 60
    retrieval_candidates: int = 30
    rerank_top_k: int = 8

    # Generation — BYOK, session-only key, never persisted (see conventions)
    anthropic_model: str = "claude-sonnet-5"
    gemini_fallback_model: str = "gemini-2.0-flash"
    # Query expansion + sufficiency gate — no API key required, small enough to sit alongside
    # bge-m3 + the reranker in memory (see the milestone-4 memory notes: shrink models before
    # tuning RAM further).
    local_expansion_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    # Operator-provisioned, server-side only — distinct from the per-request BYOK
    # anthropic_api_key above. Powers the reduced-quality fallback for callers with no Anthropic
    # key. Optional: unset means callers without a key get a clear "no key" error, not a
    # degraded answer from a key that doesn't exist.
    gemini_api_key: str | None = None

    # API
    cors_origins: list[str] = ["http://localhost:3000"]
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
