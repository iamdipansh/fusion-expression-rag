from fastapi import APIRouter, HTTPException

from app.schemas import QueryRequest, QueryResponse
from generation.synthesize import GenerationUnavailableError, NoGenerationKeyError
from retrieval.hybrid import answer_query

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        return await answer_query(request.question, request.anthropic_api_key)
    except NoGenerationKeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except GenerationUnavailableError as e:
        # 503, not 500: the request was fine and retrying may well work. A bare 500 left the UI
        # showing "Something went wrong" for what is really "the free quota ran out".
        raise HTTPException(status_code=503, detail=str(e)) from e
