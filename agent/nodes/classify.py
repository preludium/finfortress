from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

from agent.state import AgentState
from agent.prompts.classify import CLASSIFY_SYSTEM, CLASSIFY_USER

log = logging.getLogger(__name__)

GRADER_MODEL    = os.getenv("GRADER_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None


class ClassifyResult(BaseModel):
    query_type: Literal["factual", "calculation", "comparison", "advice"] = "factual"
    needs_live_data: bool = False


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=GRADER_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def classify(state: AgentState) -> dict:
    llm      = _get_llm()
    question = state["question"]
    try:
        result: ClassifyResult = llm.with_structured_output(
            ClassifyResult, method="json_mode"
        ).invoke([
            SystemMessage(content=CLASSIFY_SYSTEM),
            HumanMessage(content=CLASSIFY_USER.format(question=question)),
        ])
        query_type = result.query_type
        needs_live = result.needs_live_data
    except Exception as exc:
        # Visible error — not silent. Fallback keeps the graph alive but
        # "factual, no live data" is wrong for most questions, so log at ERROR
        # so LangSmith and local logs both surface this.
        log.error("Classify structured output failed: %s — defaulting to factual", exc)
        query_type = "factual"
        needs_live = False

    log.info("Classify: query_type=%s needs_live_data=%s", query_type, needs_live)
    return {"query_type": query_type, "needs_live_data": needs_live}
