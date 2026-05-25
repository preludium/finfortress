"""Smoke test for financial calculators.

Unit tests run first (no LLM — fast). LLM dispatch test runs last.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from agent.tools.calculator import (
    cash_allocation,
    mortgage_vs_investment,
    ikze_tax_shield,
    belka_tax,
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
