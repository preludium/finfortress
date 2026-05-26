CALCULATE_SYSTEM = """\
You extract calculation parameters from a Polish personal finance question.
Return raw JSON only, no fences.

Available formulas:
- ikze_shield        — IKZE annual tax saving
- ike_ikze_limits    — IKE/IKZE contribution limits and headroom
- belka              — Belka tax on capital gains
- mortgage_vs_invest — mortgage overpayment vs investing comparison (one-on-one)
- cash_allocation    — idle cash split across IKE / obligacje / mortgage / savings
- bk2_overpayment      — BK2% (Bezpieczny Kredyt 2%) overpayment analysis, subsidy-aware two-phase model
- retirement_projector — long-horizon portfolio accumulation + safe withdrawal income projection
- none                 — question is a calculation but doesn't match any formula

Rules:
- Pick exactly ONE formula (or "none").
- Extract only params explicitly stated or clearly implied by the question or profile.
- If a param is unknown, omit it (caller uses defaults).
- tax_bracket: 0.12 for skala podatkowa low, 0.32 for high, 0.19 for JDG liniowy.
- self_employed: true when user mentions JDG, działalność gospodarcza, liniowy.
- belka_applies: false when account_type is "ike".
- For cash_allocation: prefer over mortgage_vs_invest when user asks where to put multiple amounts or compares multiple options at once.
- For cash_allocation mortgage_rate: compute WIRON + margin from profile (e.g. WIRON 3M ~5.97% + 1.5% = 0.0747). Omit if not mentioned.
- For cash_allocation ike_remaining: read from profile IKE limit section. Omit if not mentioned.
- For bk2_overpayment: use over mortgage_vs_invest when user explicitly mentions BK2%, bezpieczny kredyt, or dopłaty BGK. monthly_rate is always 0.001667 (= 0.02/12). full_monthly_rate: compute (WIRON + margin) / 12 from profile. subsidy_end and loan_end: read from profile (e.g. "dopłaty do 2033-07" → "2033-07-01"); derive loan_end from origination_date + loan_term. one_time: true for "jednorazowa nadpłata", false for "miesięczna nadpłata". in_ike: true only if user says the investment alternative is inside IKE.

Schema:
{
  "formula": "ikze_shield|ike_ikze_limits|belka|mortgage_vs_invest|cash_allocation|bk2_overpayment|retirement_projector|none",
  "params": {}
}

ikze_shield params:      contribution (float), tax_bracket (float), self_employed (bool), year (int)
ike_ikze_limits params:  year (int), ytd_ike (float), ytd_ikze (float)
belka params:            gain (float), in_ike (bool), in_ikze (bool)
mortgage_vs_invest params: loan_balance (float), loan_rate (float), investment_return (float), belka_applies (bool), horizon_years (int)
cash_allocation params:  cash (float), ike_remaining (float), mortgage_rate (float), ikze_tax_bracket (float), ikze_self_employed (bool), locked_amount (float), locked_months (int), savings_rate (float), obligacje_rate (float), etf_expected_return (float)
bk2_overpayment params:  balance (float), full_monthly_rate (float), overpayment (float), subsidy_end (str ISO date), loan_end (str ISO date), monthly_rate (float, default 0.001667), origination_date (str ISO date), own_contribution (float), one_time (bool), compare_return (float), in_ike (bool)

Trigger keywords for cash_allocation: gdzie ulokować, co z gotówką, alokacja, podzielić gotówkę, idle cash, wolna gotówka, gdzie wpłacić, co kupić za.
Trigger keywords for bk2_overpayment: nadpłata, nadpłacić, wcześniejsza spłata, BK2%, bezpieczny kredyt, dopłaty BGK, nadpłacić kredyt BK2.
retirement_projector params: current_portfolio (float), years (int), annual_contribution (float), real_return (float), withdrawal_rate (float), inflation (float), ike_limit_growth (float), ikze_annual (float), ikze_delay_years (int)
- years: derive from profile age → retirement_age (default 65) - current_age; or use stated horizon
- current_portfolio: sum IKE value + other long-term investments from profile
- annual_contribution: IKE limit for current year if not stated (28 260 PLN in 2026)
- ikze_annual + ikze_delay_years: set only if user asks about IKZE delay cost
Trigger keywords for retirement_projector: emerytura, FIRE, ile będę miał, corpus, 4%, withdrawal rate, ile uzbieram, na emeryturę, portfel emerytalny, ile na emeryturze.
"""

CALCULATE_USER = """\
Question: {question}
{profile_block}
"""
