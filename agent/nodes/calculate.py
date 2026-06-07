from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

from typing import Callable

from agent.state import AgentState
from agent.prompts.calculate import CALCULATE_SYSTEM, CALCULATE_USER


class CalculateRequest(BaseModel):
    formula: str = "none"
    params: dict = {}

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


def _format_result(formula: str, result: dict) -> str:
    lines = [f"Calculator ({formula}):"]
    for k, v in result.items():
        if k == "note":
            continue
        if isinstance(v, float):
            lines.append(f"  {k}: {v:,.2f}" if v > 100 else f"  {k}: {v:.4f}")
        else:
            lines.append(f"  {k}: {v}")
    if "note" in result:
        lines.append(f"  note: {result['note']}")
    return "\n".join(lines)


def build_calculate_node(profile_block: str = "") -> Callable[[AgentState], dict]:

    def calculate(state: AgentState) -> dict:
        if state.get("query_type") != "calculation":
            return {"calc_result": None}

        question = state["question"]

        try:
            llm = _get_llm()
            parsed: CalculateRequest = llm.with_structured_output(
                CalculateRequest, method="json_mode"
            ).invoke([
                SystemMessage(content=CALCULATE_SYSTEM),
                HumanMessage(content=CALCULATE_USER.format(
                    question=question,
                    profile_block=profile_block,
                )),
            ])
        except Exception as exc:
            log.error("Calculate structured output failed: %s — skipping calculator", exc)
            return {"calc_result": None}

        formula = parsed.formula
        params  = parsed.params
        log.info("Calculate: formula=%s params=%s", formula, params)

        if formula == "none":
            return {"calc_result": None}

        try:
            from agent.tools.calculator import (
                ikze_tax_shield,
                ike_ikze_limits,
                belka_tax,
                mortgage_vs_investment,
                cash_allocation,
                bk2_overpayment,
                retirement_projector,
            )
            dispatch = {
                "ikze_shield":           ikze_tax_shield,
                "ike_ikze_limits":       ike_ikze_limits,
                "belka":                 belka_tax,
                "mortgage_vs_invest":    mortgage_vs_investment,
                "cash_allocation":       cash_allocation,
                "bk2_overpayment":       bk2_overpayment,
                "retirement_projector":  retirement_projector,
            }
            fn = dispatch.get(formula)
            if fn is None:
                log.warning("Calculate: unknown formula %r", formula)
                return {"calc_result": None}

            result = fn(**params)
            calc_result = _format_result(formula, result)
            log.info("Calculate: result ready (%d chars)", len(calc_result))
            return {"calc_result": calc_result}

        except Exception as exc:
            log.warning("Calculate execution error (formula=%s): %s", formula, exc)
            return {"calc_result": None}

    return calculate
