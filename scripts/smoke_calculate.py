"""Smoke test for financial calculators.

Unit tests run first (no LLM — fast). LLM dispatch test runs last.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from agent.tools.calculator import (
    cash_allocation,
    mortgage_vs_investment,
    ikze_tax_shield,
    belka_tax,
    bk2_overpayment,
    retirement_projector,
)

FAIL = 0


def check(name: str, condition: bool) -> None:
    global FAIL
    status = "OK  " if condition else "FAIL"
    if not condition:
        FAIL += 1
    print(f"  [{status}] {name}")


# ---------------------------------------------------------------------------
# cash_allocation
# ---------------------------------------------------------------------------

print("\n=== cash_allocation ===")

# Happy path: IKE headroom, cash > IKE limit → remainder goes to mortgage
r = cash_allocation(
    cash=50_000,
    locked_amount=12_000,
    locked_months=4,
    ike_remaining=28_260,
    mortgage_rate=0.0797,
)
check("locked key present",                  "locked" in r)
check("available = 38 000",                  r["available_to_invest"] == 38_000.0)
check("step1 → IKE",                         "IKE" in r.get("step1", ""))
check("step2 → mortgage (rate > COI net)",   "mortgage" in r.get("step2", ""))
check("ikze_separate present",               "ikze_separate" in r)
check("after_tax_returns present",           "after_tax_returns" in r)
check("assumptions present",                 "assumptions" in r)

# All cash locked — nothing to invest
r2 = cash_allocation(cash=10_000, locked_amount=10_000, locked_months=2)
check("zero available: no step1",            "step1" not in r2)
check("zero available: note present",        "note" in r2)

# Cash < IKE remaining → IKE gets everything, no step2
r3 = cash_allocation(cash=5_000, ike_remaining=28_260)
check("IKE capped at available (5 000 PLN)", "5 000" in r3.get("step1", ""))  # space-formatted
check("no step2 when remaining = 0",         "step2" not in r3)

# No IKE remaining, low savings rate → COI wins
r4 = cash_allocation(cash=50_000, ike_remaining=0, savings_rate=0.03, obligacje_rate=0.062)
check("no IKE in step1 when ike_remaining=0", "IKE" not in r4.get("step1", ""))
check("COI wins over 3% savings",             "obligacje" in r4.get("step1", "").lower())

# Mortgage rate below COI net → COI recommended with note
r5 = cash_allocation(cash=20_000, ike_remaining=0, mortgage_rate=0.04, obligacje_rate=0.062)
obligacje_net_rate = round(0.062 * 0.81, 4)
check("COI wins when mortgage rate < COI net", "lower" in r5.get("step1", "").lower())

# No mortgage provided → obligacje vs savings branch
r6 = cash_allocation(cash=30_000, ike_remaining=10_000, savings_rate=0.05, obligacje_rate=0.062)
check("step1 IKE (10 000)",                 "10 000" in r6.get("step1", ""))  # space-formatted
check("step2 COI (5% > savings 4.05%)",     "obligacje" in r6.get("step2", "").lower())

# IKZE cap falls back to year limit when ikze_remaining not given
r7 = cash_allocation(cash=20_000, ikze_self_employed=True, ikze_tax_bracket=0.19)
check("ikze_separate uses year limit",       "16 956" in r7.get("ikze_separate", ""))  # space-formatted
check("ikze shield ≈ 3 222 PLN",            "3 222" in r7.get("ikze_separate", ""))   # space-formatted

# ---------------------------------------------------------------------------
# mortgage_vs_investment
# ---------------------------------------------------------------------------

print("\n=== mortgage_vs_investment ===")

r8 = mortgage_vs_investment(
    loan_balance=400_000, loan_rate=0.075,
    investment_return=0.08, belka_applies=True,
)
expected_spread = round(0.08 * 0.81 - 0.075, 4)
check("spread correct",                      abs(r8["spread"] - expected_spread) < 0.001)
check("recommendation: overpay",             r8["recommendation"] == "overpay mortgage")

r9 = mortgage_vs_investment(
    loan_balance=400_000, loan_rate=0.05,
    investment_return=0.08, belka_applies=False,  # IKE — no Belka
)
check("IKE 8% > 5% loan → invest",          r9["recommendation"] == "invest")

# ---------------------------------------------------------------------------
# ikze_tax_shield
# ---------------------------------------------------------------------------

print("\n=== ikze_tax_shield ===")

r10 = ikze_tax_shield(contribution=16_956, tax_bracket=0.19, self_employed=True)
check("shield ≈ 3 221.64 PLN",               abs(r10["tax_saving_pln"] - 3_221.64) < 1.0)
check("contribution capped at JDG limit",    r10["contribution_effective"] == 16_956.0)

r11 = ikze_tax_shield(contribution=999_999, tax_bracket=0.19, self_employed=True)
check("over-contribution capped at limit",   r11["contribution_effective"] == 16_956.0)

# ---------------------------------------------------------------------------
# belka_tax
# ---------------------------------------------------------------------------

print("\n=== belka_tax ===")

r12 = belka_tax(gain=10_000)
check("standard: tax = 1 900 PLN",          r12["tax"] == 1_900.0)

r13 = belka_tax(gain=10_000, in_ike=True)
check("IKE: tax = 0",                        r13["tax"] == 0.0)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# bk2_overpayment
# ---------------------------------------------------------------------------

print("\n=== bk2_overpayment ===")

# Baseline: 500k PLN, 7.47% full rate, 10yr Phase 1 remaining, 15yr Phase 2
# Loan originated 2023-07-01, subsidy_end 2033-07-01, loan_end 2048-07-01
# Today is 2026-05-26 → ~34 months elapsed → just past 3-yr lock-in
BK_BALANCE       = 480_000.0
BK_FULL_RATE     = 0.0747 / 12
BK_SUBSIDY_END   = "2033-07-01"
BK_LOAN_END      = "2048-07-01"
BK_ORIGINATION   = "2023-07-01"

# One-time 50k overpayment — should NOT be at risk (>3 years)
r_one = bk2_overpayment(
    balance=BK_BALANCE,
    full_monthly_rate=BK_FULL_RATE,
    overpayment=50_000,
    subsidy_end=BK_SUBSIDY_END,
    loan_end=BK_LOAN_END,
    origination_date=BK_ORIGINATION,
)
check("one-time: subsidy_at_risk=False after lock-in",  r_one["subsidy_at_risk"] is False)
check("one-time: interest_saved_total > 0",             "0 PLN" not in r_one["interest_saved_total"])
check("one-time: phase2 saving > phase1 saving",        # Phase 2 dominates (more months at full rate)
      int(r_one["interest_saved_phase2"].split()[0].replace(" ", "").replace("\xa0", "")) >
      int(r_one["interest_saved_phase1"].split()[0].replace(" ", "").replace("\xa0", "")))
check("one-time: months_shortened > 0",                 r_one["months_shortened"] > 0)
check("one-time: recommendation is overpay (Phase 2 dominates)", r_one["recommendation"] == "overpay")
check("one-time: equivalent_return > 5%",               # Phase 2 (15yr @ 7.47%) dominates
      float(r_one["equivalent_annual_return"].rstrip("%")) > 5.0)

# Scenario where investing wins: long Phase 1 (9yr), very short Phase 2 (3yr)
r_invest = bk2_overpayment(
    balance=480_000,
    full_monthly_rate=0.075 / 12,
    overpayment=50_000,
    subsidy_end="2035-07-01",   # ~9 yr Phase 1
    loan_end="2038-07-01",      # ~3 yr Phase 2 — savings at full rate are small
    origination_date=BK_ORIGINATION,
)
check("invest scenario: recommendation is invest",             r_invest["recommendation"] == "invest")
check("invest scenario: equivalent_return < 5%",               # short Phase 2 → blended return low
      float(r_invest["equivalent_annual_return"].rstrip("%")) < 5.0)

# Monthly 2k/mth overpayment
r_mo = bk2_overpayment(
    balance=BK_BALANCE,
    full_monthly_rate=BK_FULL_RATE,
    overpayment=2_000,
    subsidy_end=BK_SUBSIDY_END,
    loan_end=BK_LOAN_END,
    origination_date=BK_ORIGINATION,
    one_time=False,
)
check("monthly: subsidy_at_risk=False",                 r_mo["subsidy_at_risk"] is False)
check("monthly: interest_saved_total > 0",              "0 PLN" not in r_mo["interest_saved_total"])
check("monthly: months_shortened > 0",                  r_mo["months_shortened"] > 0)

# Lock-in scenario: originated 2024-06-01 → <36 months → risky large overpayment
r_lock = bk2_overpayment(
    balance=500_000,
    full_monthly_rate=BK_FULL_RATE,
    overpayment=100_000,
    subsidy_end="2034-06-01",
    loan_end="2049-06-01",
    origination_date="2024-06-01",
    own_contribution=50_000,   # 100k + 50k = 150k ≤ 200k → should be safe via cumulative cap
)
check("lock-in: cumulative cap 150k ≤ 200k → not at risk", r_lock["subsidy_at_risk"] is False)

r_lock2 = bk2_overpayment(
    balance=500_000,
    full_monthly_rate=BK_FULL_RATE,
    overpayment=160_000,
    subsidy_end="2034-06-01",
    loan_end="2049-06-01",
    origination_date="2024-06-01",
    own_contribution=50_000,   # 160k + 50k = 210k > 200k → at risk
)
check("lock-in: 210k > 200k cumulative → at risk",      r_lock2["subsidy_at_risk"] is True)
check("lock-in: note contains WARNING",                  "WARNING" in r_lock2.get("note", ""))

# Edge: Phase 1 already over (subsidy_end in the past) → pure Phase 2
r_p2only = bk2_overpayment(
    balance=300_000,
    full_monthly_rate=BK_FULL_RATE,
    overpayment=30_000,
    subsidy_end="2024-01-01",   # already passed
    loan_end="2048-07-01",
)
check("phase1=0: no Phase 1 interest saved",            r_p2only["interest_saved_phase1"].startswith("0 PLN"))
check("phase1=0: Phase 2 saving > 0",                   "0 PLN" not in r_p2only["interest_saved_phase2"])
check("phase1=0: equivalent_return near full rate",
      float(r_p2only["equivalent_annual_return"].rstrip("%")) > 5.0)

# ---------------------------------------------------------------------------
# retirement_projector
# ---------------------------------------------------------------------------

print("\n=== retirement_projector ===")

# Base: 28yr old, 37yr horizon (retire at 65), 50k IKE, 5% real return
r_ret = retirement_projector(
    current_portfolio=50_000,
    years=37,
    annual_contribution=28_260,
    real_return=0.05,
    withdrawal_rate=0.04,
)
check("base: portfolio_real key present",       "portfolio_real" in r_ret)
check("base: monthly_income_real key present",  "monthly_income_real" in r_ret)
check("base: sensitivity_3pct present",         "sensitivity_3pct" in r_ret)
check("base: sensitivity_7pct present",         "sensitivity_7pct" in r_ret)
check("base: ike_limit_growth_scenario present","ike_limit_growth_scenario" in r_ret)
check("base: assumptions present",             "assumptions" in r_ret)

# Manual check: FV = 50000*(1.05)^37 + 28260*((1.05)^37 - 1)/0.05
import math as _math
_fv_expected = 50_000 * 1.05**37 + 28_260 * (1.05**37 - 1) / 0.05
_income_expected = _fv_expected * 0.04
# Extract numeric value from portfolio_real string (format: "X XXX PLN ...")
_portfolio_str = r_ret["portfolio_real"].split(" PLN")[0].replace(" ", "").replace("\xa0", "").replace(",", "")
_portfolio_actual = float(_portfolio_str)
check("base: portfolio_real within 1% of formula",
      abs(_portfolio_actual - _fv_expected) / _fv_expected < 0.01)

# Sensitivity ordering: 3% < base(5%) < 7%
def _extract_pln(s):
    return float(s.split(" PLN")[0].replace(" ", "").replace("\xa0", "").replace(",", ""))

check("sensitivity: 3% < 5% < 7%",
      _extract_pln(r_ret["sensitivity_3pct"]) <
      _extract_pln(r_ret["sensitivity_base"]) <
      _extract_pln(r_ret["sensitivity_7pct"]))

# IKZE delay cost: 5yr delay on 16 956 PLN/yr, 37yr horizon
r_ikze = retirement_projector(
    current_portfolio=50_000,
    years=37,
    ikze_annual=16_956,
    ikze_delay_years=5,
)
check("ikze_delay: key present",               "ikze_delay_cost" in r_ikze)
check("ikze_delay: cost > 0",                  _extract_pln(r_ikze["ikze_delay_cost"].split("costs ")[1]) > 0)

# Edge: years=0 → error note
r_zero = retirement_projector(current_portfolio=100_000, years=0)
check("edge: years=0 returns note",            "note" in r_zero)

# Nominal > real (inflation adds to nominal value)
_real_val    = _extract_pln(r_ret["portfolio_real"])
_nominal_str = r_ret["portfolio_nominal"].split(" PLN")[0].replace(" ", "").replace("\xa0", "").replace(",", "")
_nominal_val = float(_nominal_str)
check("nominal > real (inflation effect)",     _nominal_val > _real_val)

print(f"\nUnit tests: {'ALL PASSED' if FAIL == 0 else f'{FAIL} FAILED'}")

if FAIL > 0:
    sys.exit(1)

# ---------------------------------------------------------------------------
# LLM dispatch test (hits grader model — needs .env)
# ---------------------------------------------------------------------------

print("\n=== LLM dispatch: cash_allocation ===")
logging.getLogger().setLevel(logging.INFO)

from agent.nodes.calculate import build_calculate_node
from agent.state import INITIAL_STATE

profile_block = """\
## Sytuacja dochodowa
- Forma zatrudnienia: JDG, podatek liniowy 19%

## Portfolio snapshot
### IKE — XTB (otwarte czerwiec 2021)
- VWCE (IE00B3RBWM25): 12 units, avg 112.50 EUR
- 2026 limit: 28 260 PLN, not yet filled

### Kredyt hipoteczny
WIRON 3M + 1,5% marży, raty malejące, 30 lat.
- Mortgage WIRON: 400 000 PLN (2024-01)
"""

calculate = build_calculate_node(profile_block=profile_block)

state = {
    **INITIAL_STATE,
    "question": "Mam 40 000 zł wolnej gotówki, za 4 miesiące płacę 12 000 zł za remont. Gdzie ulokować resztę — IKE, nadpłata kredytu?",
    "query_type": "calculation",
}

result = calculate(state)
calc_result = result.get("calc_result")

print(f"\ncalc_result:\n{calc_result or '(None)'}\n")

if calc_result and "cash_allocation" in calc_result:
    print("[OK] LLM dispatch → formula=cash_allocation, result present")
elif calc_result:
    print("[WARN] calc_result returned but formula may differ — check output above")
else:
    print("[FAIL] calc_result is None — formula not dispatched or LLM error")
