from fastapi import APIRouter, HTTPException

from app.schemas import QueryRequest, QueryResponse
from generation.synthesize import NoGenerationKeyError
from retrieval.hybrid import answer_query

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        return await answer_query(request.question, request.anthropic_api_key)
    except NoGenerationKeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
