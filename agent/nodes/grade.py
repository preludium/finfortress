from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

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


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=GRADER_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def _parse_grade(raw: str) -> dict:
    """Strip markdown fences and parse JSON. Returns default on failure."""
    cleaned = re.sub(r"```json?\n?|```", "", raw).strip()
    try:
        result = json.loads(cleaned)
        return {
            "score": float(result.get("score", 0.0)),
            "temporal_mismatch": bool(result.get("temporal_mismatch", False)),
            "reason": str(result.get("reason", "")),
        }
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Grade parse error: %s | raw: %r", exc, raw[:120])
        return {"score": 0.0, "temporal_mismatch": False, "reason": "parse error"}


async def _grade_chunk_async(llm: ChatOpenAI, question: str, chunk, today: str) -> dict:
    date   = chunk.metadata.get("date", "unknown")
    source = chunk.metadata.get("source", "unknown")
    system = GRADE_SYSTEM.format(stale_months=STALE_MONTHS, today=today)
    user   = GRADE_USER.format(
        question=question,
        date=date,
        source=source,
        chunk_text=chunk.page_content[:1000],
    )
    raw = (await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])).content
    return _parse_grade(raw)


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
        async def _safe_grade(i: int, chunk) -> dict:
            try:
                return await _grade_chunk_async(llm, question, chunk, today)
            except Exception as exc:
                log.warning("Grade chunk [%d] failed: %s — defaulting score=0.0", i + 1, exc)
                return {"score": 0.0, "temporal_mismatch": False, "reason": "error"}

        results = await asyncio.gather(*[
            _safe_grade(i, chunk) for i, chunk in enumerate(context)
        ])

        scores: list[float] = []
        stale = False

        # Log in original order (gather preserves input order)
        for i, result in enumerate(results):
            score    = result["score"]
            mismatch = result["temporal_mismatch"]
            scores.append(score)
            if mismatch:
                stale = True
            log.info(
                "  chunk [%d/%d] score=%.2f temporal_mismatch=%s | %s",
                i + 1, len(context), score, mismatch, result["reason"][:80],
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
            "avg_grade":    avg,
            "stale_data":   stale,
            "needs_rewrite": needs_rewrite,
        }

    return grade
