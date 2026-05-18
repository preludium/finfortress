"""
Live NBP exchange rates via api.nbp.pl.

Returns formatted string ready for injection into generate prompt as live_data.
Called when query_type == "calculation" or temporal_mismatch detected on rate queries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_BASE = "https://api.nbp.pl/api/exchangerates/rates/A"
_TIMEOUT = 10
_CURRENCIES = ["EUR", "USD", "CHF", "GBP"]
_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


def _fetch_rate(code: str) -> dict | None:
    try:
        resp = _SESSION.get(f"{_BASE}/{code}/?format=json", timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"][0]
        return {
            "code":          data["code"],
            "currency":      data["currency"],
            "mid":           rate["mid"],
            "effectiveDate": rate["effectiveDate"],
            "tableNo":       rate["no"],
        }
    except Exception as exc:
        log.warning("NBP rate fetch failed for %s: %s", code, exc)
        return None


def fetch_exchange_rates() -> str:
    """Fetch current NBP exchange rates. Returns formatted string for LLM context."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"Kursy walut NBP (tabela A, pobrano: {fetched_at})"]

    for code in _CURRENCIES:
        rate = _fetch_rate(code)
        if rate:
            lines.append(
                f"  {rate['code']} ({rate['currency']}): {rate['mid']:.4f} PLN "
                f"[data: {rate['effectiveDate']}, tabela: {rate['tableNo']}]"
            )
        else:
            lines.append(f"  {code}: niedostępny")

    return "\n".join(lines)


def fetch_nbp_rates() -> str:
    """Main entry point — returns all available live NBP data as formatted string."""
    sections = [fetch_exchange_rates()]

    sections.append(
        "\nUwaga: Stawki WIBOR i WIRON są publikowane przez GPW Benchmark "
        "(gpwbenchmark.pl), nie przez NBP API. "
        "Stopa referencyjna NBP jest ogłaszana przez Radę Polityki Pieniężnej."
    )

    return "\n\n".join(sections)


if __name__ == "__main__":
    print(fetch_nbp_rates())
