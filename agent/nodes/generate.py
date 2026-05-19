from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.state import AgentState, Citation
from agent.prompts.generate import GENERATE_SYSTEM, GENERATE_USER, ADVICE_DISCLAIMER

log = logging.getLogger(__name__)

LLM_MODEL       = os.getenv("LLM_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None
GRADE_THRESHOLD = float(os.getenv("GRADE_THRESHOLD", "0.6"))


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=LLM_MODEL, temperature=0.2, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def _confidence(avg_grade: float) -> str:
    if avg_grade >= 0.8:
        return "high"
    if avg_grade >= GRADE_THRESHOLD:
        return "medium"
    return "low"


def _format_context(chunks) -> str:
    parts = []
    for i, doc in enumerate(chunks, 1):
        meta = doc.metadata
        header = f"[{i}] {meta.get('source','?')} | {meta.get('author','?')} | {meta.get('date','?')} | {meta.get('title','')[:60]}"
        parts.append(f"{header}\n{doc.page_content[:800]}")
    return "\n\n".join(parts)


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"```json?\n?|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Generate parse error: %s | raw: %r", exc, raw[:200])
        return {
            "answer": raw,
            "citations": [],
            "confidence": "low",
            "disclaimer": None,
        }


def build_generate_node(profile_block: str = "") -> Callable[[AgentState], dict]:

    def generate(state: AgentState) -> dict:
        llm         = _get_llm()
        question    = state["question"]
        context     = state.get("context", [])
        query_type  = state.get("query_type", "factual")
        avg_grade   = state.get("avg_grade", 0.0)
        live_data   = state.get("live_data")
        today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        confidence  = _confidence(avg_grade)

        disclaimer_block = (
            f"Disclaimer to include: {ADVICE_DISCLAIMER}"
            if query_type == "advice"
            else ""
        )
        live_data_block = (
            f"Live data (use for current rates): {live_data}"
            if live_data
            else ""
        )

        system = GENERATE_SYSTEM.format(today=today)
        user = GENERATE_USER.format(
            question=question,
            query_type=query_type,
            avg_grade=avg_grade,
            confidence=confidence,
            today=today,
            profile_block=profile_block,
            disclaimer_block=disclaimer_block,
            live_data_block=live_data_block,
            context_text=_format_context(context),
        )

        log.info("Generate | model=%s confidence=%s chunks=%d", LLM_MODEL, confidence, len(context))
        raw = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
        parsed = _parse_response(raw)

        citations: list[Citation] = []
        for c in parsed.get("citations", []):
            citations.append({
                "source":  str(c.get("source", "")),
                "author":  str(c.get("author", "")),
                "url":     str(c.get("url", "")),
                "title":   str(c.get("title", "")),
                "date":    str(c.get("date", "")),
            })

        disclaimer = ADVICE_DISCLAIMER if query_type == "advice" else None

        log.info("Generated answer (%d chars)", len(parsed.get("answer", "")))

        return {
            "answer":     parsed.get("answer", ""),
            "citations":  citations,
            "confidence": parsed.get("confidence", confidence),
            "disclaimer": disclaimer,
        }

    return generate
