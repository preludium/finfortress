from __future__ import annotations

import logging
import os
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
from agent.prompts.rewrite import REWRITE_SYSTEM, REWRITE_USER

log = logging.getLogger(__name__)

GRADER_MODEL    = os.getenv("GRADER_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or None


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=GRADER_MODEL, temperature=0.3, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def rewrite(state: AgentState) -> dict:
    llm          = _get_llm()
    question     = state["question"]
    stale        = state.get("stale_data", False)
    rewrite_count = state.get("rewrite_count", 0)
    context      = state.get("context", [])

    reason = "STALE DATA — documents are outdated for this question" if stale else "LOW RELEVANCE — retrieved chunks do not answer the question"
    chunk_titles = ", ".join(
        doc.metadata.get("title", "?")[:40] for doc in context[:3]
    ) or "none"

    raw = llm.invoke([
        SystemMessage(content=REWRITE_SYSTEM),
        HumanMessage(content=REWRITE_USER.format(
            question=question,
            reason=reason,
            chunk_titles=chunk_titles,
        )),
    ]).content

    # Extract first non-empty line — guards against multi-line LLM responses
    lines = [ln.strip().strip('"').strip("'") for ln in raw.splitlines() if ln.strip()]
    new_query = lines[0] if lines else raw.strip()
    log.info("Rewrite [%d]: %r → %r", rewrite_count + 1, question[:60], new_query[:60])

    return {
        "current_query": new_query,
        "rewrite_count": rewrite_count + 1,
        "needs_rewrite": False,
    }
