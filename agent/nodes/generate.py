from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

from agent.state import AgentState, Citation
from agent.prompts.generate import GENERATE_SYSTEM, GENERATE_USER, ADVICE_DISCLAIMER

log = logging.getLogger(__name__)

LLM_MODEL       = os.getenv("LLM_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None
GRADE_THRESHOLD = float(os.getenv("GRADE_THRESHOLD", "0.6"))


class _CitationModel(BaseModel):
    source: str = ""
    author: str = ""
    url: str = ""
    title: str = ""
    date: str = ""


class _GenerateResult(BaseModel):
    answer: str = ""
    citations: list[_CitationModel] = Field(default_factory=list)
    confidence: str = "low"
    disclaimer: Optional[str] = None


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


def _format_history(history: list) -> str:
    if not history:
        return ""
    turns = history[-5:]
    lines = ["HISTORIA ROZMOWY (ostatnie tury — uwzględnij przy odpowiedzi):"]
    for turn in turns:
        lines.append(f"Użytkownik: {turn['question']}")
        answer_preview = turn["answer"][:400]
        if len(turn["answer"]) > 400:
            answer_preview += "…"
        lines.append(f"Asystent: {answer_preview}")
    return "\n".join(lines)


def _format_context(chunks) -> str:
    parts = []
    for i, doc in enumerate(chunks, 1):
        meta = doc.metadata
        header = f"[{i}] {meta.get('source','?')} | {meta.get('author','?')} | {meta.get('date','?')} | {meta.get('title','')[:60]}"
        parts.append(f"{header}\n{doc.page_content[:800]}")
    return "\n\n".join(parts)


def build_generate_node(profile_block: str = "") -> Callable[[AgentState], dict]:

    def generate(state: AgentState) -> dict:
        llm         = _get_llm()
        question    = state["question"]
        context     = state.get("context", [])
        query_type  = state.get("query_type", "factual")
        avg_grade   = state.get("avg_grade", 0.0)
        live_data   = state.get("live_data")
        history     = list(state.get("history") or [])
        calc_result = state.get("calc_result")
        today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Calculator and live data are deterministic — RAG grade is irrelevant for confidence
        if calc_result or live_data:
            confidence = "high"
        else:
            confidence = _confidence(avg_grade)

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
        calc_result_block = (
            f"Calculator result (exact — use these numbers, do not recalculate): {calc_result}"
            if calc_result
            else ""
        )

        system = GENERATE_SYSTEM.format(today=today)
        user = GENERATE_USER.format(
            question=question,
            query_type=query_type,
            avg_grade=avg_grade,
            confidence=confidence,
            today=today,
            history_block=_format_history(history),
            profile_block=profile_block,
            disclaimer_block=disclaimer_block,
            live_data_block=live_data_block,
            calc_result_block=calc_result_block,
            context_text=_format_context(context),
        )

        log.info("Generate | model=%s confidence=%s chunks=%d", LLM_MODEL, confidence, len(context))
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        try:
            result: _GenerateResult = llm.with_structured_output(
                _GenerateResult, method="json_mode"
            ).invoke(messages)
            answer = result.answer
            citations: list[Citation] = [
                {"source": c.source, "author": c.author, "url": c.url, "title": c.title, "date": c.date}
                for c in result.citations
            ]
            confidence = result.confidence or confidence
        except Exception as exc:
            log.warning("Generate structured output failed: %s — falling back to raw answer", exc)
            raw = llm.invoke(messages).content
            answer = raw
            citations = []
            # confidence stays as computed above

        disclaimer = ADVICE_DISCLAIMER if query_type == "advice" else None
        history.append({"question": question, "answer": answer})
        log.info("Generated answer (%d chars), history now %d turns", len(answer), len(history))

        return {
            "answer":     answer,
            "citations":  citations,
            "confidence": confidence,
            "disclaimer": disclaimer,
            "history":    history[-10:],
        }

    return generate
