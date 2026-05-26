"""
Pure-Python financial calculators for Polish personal finance.
No external calls — all inputs come from the question / user profile.
"""

from __future__ import annotations

import math
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


# ---------------------------------------------------------------------------
# 5. Cash allocation across Polish investment options
# ---------------------------------------------------------------------------

def _pln(n: float) -> str:
    """Format PLN amount with space thousands separator (Polish convention)."""
    return f"{n:,.0f}".replace(",", " ")


def cash_allocation(
    cash: float,
    ike_remaining: float = 0.0,
    ikze_remaining: float | None = None,
    mortgage_rate: float | None = None,
    ikze_tax_bracket: float = 0.19,
    ikze_self_employed: bool = True,
    locked_amount: float = 0.0,
    locked_months: int = 0,
    savings_rate: float = 0.05,
    obligacje_rate: float = 0.062,
    etf_expected_return: float = 0.07,
) -> dict:
    """
    Side-by-side allocation of idle PLN cash across Polish investment options.

    Allocates sequentially: IKE (annual limit, Belka-free) first, then the best
    remaining option by after-tax return. IKZE is always reported separately —
    it has its own annual limit and a different tax mechanic (upfront deduction).

    Assumptions for expected returns are shown in the output — the generator
    should restate them and invite the user to override if their actual rates differ.
    """
    available = max(0.0, cash - locked_amount)

    result: dict = {
        "cash_total": cash,
        "available_to_invest": available,
    }

    if locked_amount > 0:
        result["locked"] = f"{_pln(locked_amount)} PLN — hold liquid ({locked_months} months), do not invest"

    if available <= 0:
        result["note"] = "All cash committed to locked expenses — nothing available to invest now."
        return result

    remaining = available
    step = 1

    # Step 1: IKE — Belka-free, annual limit, always fill first
    if ike_remaining > 0:
        ike_alloc = min(remaining, ike_remaining)
        result[f"step{step}"] = (
            f"{_pln(ike_alloc)} PLN → IKE | {etf_expected_return*100:.1f}% net (Belka-free, annual limit)"
        )
        remaining -= ike_alloc
        step += 1

    # Step 2: Best option for remainder by after-tax return
    if remaining > 0:
        obligacje_net = obligacje_rate * (1 - BELKA_RATE)
        savings_net = savings_rate * (1 - BELKA_RATE)

        if mortgage_rate is not None:
            if mortgage_rate >= obligacje_net:
                result[f"step{step}"] = (
                    f"{_pln(remaining)} PLN → mortgage overpayment | "
                    f"{mortgage_rate*100:.2f}% guaranteed (= loan rate, risk-free)"
                )
            else:
                result[f"step{step}"] = (
                    f"{_pln(remaining)} PLN → COI obligacje | {obligacje_net*100:.2f}% net after Belka "
                    f"(mortgage {mortgage_rate*100:.2f}% is lower)"
                )
        elif obligacje_net >= savings_net:
            result[f"step{step}"] = (
                f"{_pln(remaining)} PLN → COI obligacje | {obligacje_net*100:.2f}% net after Belka"
            )
        else:
            result[f"step{step}"] = (
                f"{_pln(remaining)} PLN → savings account | {savings_net*100:.2f}% net after Belka"
            )

    # IKZE: separate limit, reported alongside but not deducted from available cash
    limits = _limits()
    ikze_cap = (
        ikze_remaining
        if ikze_remaining is not None
        else (limits["ikze_self_employed"] if ikze_self_employed else limits["ikze_default"])
    )
    if ikze_cap > 0:
        ikze_shield = round(ikze_cap * ikze_tax_bracket, 2)
        result["ikze_separate"] = (
            f"{_pln(ikze_cap)} PLN limit | {_pln(ikze_shield)} PLN/yr tax shield "
            f"({int(ikze_tax_bracket*100)}% bracket) — separate from above"
        )

    # After-tax return comparison for all options
    obligacje_net = obligacje_rate * (1 - BELKA_RATE)
    savings_net = savings_rate * (1 - BELKA_RATE)
    parts = [f"IKE {etf_expected_return*100:.1f}% (no Belka)"]
    if mortgage_rate is not None:
        parts.append(f"mortgage {mortgage_rate*100:.2f}% (guaranteed)")
    parts.append(f"COI {obligacje_net*100:.2f}% (after Belka)")
    parts.append(f"savings {savings_net*100:.2f}% (after Belka)")
    result["after_tax_returns"] = " | ".join(parts)

    result["assumptions"] = (
        f"ETF {etf_expected_return*100:.0f}%/yr, COI {obligacje_rate*100:.1f}%/yr, "
        f"savings {savings_rate*100:.0f}%/yr — restate in question to override"
    )

    return result


# ---------------------------------------------------------------------------
# 6. BK2% overpayment — two-phase model
# ---------------------------------------------------------------------------

def bk2_overpayment(
    balance: float,
    full_monthly_rate: float,
    overpayment: float,
    subsidy_end: str,
    loan_end: str,
    monthly_rate: float = 0.02 / 12,
    origination_date: str | None = None,
    own_contribution: float = 0.0,
    one_time: bool = True,
    compare_return: float = 0.07,
    in_ike: bool = False,
) -> dict:
    """
    BK2% (Bezpieczny Kredyt 2%) overpayment analysis.

    Phase 1 (until subsidy_end): raty malejące at 2% effective rate — BGK covers the spread.
    Phase 2 (subsidy_end to loan_end): standard annuity at full market rate.

    Overpaying during Phase 1 saves interest only at the 2% borrower rate (not the full rate).
    The larger saving comes from lower balance at Phase 2 start, where full rate applies.

    Phase 2 convention: shorten term, keep base PMT (standard Polish mortgage overpayment default).

    balance           — current remaining principal (PLN)
    full_monthly_rate — full contractual rate / 12 (e.g. (WIRON + margin) / 12)
    overpayment       — lump-sum or monthly extra payment (PLN)
    subsidy_end       — ISO date of expected 120th scheduled instalment
    loan_end          — ISO date of final scheduled instalment
    monthly_rate      — effective rate during subsidy = 0.02/12 (always 2%/12 for BK2%)
    origination_date  — ISO date loan was originated (for 3-yr lock-in check)
    own_contribution  — wkład własny at origination (for 200k cumulative cap check)
    one_time          — True: lump-sum; False: monthly extra payment
    compare_return    — annual gross investment alternative (default 0.07)
    in_ike            — True: no Belka on investment return
    """
    today = date.today()
    sub_end = date.fromisoformat(subsidy_end)
    loan_end_d = date.fromisoformat(loan_end)

    # ── Time horizons ────────────────────────────────────────────────────────
    phase1_months = max(0, (sub_end.year - today.year) * 12 + (sub_end.month - today.month))
    total_months = max(1, (loan_end_d.year - today.year) * 12 + (loan_end_d.month - today.month))
    phase2_months = max(0, total_months - phase1_months)

    # Fixed capital portion per month (raty malejące — equal capital repayment)
    cap_per_month = balance / total_months

    # ── Lock-in check (§4 ust. 6 pkt 10) ───────────────────────────────────
    in_lockup = False
    if origination_date:
        orig = date.fromisoformat(origination_date)
        months_elapsed = (today.year - orig.year) * 12 + (today.month - orig.month)
        in_lockup = months_elapsed < 36

    # Net monthly instalment (conservative: current balance, not origination balance)
    # §4 ust. 6 pkt 10d uses the *first* instalment at origination — actual cap is slightly higher.
    net_installment = cap_per_month + balance * monthly_rate

    if one_time:
        cumulative_ok = (overpayment + own_contribution) <= 200_000
        monthly_cap_ok = overpayment <= net_installment
        subsidy_safe = (not in_lockup) or cumulative_ok or monthly_cap_ok
    else:
        subsidy_safe = (not in_lockup) or (overpayment <= net_installment)
    subsidy_at_risk = not subsidy_safe

    # ── Phase 1 simulation (raty malejące) ──────────────────────────────────
    def _sim_p1(start_ks: float, extra_monthly: float = 0.0) -> tuple[float, float, int]:
        ks = max(0.0, start_ks)
        interest = 0.0
        months = 0
        for _ in range(phase1_months):
            if ks < 0.01:
                break
            interest += ks * monthly_rate
            ks = max(0.0, ks - cap_per_month - extra_monthly)
            months += 1
        return interest, ks, months

    i1_base, bp2_base, p1m_base = _sim_p1(balance)

    if one_time:
        i1_op, bp2_op, p1m_op = _sim_p1(balance - min(overpayment, balance))
    else:
        i1_op, bp2_op, p1m_op = _sim_p1(balance, extra_monthly=overpayment)

    # ── Phase 2 (shorten term, keep base PMT) ───────────────────────────────
    r = full_monthly_rate

    if bp2_base > 0.01 and phase2_months > 0 and r > 0:
        pmt_base = bp2_base * r / (1 - (1 + r) ** -phase2_months)
        i2_base = pmt_base * phase2_months - bp2_base
    else:
        pmt_base = 0.0
        i2_base = 0.0

    if bp2_op < 0.01:
        i2_op = 0.0
        months_shortened_p2 = phase2_months
    elif pmt_base > 0 and r > 0 and bp2_op * r < pmt_base:
        n_new = -math.log(1 - bp2_op * r / pmt_base) / math.log(1 + r)
        i2_op = pmt_base * n_new - bp2_op
        months_shortened_p2 = round(phase2_months - n_new)
    else:
        i2_op = i2_base
        months_shortened_p2 = 0

    # ── Totals ───────────────────────────────────────────────────────────────
    interest_saved_p1 = max(0.0, round(i1_base - i1_op, 2))
    interest_saved_p2 = max(0.0, round(i2_base - i2_op, 2))
    interest_saved_total = round(interest_saved_p1 + interest_saved_p2, 2)
    months_shortened = max(0, p1m_base - p1m_op) + months_shortened_p2

    # ── Equivalent annual return (sim-based) ─────────────────────────────────
    # For one-time: single PLN works from t=0 over full remaining term.
    # For monthly: each PLN works from its payment date; avg holding period ≈
    #   midpoint between total_months (first payment) and phase2_months (last payment).
    if one_time:
        total_invested = overpayment
        avg_months = total_months
    else:
        total_invested = overpayment * max(p1m_op, 1)
        avg_months = (total_months + phase2_months) / 2

    if total_invested > 0 and avg_months > 0:
        equivalent_annual_return = round(
            interest_saved_total / total_invested / (avg_months / 12), 4
        )
    else:
        equivalent_annual_return = 0.0

    # ── Recommendation ───────────────────────────────────────────────────────
    compare_rate_net = compare_return if in_ike else round(compare_return * (1 - BELKA_RATE), 4)
    recommendation = "overpay" if equivalent_annual_return >= compare_rate_net else "invest"

    # ── Output ───────────────────────────────────────────────────────────────
    overpay_type = "lump-sum" if one_time else "monthly"
    full_rate_pct = round(full_monthly_rate * 12 * 100, 2)

    result: dict = {
        "balance": f"{_pln(balance)} PLN",
        "overpayment": f"{_pln(overpayment)} PLN ({overpay_type})",
        "phase1_months_remaining": phase1_months,
        "phase2_months_remaining": phase2_months,
        "subsidy_at_risk": subsidy_at_risk,
        "interest_saved_phase1": (
            f"{_pln(interest_saved_p1)} PLN "
            f"(2% effective rate — borrower portion only; BGK dopłata shrinks proportionally)"
        ),
        "interest_saved_phase2": (
            f"{_pln(interest_saved_p2)} PLN "
            f"(full rate {full_rate_pct:.2f}% after subsidy ends)"
        ),
        "interest_saved_total": f"{_pln(interest_saved_total)} PLN",
        "months_shortened": months_shortened,
        "equivalent_annual_return": f"{equivalent_annual_return * 100:.2f}%",
        "compare_return_net": (
            f"{compare_rate_net * 100:.2f}% "
            f"({'IKE — no Belka tax' if in_ike else 'after 19% Belka tax'})"
        ),
        "recommendation": recommendation,
    }

    if subsidy_at_risk:
        result["note"] = (
            f"WARNING: loan within 3-year lock-in (§4 ust. 6 pkt 10). "
            f"Overpayment of {_pln(overpayment)} PLN may trigger loss of all BGK subsidies. "
            f"Safe if: after 3 years from origination, OR total overpayment + own contribution "
            f"≤200 000 PLN, OR overpayment ≤ net monthly instalment ({_pln(net_installment)} PLN)."
        )
    else:
        result["note"] = (
            f"Effective overpayment return: {equivalent_annual_return * 100:.2f}%/yr "
            f"vs net investment return: {compare_rate_net * 100:.2f}%/yr → {recommendation}. "
            f"Phase 1 saves at 2% (small); Phase 2 saves at {full_rate_pct:.2f}% (large). "
            f"The closer to subsidy end, the more attractive overpayment becomes."
        )

    return result
