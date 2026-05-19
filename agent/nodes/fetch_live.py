from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.state import AgentState

log = logging.getLogger(__name__)

_OBLIGACJE_KEYWORDS = re.compile(
    r"\b(obligacje?|COI|EDO|OTS|ROR|DOR|TOS|ROS|ROD|skarbowe|oprocentowanie obligacji)\b",
    re.IGNORECASE,
)
_NBP_KEYWORDS = re.compile(
    r"\b(kurs|walut[ay]|EUR|USD|CHF|GBP|wymiana|WIBOR|WIRON|stopa referencyjna|NBP)\b",
    re.IGNORECASE,
)


def fetch_live(state: AgentState) -> dict:
    """Fetch live rate data when classify flagged needs_live_data=True."""
    if not state.get("needs_live_data"):
        return {"live_data": None}

    question = state["question"]
    parts: list[str] = []

    if _NBP_KEYWORDS.search(question):
        log.info("fetch_live: fetching NBP rates")
        try:
            from agent.tools.nbp_rates import fetch_nbp_rates
            parts.append(fetch_nbp_rates())
        except Exception as exc:
            log.warning("NBP fetch failed: %s", exc)

    if _OBLIGACJE_KEYWORDS.search(question):
        log.info("fetch_live: fetching obligacje rates")
        try:
            from agent.tools.obligacje_rates import fetch_obligacje_rates
            parts.append(fetch_obligacje_rates())
        except Exception as exc:
            log.warning("Obligacje fetch failed: %s", exc)

    live_data = "\n\n".join(parts) if parts else None
    if live_data:
        log.info("fetch_live: got %d chars of live data", len(live_data))
    else:
        log.warning("fetch_live: needs_live_data=True but no keyword matched — confidence will be low")

    return {"live_data": live_data, "needs_live_data": bool(live_data)}
