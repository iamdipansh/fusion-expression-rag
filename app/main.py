from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import query
from app.schemas import HealthResponse
from config import settings

app = FastAPI(title="Fusion Expression RAG", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    index_loaded = settings.lancedb_uri.exists()
    return HealthResponse(status="ok", index_loaded=index_loaded)
