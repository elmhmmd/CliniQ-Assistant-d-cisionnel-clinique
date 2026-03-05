import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.security import decode_token
from backend.models.query_log import QueryLog
from backend.models.user import User
from backend.schemas.query import HistoryItem, QueryRequest, QueryResponse
from rag.mlflow_logger import log_query as mlflow_log_query
from rag.pipeline import Pipeline, SYSTEM_PROMPT

router = APIRouter()
bearer = HTTPBearer()

_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(
            model=settings.ollama_model,
            top_k=settings.retriever_k,
            tracking_uri=settings.mlflow_tracking_uri,
        )
    return _pipeline


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    background_tasks: BackgroundTasks,
    pipeline: Pipeline = Depends(get_pipeline),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t0 = time.monotonic()
    result = pipeline.query(body.question, specialty=body.specialty)
    elapsed_ms = (time.monotonic() - t0) * 1000

    log = QueryLog(
        user_id=user.id,
        question=body.question,
        specialty=body.specialty,
        answer=result["answer"],
        sources=result["sources"],
        response_time_ms=elapsed_ms,
    )
    db.add(log)
    db.commit()

    background_tasks.add_task(
        mlflow_log_query,
        question=body.question,
        answer=result["answer"],
        contexts=result["contexts"],
        response_time_ms=elapsed_ms,
        llm_model=settings.ollama_model,
        top_k=settings.retriever_k,
        system_prompt=SYSTEM_PROMPT,
    )

    return QueryResponse(
        answer=result["answer"],
        sources=result["sources"],
        response_time_ms=elapsed_ms,
    )


@router.get("/history", response_model=list[HistoryItem])
def history(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(QueryLog)
        .filter(QueryLog.user_id == user.id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .all()
    )
