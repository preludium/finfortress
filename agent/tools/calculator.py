"""
Pure-Python financial calculators for Polish personal finance.
No external calls — all inputs come from the question / user profile.
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# Annual contribution limits — update each January when MF announces new values
# ---------------------------------------------------------------------------

_IKE_IKZE_LIMITS: dict[int, dict] = {
    2023: {"ike": 20_805.0,  "ikze_default":  8_322.0,   "ikze_self_employed": 12_483.0},
    2024: {"ike": 23_472.0,  "ikze_default":  9_388.80,  "ikze_self_employed": 14_083.20},
    2025: {"ike": 26_019.0,  "ikze_default": 10_407.60,  "ikze_self_employed": 15_611.40},
    2026: {"ike": 28_260.0,  "ikze_default": 11_304.0,   "ikze_self_employed": 16_956.0},
}

BELKA_RATE = 0.19


def _limits(year: int | None = None) -> dict:
    y = year or date.today().year
    return _IKE_IKZE_LIMITS.get(y, _IKE_IKZE_LIMITS[max(_IKE_IKZE_LIMITS)])


# ---------------------------------------------------------------------------
# 1. IKZE tax shield
# ---------------------------------------------------------------------------

def ikze_tax_shield(
    contribution: float,
    tax_bracket: float,
    self_employed: bool = False,
    year: int | None = None,
) -> dict:
    """
    Annual tax saving from IKZE deduction.

    contribution  — planned PLN amount (capped at annual limit)
    tax_bracket   — marginal PIT rate: 0.12, 0.19 (JDG liniowy), 0.32
    self_employed — True for JDG (higher IKZE limit applies)
    """
    limits = _limits(year)
    cap = limits["ikze_self_employed"] if self_employed else limits["ikze_default"]
    effective = min(contribution, cap)
    saving = round(effective * tax_bracket, 2)
    return {
        "contribution_effective": effective,
        "annual_limit": cap,
        "tax_bracket": tax_bracket,
        "tax_saving_pln": saving,
        "note": f"JDG liniowy {int(tax_bracket*100)}%" if self_employed else f"Skala {int(tax_bracket*100)}%",
    }


# ---------------------------------------------------------------------------
# 2. IKE / IKZE contribution limits
# ---------------------------------------------------------------------------

def ike_ikze_limits(year: int | None = None, ytd_ike: float = 0.0, ytd_ikze: float = 0.0) -> dict:
    """
    Return annual IKE and IKZE limits and remaining headroom.

    ytd_ike  — contributions made to IKE so far this year
    ytd_ikze — contributions made to IKZE so far this year
    """
    limits = _limits(year)
    y = year or date.today().year
    return {
        "year": y,
        "ike_limit": limits["ike"],
        "ike_remaining": max(0.0, limits["ike"] - ytd_ike),
        "ikze_limit_default": limits["ikze_default"],
        "ikze_limit_self_employed": limits["ikze_self_employed"],
        "ikze_remaining_default": max(0.0, limits["ikze_default"] - ytd_ikze),
        "ikze_remaining_self_employed": max(0.0, limits["ikze_self_employed"] - ytd_ikze),
    }


# ---------------------------------------------------------------------------
# 3. Belka tax on capital gains
# ---------------------------------------------------------------------------

def belka_tax(
    gain: float,
    in_ike: bool = False,
    in_ikze: bool = False,
) -> dict:
    """
    19% Belka tax on capital gains.
    IKE: fully exempt. IKZE: gain exempt, principal taxed as income at withdrawal.
    """
    if in_ike:
        return {
            "gain": gain,
            "tax": 0.0,
            "net_gain": gain,
            "note": "IKE — capital gains fully exempt from Belka tax",
        }
    if in_ikze:
        return {
            "gain": gain,
            "tax": 0.0,
            "net_gain": gain,
            "note": "IKZE — capital gains exempt; full withdrawal taxed as income (PIT at marginal rate)",
        }
    tax = round(gain * BELKA_RATE, 2)
    return {
        "gain": gain,
        "tax": tax,
        "net_gain": round(gain - tax, 2),
        "note": f"Standard taxable account — Belka {int(BELKA_RATE*100)}% applies",
    }


# ---------------------------------------------------------------------------
# 4. Mortgage overpayment vs investment
# ---------------------------------------------------------------------------

def mortgage_vs_investment(
    loan_balance: float,
    loan_rate: float,
    investment_return: float,
    belka_applies: bool = True,
    horizon_years: int = 1,
) -> dict:
    """
    Compare effective returns: mortgage overpayment vs investing 1 PLN.

    loan_rate         — annual nominal rate, e.g. 0.075
    investment_return — expected annual gross return, e.g. 0.08
    belka_applies     — False when investing inside IKE (no Belka)
    horizon_years     — for compound comparison (default 1 for simple rate comparison)
    """
    guaranteed_return = loan_rate
    effective_invest = investment_return * (1 - BELKA_RATE) if belka_applies else investment_return
    spread = round(effective_invest - guaranteed_return, 4)
    recommendation = "invest" if spread > 0 else "overpay mortgage"

    return {
        "loan_balance": loan_balance,
        "loan_rate": loan_rate,
        "investment_gross_return": investment_return,
        "effective_investment_return": round(effective_invest, 4),
        "overpayment_guaranteed_return": guaranteed_return,
        "spread": spread,
        "recommendation": recommendation,
        "belka_applied": belka_applies,
        "note": (
            f"Investing nets {effective_invest*100:.2f}% after Belka vs {loan_rate*100:.2f}% guaranteed by overpayment. "
            f"Spread: {spread*100:+.2f}%."
        ),
    }
