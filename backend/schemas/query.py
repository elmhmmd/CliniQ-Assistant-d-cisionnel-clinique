from datetime import datetime

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    specialty: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    response_time_ms: float


class HistoryItem(BaseModel):
    id: int
    question: str
    specialty: str | None
    answer: str
    sources: list[dict]
    response_time_ms: float
    created_at: datetime

    model_config = {"from_attributes": True}
