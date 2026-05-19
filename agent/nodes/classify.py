from __future__ import annotations

import json
import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.state import AgentState
from agent.prompts.classify import CLASSIFY_SYSTEM, CLASSIFY_USER

log = logging.getLogger(__name__)

GRADER_MODEL    = os.getenv("GRADER_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=GRADER_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def classify(state: AgentState) -> dict:
    llm = _get_llm()
    question = state["question"]
    raw = llm.invoke([
        SystemMessage(content=CLASSIFY_SYSTEM),
        HumanMessage(content=CLASSIFY_USER.format(question=question)),
    ]).content
    cleaned = re.sub(r"```json?\n?|```", "", raw).strip()
    try:
        result = json.loads(cleaned)
        query_type = result.get("query_type", "factual")
        needs_live = bool(result.get("needs_live_data", False))
    except (json.JSONDecodeError, ValueError):
        log.warning("Classify parse error — defaulting to factual. raw: %r", raw[:100])
        query_type = "factual"
        needs_live = False

    log.info("Classify: query_type=%s needs_live_data=%s", query_type, needs_live)
    return {"query_type": query_type, "needs_live_data": needs_live}
