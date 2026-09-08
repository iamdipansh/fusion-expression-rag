from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import query
from app.schemas import HealthResponse
from config import settings

app = FastAPI(title="Fusion Expression RAG", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)


@app.get("/health", response_model=HealthResponse)
async def health(probe: str | None = None) -> HealthResponse:
    """`?probe=pipeline` additionally runs one real retrieval and one sufficiency-gate call and
    reports what each returned. Opt-in because the gate call spends Gemini free-tier quota."""
    from retrieval.store import index_diagnostics

    diagnostics = index_diagnostics()
    if probe == "pipeline":
        from generation.synthesize import classify_sufficiency_remote
        from retrieval.hybrid import retrieve

        question = "how can I use polyline expressions to build a circle"
        try:
            chunks = retrieve(question)
            diagnostics["probe_chunks"] = len(chunks)
            diagnostics["probe_top"] = chunks[0].breadcrumb if chunks else None
            diagnostics["probe_sufficiency"] = await classify_sufficiency_remote(question, chunks)
        except Exception as e:
            diagnostics["probe_error"] = f"{type(e).__name__}: {e}"

    return HealthResponse(
        status="ok",
        index_loaded=settings.lancedb_uri.exists(),
        retrieval_mode=settings.retrieval_mode,
        index=diagnostics,
    )
