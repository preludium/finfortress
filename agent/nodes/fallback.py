from __future__ import annotations

import logging

from agent.state import AgentState

log = logging.getLogger(__name__)

_FALLBACK_TEMPLATE = """\
I could not find reliable enough information to answer this question.

Check these authoritative sources directly:
- **KNF / inwestoredukacja.pl** — IKE, IKZE, investment funds
- **podatki.gov.pl** — tax questions (PIT, Belka tax)
- **nbp.pl** — current interest rates (WIBOR, WIRON, reference rate)
- **obligacjeskarbowe.pl** — current government bond rates

Your question: *{question}*
"""


def fallback(state: AgentState) -> dict:
    question = state["question"]
    log.info("Fallback triggered after %d rewrites", state.get("rewrite_count", 0))
    return {
        "answer":     _FALLBACK_TEMPLATE.format(question=question),
        "citations":  [],
        "confidence": "low",
        "disclaimer": None,
        "give_up":    True,
    }
