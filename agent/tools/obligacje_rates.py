"""
Live Polish government bond rates scraped from obligacjeskarbowe.pl.

No official API exists — fresh HTML parse at query time.
Called when question mentions: obligacje, COI, EDO, OTS, ROR, DOR, TOS, ROS, ROD.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_BASE_URL = "https://obligacjeskarbowe.pl"
_TIMEOUT  = 15
_SESSION  = requests.Session()
_SESSION.headers.update({
    "User-Agent": "finfortress-bot/1.0 (personal RAG project, non-commercial)"
})

# All current bond series with their product page paths
_BOND_PAGES = {
    "ROR":  "/oferta-obligacji/obligacje-roczne-ror/ror0527/",
    "DOR":  "/oferta-obligacji/obligacje-2-letnie-dor/dor0528/",
    "TOS":  "/oferta-obligacji/obligacje-3-letnie-tos/tos0529/",
    "OTS":  "/oferta-obligacji/obligacje-3-miesieczne-ots/ots0826/",
    "COI":  "/oferta-obligacji/obligacje-4-letnie-coi/coi0530/",
    "ROS":  "/oferta-obligacji/obligacje-6-letnie-ros/ros0532/",
    "EDO":  "/oferta-obligacji/obligacje-10-letnie-edo/edo0536/",
    "ROD":  "/oferta-obligacji/obligacje-12-letnie-rod/rod0538/",
}

_BOND_NAMES = {
    "ROR": "Obligacje roczne ROR",
    "DOR": "Obligacje 2-letnie DOR",
    "TOS": "Obligacje 3-letnie TOS",
    "OTS": "Obligacje 3-miesięczne OTS",
    "COI": "Obligacje 4-letnie COI (antyinflacyjne)",
    "ROS": "Obligacje 6-letnie ROS (rodzinne)",
    "EDO": "Obligacje 10-letnie EDO (antyinflacyjne)",
    "ROD": "Obligacje 12-letnie ROD (rodzinne)",
}


def _parse_rate(html: str) -> str | None:
    """Extract first rate percentage from product page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Rates appear as: <number><sub>%</sub>
    for sub in soup.find_all("sub"):
        if sub.get_text(strip=True) == "%":
            prev = sub.previous_sibling
            if prev and isinstance(prev, str):
                rate_str = prev.strip().replace(",", ".")
                try:
                    float(rate_str)  # validate it's a number
                    return f"{prev.strip()}%"
                except ValueError:
                    continue

    # Fallback: look for "X,XX%" pattern in text
    text = soup.get_text()
    m = re.search(r"(\d+[,\.]\d+)\s*%", text)
    return f"{m.group(1)}%" if m else None


def _fetch_bond(symbol: str, path: str) -> dict | None:
    url = _BASE_URL + path
    try:
        resp = _SESSION.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        rate = _parse_rate(resp.text)
        return {"symbol": symbol, "name": _BOND_NAMES[symbol], "rate": rate, "url": url}
    except Exception as exc:
        log.warning("Bond fetch failed for %s: %s", symbol, exc)
        return None


def fetch_obligacje_rates(symbols: list[str] | None = None) -> str:
    """
    Fetch current bond rates. If symbols provided, fetch only those.
    Returns formatted string for LLM context.
    """
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    targets = {s: p for s, p in _BOND_PAGES.items() if symbols is None or s in symbols}

    lines = [f"Aktualne oprocentowanie obligacji skarbowych (obligacjeskarbowe.pl, pobrano: {fetched_at})"]
    lines.append("Oprocentowanie obowiązuje w bieżącym miesiącu (resetuje się 1. dnia miesiąca).\n")

    for symbol, path in targets.items():
        result = _fetch_bond(symbol, path)
        if result:
            rate_str = result["rate"] or "niedostępne"
            lines.append(f"  {result['name']} ({symbol}): {rate_str} w pierwszym okresie odsetkowym")
            lines.append(f"    Źródło: {result['url']}")
        else:
            lines.append(f"  {symbol}: niedostępny")

    return "\n".join(lines)


if __name__ == "__main__":
    print(fetch_obligacje_rates())
