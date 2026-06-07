from __future__ import annotations

import logging
import re
from typing import Callable

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
_ETF_KEYWORDS = re.compile(
    r"\b(portfel|pozycj[aęi]|wart[oó]ść|ile warte|zysk|strat[aę]|ETF|VWCE|IWDA|ISAC|CSPX|EUNL|AGGH|VAGP)\b",
    re.IGNORECASE,
)


def build_fetch_live_node(profile_text: str = "", snapshot: dict | None = None) -> Callable[[AgentState], dict]:

    def fetch_live(state: AgentState) -> dict:
        """Fetch live data when classify flagged needs_live_data=True."""
        if not state.get("needs_live_data"):
            return {"live_data": None}

        question = state["question"]
        parts: list[str] = []
        eur_pln: float | None = None

        if _NBP_KEYWORDS.search(question):
            log.info("fetch_live: fetching NBP rates")
            try:
                from agent.tools.nbp_rates import fetch_nbp_rates, fetch_exchange_rates
                parts.append(fetch_nbp_rates())
                # extract EUR/PLN for ETF conversion — avoid a second HTTP call
                try:
                    import requests
                    resp = requests.get(
                        "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                        timeout=8,
                    )
                    resp.raise_for_status()
                    eur_pln = resp.json()["rates"][0]["mid"]
                except Exception:
                    pass
            except Exception as exc:
                log.warning("NBP fetch failed: %s", exc)

        if _OBLIGACJE_KEYWORDS.search(question):
            log.info("fetch_live: fetching obligacje rates")
            try:
                from agent.tools.obligacje_rates import fetch_obligacje_rates
                parts.append(fetch_obligacje_rates())
            except Exception as exc:
                log.warning("Obligacje fetch failed: %s", exc)

        if _ETF_KEYWORDS.search(question):
            log.info("fetch_live: fetching ETF portfolio prices")
            try:
                from agent.tools.etf_prices import parse_etf_positions, fetch_etf_prices
                # Prefer structured snapshot parser; fall back to regex on raw text
                if snapshot and snapshot.get("etf_positions"):
                    positions = snapshot["etf_positions"]
                    log.info("fetch_live: using %d position(s) from snapshot", len(positions))
                elif profile_text:
                    positions = parse_etf_positions(profile_text)
                else:
                    positions = []
                if positions:
                    parts.append(fetch_etf_prices(positions, eur_pln=eur_pln))
                else:
                    log.info("fetch_live: no ETF positions found in profile")
            except Exception as exc:
                log.warning("ETF price fetch failed: %s", exc)

        live_data = "\n\n".join(p for p in parts if p) or None
        if live_data:
            log.info("fetch_live: got %d chars of live data", len(live_data))
        else:
            log.warning("fetch_live: needs_live_data=True but no keyword matched — confidence will be low")

        return {"live_data": live_data, "needs_live_data": bool(live_data)}

    return fetch_live
