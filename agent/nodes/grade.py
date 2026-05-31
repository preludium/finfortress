from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.state import AgentState
from agent.prompts.grade import GRADE_SYSTEM, GRADE_USER

log = logging.getLogger(__name__)

GRADE_THRESHOLD = float(os.getenv("GRADE_THRESHOLD", "0.6"))
STALE_MONTHS    = int(os.getenv("STALE_MONTHS", "18"))
GRADER_MODEL    = os.getenv("GRADER_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None


class GradeResult(BaseModel):
    score: float = 0.0
    temporal_mismatch: bool = False
    reason: str = ""


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=GRADER_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


async def _grade_chunk_async(llm: ChatOpenAI, question: str, chunk, today: str) -> GradeResult:
    date   = chunk.metadata.get("date", "unknown")
    source = chunk.metadata.get("source", "unknown")
    system = GRADE_SYSTEM.format(stale_months=STALE_MONTHS, today=today)
    user   = GRADE_USER.format(
        question=question,
        date=date,
        source=source,
        chunk_text=chunk.page_content[:1000],
    )
    return await llm.with_structured_output(
        GradeResult, method="json_mode"
    ).ainvoke([SystemMessage(content=system), HumanMessage(content=user)])


def build_grade_node() -> Callable[[AgentState], Awaitable[dict]]:

    async def grade(state: AgentState) -> dict:
        llm      = _get_llm()
        question = state["question"]
        context  = state.get("context", [])
        today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not context:
            log.warning("Grade node: empty context — forcing rewrite")
            return {"avg_grade": 0.0, "needs_rewrite": True, "stale_data": False}

        # All chunks graded in parallel — 6× faster than sequential LLM calls.
        # Each coroutine gets the same shared ChatOpenAI instance (httpx pool is
        # concurrency-safe), so no lock or per-chunk client needed.
        async def _safe_grade(i: int, chunk) -> GradeResult:
            try:
                return await _grade_chunk_async(llm, question, chunk, today)
            except Exception as exc:
                log.error("Grade chunk [%d] failed: %s — defaulting score=0.0", i + 1, exc)
                return GradeResult(score=0.0, temporal_mismatch=False, reason="error")

        results = await asyncio.gather(*[
            _safe_grade(i, chunk) for i, chunk in enumerate(context)
        ])

        scores: list[float] = []
        stale = False

        # Log in original order (gather preserves input order)
        for i, result in enumerate(results):
            scores.append(result.score)
            if result.temporal_mismatch:
                stale = True
            log.info(
                "  chunk [%d/%d] score=%.2f temporal_mismatch=%s | %s",
                i + 1, len(context), result.score, result.temporal_mismatch, result.reason[:80],
            )

        avg = sum(scores) / len(scores)
        # Rewrite only when relevance is poor. Stale data alone (good relevance
        # score but old docs) triggers one rewrite attempt for fresher content,
        # but does not block generation — generate node will note low confidence.
        needs_rewrite = avg < GRADE_THRESHOLD or (stale and avg < 0.85)

        log.info(
            "Grade result: avg=%.2f threshold=%.2f stale=%s needs_rewrite=%s",
            avg, GRADE_THRESHOLD, stale, needs_rewrite,
        )

        return {
            "avg_grade":     avg,
            "stale_data":    stale,
            "needs_rewrite": needs_rewrite,
        }

    return grade
