from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
PROFILE_PATH = ROOT / "data" / "user_profile.md"


def load_profile() -> Optional[str]:
    if not PROFILE_PATH.exists():
        return None
    try:
        text = PROFILE_PATH.read_text(encoding="utf-8").strip()
        return text if text else None
    except Exception as exc:
        log.warning("user_profile.md load failed: %s — answering without profile", exc)
        return None


def format_profile_block(profile_text: Optional[str]) -> str:
    if not profile_text:
        return ""
    return f"PROFIL UŻYTKOWNIKA (uwzględnij w odpowiedzi — dostosuj ją do tej konkretnej sytuacji):\n{profile_text}"


# ---------------------------------------------------------------------------
# Portfolio snapshot parser
# ---------------------------------------------------------------------------
# Reads the structured "## Portfolio snapshot" section from the profile.
# The rest of the profile is free-form text — only this section is parsed.
# Returns None if the section is absent (agent falls back to regex parsing).

_ETF_LINE = re.compile(
    r"-\s+([A-Z]{2,6})\s+\(([A-Z]{2}[A-Z0-9]{10})\):\s+"  # - TICKER (ISIN):
    r"([\d.,]+)\s+units?,\s+avg\s+([\d.,]+)\s+([A-Z]{3})",  # N units, avg X EUR
    re.IGNORECASE,
)
_IKE_LIMIT = re.compile(
    r"(\d{4})\s+limit:\s+([\d\s]+)\s+PLN,\s+(filled|not yet filled)",
    re.IGNORECASE,
)
_BOND_LINE = re.compile(
    r"-\s+([A-Z]{3}\d{4}):\s+(\d+)\s+×\s+100\s+PLN"
    r"(?:,\s+matures\s+(\d{4}-\d{2}))?"
    r"(?:,\s+rate\s+([\d.]+)%\s+(fixed|indexed))?",
    re.IGNORECASE,
)
_CASH_LINE = re.compile(
    r"-\s+~?([\d\s]+)\s+PLN"
    r"(?:\s+\(emergency:\s+([\d\s]+)\s+PLN,\s+available:\s+([\d\s]+)\s+PLN\))?",
    re.IGNORECASE,
)
_MORTGAGE_LINE = re.compile(
    r"-\s+Mortgage\s+\S+:\s+([\d\s]+)\s+PLN",
    re.IGNORECASE,
)


def _pln(s: str) -> float:
    return float(s.replace(" ", "").replace(" ", ""))


def parse_snapshot(profile_text: str) -> dict | None:
    """
    Parse the '## Portfolio snapshot' section from the profile.

    Returns a dict with structured portfolio data, or None if the section
    is not present. All fields are optional — missing lines are omitted.

    Returned keys (all optional):
      etf_positions:          list[dict]  ticker, isin, units, avg_price, currency
      ike_limits:             dict        year → {limit_pln, filled}
      bonds:                  list[dict]  series, count, maturity, rate, rate_type
      cash_pln:               float       total cash
      cash_emergency_pln:     float
      cash_available_pln:     float
      mortgage_balance_pln:   float
    """
    marker = re.search(r"^##\s+Portfolio snapshot", profile_text, re.IGNORECASE | re.MULTILINE)
    if not marker:
        return None

    snapshot_text = profile_text[marker.start():]
    # Stop at the next top-level heading (##) if any
    next_section = re.search(r"\n##\s+", snapshot_text[3:])
    if next_section:
        snapshot_text = snapshot_text[: next_section.start() + 1]

    result: dict = {}

    # ETF positions (IKE + other sections)
    etf_positions = []
    for m in _ETF_LINE.finditer(snapshot_text):
        try:
            etf_positions.append({
                "ticker":    m.group(1).upper(),
                "isin":      m.group(2).upper(),
                "units":     float(m.group(3).replace(",", ".")),
                "avg_price": float(m.group(4).replace(",", ".")),
                "currency":  m.group(5).upper(),
            })
        except ValueError:
            pass
    if etf_positions:
        result["etf_positions"] = etf_positions

    # IKE annual limits
    ike_limits = {}
    for m in _IKE_LIMIT.finditer(snapshot_text):
        try:
            ike_limits[int(m.group(1))] = {
                "limit_pln": _pln(m.group(2)),
                "filled":    m.group(3).lower() == "filled",
            }
        except ValueError:
            pass
    if ike_limits:
        result["ike_limits"] = ike_limits

    # Bonds
    bonds = []
    for m in _BOND_LINE.finditer(snapshot_text):
        bond: dict = {
            "series": m.group(1).upper(),
            "count":  int(m.group(2)),
            "total_pln": int(m.group(2)) * 100,
        }
        if m.group(3):
            bond["maturity"] = m.group(3)
        if m.group(4):
            bond["rate"] = float(m.group(4))
        if m.group(5):
            bond["rate_type"] = m.group(5).lower()
        bonds.append(bond)
    if bonds:
        result["bonds"] = bonds

    # Cash
    cash_m = _CASH_LINE.search(snapshot_text)
    if cash_m:
        try:
            result["cash_pln"] = _pln(cash_m.group(1))
            if cash_m.group(2):
                result["cash_emergency_pln"] = _pln(cash_m.group(2))
            if cash_m.group(3):
                result["cash_available_pln"] = _pln(cash_m.group(3))
        except (ValueError, AttributeError):
            pass

    # Mortgage
    mortgage_m = _MORTGAGE_LINE.search(snapshot_text)
    if mortgage_m:
        try:
            result["mortgage_balance_pln"] = _pln(mortgage_m.group(1))
        except ValueError:
            pass

    if not result:
        return None

    log.info(
        "parse_snapshot: ETF positions=%d, bonds=%d, cash=%s, mortgage=%s",
        len(result.get("etf_positions", [])),
        len(result.get("bonds", [])),
        result.get("cash_pln"),
        result.get("mortgage_balance_pln"),
    )
    return result
