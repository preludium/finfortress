from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    thread_id: Optional[str] = None


class CitationModel(BaseModel):
    source: str
    author: str
    url: str
    title: str
    date: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationModel]
    confidence: Optional[str]
    disclaimer: Optional[str]
    avg_grade: float
    query_type: str
    rewrite_count: int
    give_up: bool
    thread_id: Optional[str] = None
