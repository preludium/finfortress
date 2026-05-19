from __future__ import annotations

from typing import List, Literal, Optional

from langchain_core.documents import Document
from typing_extensions import TypedDict


class Citation(TypedDict):
    source: str
    author: str
    url: str
    title: str
    date: str


class AgentState(TypedDict):
    question: str
    query_type: Literal["factual", "calculation", "comparison", "advice"]
    needs_live_data: bool
    context: List[Document]
    avg_grade: float
    needs_rewrite: bool
    stale_data: bool
    rewrite_count: int
    current_query: Optional[str]   # None = use question; set by rewrite node
    live_data: Optional[str]
    answer: Optional[str]
    citations: Optional[List[Citation]]
    confidence: Optional[Literal["high", "medium", "low"]]
    disclaimer: Optional[str]
    give_up: bool
    history: List[dict]            # [{"question": ..., "answer": ...}, ...]


INITIAL_STATE: AgentState = {
    "question": "",
    "query_type": "factual",
    "needs_live_data": False,
    "context": [],
    "avg_grade": 0.0,
    "needs_rewrite": False,
    "stale_data": False,
    "rewrite_count": 0,
    "current_query": None,
    "live_data": None,
    "answer": None,
    "citations": None,
    "confidence": None,
    "disclaimer": None,
    "give_up": False,
    "history": [],
}
