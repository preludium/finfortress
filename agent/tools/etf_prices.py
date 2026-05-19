"""
Live ETF price fetching via yfinance.
Parses positions from user profile text, fetches current NAV,
converts to PLN using NBP exchange rates.
Never indexed — always fetched at query time.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Matches lines like:
#   VWCE (IE00B3RBWM25): 12 szt., śr. cena zakupu 112,50 EUR
#   IWDA (IE00B4L5Y983): 5 szt., śr. cena 85,00 EUR
_POSITION_RE = re.compile(
    r"\b([A-Z]{2,6})\s+\([A-Z]{2}[A-Z0-9]{10}\)"  # ticker (ISIN — alphanumeric)
    r":\s+(\d+(?:[.,]\d+)?)\s+szt\."               # N szt.
    r".*?(?:śr\. cena zakupu|śr\. cena)\s+"        # avg price label
    r"([\d]+(?:[.,]\d+)?)\s+([A-Z]{3})",           # price + currency
    re.IGNORECASE,
)

# Xetra suffix covers most UCITS ETFs; try .L (London) as fallback
_EXCHANGE_SUFFIXES = [".DE", ".L", ".AS", ""]


def parse_etf_positions(profile_text: str) -> list[dict]:
    """Extract ETF positions from free-text user profile."""
    positions = []
    for match in _POSITION_RE.finditer(profile_text):
        ticker   = match.group(1).upper()
        units    = float(match.group(2).replace(",", ".").replace(" ", ""))
        avg_str  = match.group(3).replace(" ", "").replace(",", ".")
        currency = match.group(4).upper()
        try:
            avg_price = float(avg_str)
        except ValueError:
            log.warning("ETF parser: could not parse avg price %r for %s", avg_str, ticker)
            continue
        positions.append({"ticker": ticker, "units": units, "avg_price": avg_price, "currency": currency})
    log.info("ETF parser: found %d position(s) in profile", len(positions))
    return positions


def _fetch_price_yfinance(ticker: str) -> tuple[float, str] | None:
    """
    Fetch latest close price via yfinance.
    Returns (price, currency) or None on failure.
    Tries exchange suffixes in order until one succeeds.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed — ETF prices unavailable")
        return None

    for suffix in _EXCHANGE_SUFFIXES:
        symbol = f"{ticker}{suffix}"
        try:
            data = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
            if data.empty:
                continue
            close = float(data["Close"].dropna().iloc[-1])
            info  = yf.Ticker(symbol).fast_info
            currency = getattr(info, "currency", "EUR") or "EUR"
            log.info("ETF fetch: %s → %.4f %s", symbol, close, currency)
            return close, currency
        except Exception as exc:
            log.debug("ETF fetch failed for %s: %s", symbol, exc)
    return None


def fetch_etf_prices(positions: list[dict], eur_pln: float | None = None) -> str:
    """
    Fetch live prices for all positions and format as a string for the LLM prompt.

    eur_pln — EUR/PLN rate (pass from already-fetched NBP data if available).
              If None, fetched fresh from NBP.
    """
    if not positions:
        return ""

    if eur_pln is None:
        try:
            import requests
            resp = requests.get(
                "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                timeout=8,
            )
            resp.raise_for_status()
            eur_pln = resp.json()["rates"][0]["mid"]
        except Exception as exc:
            log.warning("ETF tool: NBP EUR/PLN fetch failed: %s — using fallback 4.25", exc)
            eur_pln = 4.25

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"ETF Portfolio (live prices, {fetched_at}, EUR/PLN: {eur_pln:.4f}):"]
    lines.append("")

    total_pln = 0.0

    for pos in positions:
        ticker    = pos["ticker"]
        units     = pos["units"]
        avg_price = pos["avg_price"]
        currency  = pos["currency"]

        result = _fetch_price_yfinance(ticker)
        if result is None:
            lines.append(f"  {ticker}: price unavailable")
            continue

        current_price, fetched_currency = result
        # normalise: use fetched currency if available
        fx = eur_pln if fetched_currency.upper() in ("EUR", "GBP") else 1.0

        value_native = units * current_price
        value_pln    = value_native * fx
        cost_native  = units * avg_price
        pnl_native   = value_native - cost_native
        pnl_pct      = (pnl_native / cost_native * 100) if cost_native else 0.0
        pnl_sign     = "+" if pnl_native >= 0 else ""

        lines.append(
            f"  {ticker}  {units:.0f} szt. × {current_price:.2f} {fetched_currency}"
            f" = {value_native:,.2f} {fetched_currency} = {value_pln:,.2f} PLN"
        )
        lines.append(
            f"           Avg cost: {avg_price:.2f} {currency}"
            f" | P&L: {pnl_sign}{pnl_native:.2f} {fetched_currency}"
            f" ({pnl_sign}{pnl_pct:.1f}%)"
        )
        lines.append("")
        total_pln += value_pln

    lines.append(f"  Total portfolio value: {total_pln:,.2f} PLN")
    return "\n".join(lines)
