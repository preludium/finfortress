from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

from agent.state import AgentState
from agent.prompts.profile_suggest import PROFILE_SUGGEST_SYSTEM, PROFILE_SUGGEST_USER

log = logging.getLogger(__name__)

LLM_MODEL        = os.getenv("LLM_MODEL", "gpt-4o")
OPENAI_BASE_URL  = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY") or None
PROFILE_AUTOSAVE = os.getenv("PROFILE_AUTOSAVE", "false").lower() not in ("0", "false", "no")
PROFILE_PATH     = ROOT / "data" / "user_profile.md"


class _SuggestResult(BaseModel):
    answer: str = ""
    citations: list = Field(default_factory=list)
    confidence: str = "high"
    disclaimer: str | None = None


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    kwargs = dict(model=LLM_MODEL, temperature=0.1, api_key=OPENAI_API_KEY)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def _format_history(history: list) -> str:
    if not history:
        return "(no previous context)"
    turns = history[-3:]
    lines = []
    for turn in turns:
        lines.append(f"User: {turn['question']}")
        lines.append(f"Assistant: {turn['answer'][:300]}")
    return "\n".join(lines)


def build_profile_suggest_node(profile_block: str = "") -> Callable[[AgentState], dict]:

    def profile_suggest(state: AgentState) -> dict:
        llm      = _get_llm()
        question = state["question"]
        history  = list(state.get("history") or [])

        user_msg = PROFILE_SUGGEST_USER.format(
            question=question,
            history_block=_format_history(history),
            profile_block=profile_block or "(empty)",
        )

        messages = [SystemMessage(content=PROFILE_SUGGEST_SYSTEM), HumanMessage(content=user_msg)]
        try:
            result: _SuggestResult = llm.with_structured_output(
                _SuggestResult, method="json_mode"
            ).invoke(messages)
            answer = result.answer
        except Exception as exc:
            log.warning("profile_suggest structured output failed: %s — falling back to raw", exc)
            answer = llm.invoke(messages).content

        if PROFILE_AUTOSAVE and PROFILE_PATH.exists():
            with open(PROFILE_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n\n<!-- auto-saved by FinFortress -->\n{answer}")
            log.info("profile_suggest: auto-saved to %s", PROFILE_PATH)
            answer += "\n\n_(Zapisano automatycznie do profilu. Zrestartuj aplikację żeby zmiany były aktywne.)_"

        history.append({"question": question, "answer": answer})
        log.info("profile_suggest: answered (%d chars)", len(answer))

        return {
            "answer":     answer,
            "citations":  [],
            "confidence": "high",
            "disclaimer": None,
            "give_up":    False,
            "history":    history[-10:],
        }

    return profile_suggest
