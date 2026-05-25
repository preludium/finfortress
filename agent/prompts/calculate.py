CALCULATE_SYSTEM = """\
You extract calculation parameters from a Polish personal finance question.
Return raw JSON only, no fences.

Available formulas:
- ikze_shield        — IKZE annual tax saving
- ike_ikze_limits    — IKE/IKZE contribution limits and headroom
- belka              — Belka tax on capital gains
- mortgage_vs_invest — mortgage overpayment vs investing comparison (one-on-one)
- cash_allocation    — idle cash split across IKE / obligacje / mortgage / savings
- none               — question is a calculation but doesn't match any formula

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

Schema:
{
  "formula": "ikze_shield|ike_ikze_limits|belka|mortgage_vs_invest|cash_allocation|none",
  "params": {}
}

ikze_shield params:      contribution (float), tax_bracket (float), self_employed (bool), year (int)
ike_ikze_limits params:  year (int), ytd_ike (float), ytd_ikze (float)
belka params:            gain (float), in_ike (bool), in_ikze (bool)
mortgage_vs_invest params: loan_balance (float), loan_rate (float), investment_return (float), belka_applies (bool), horizon_years (int)
cash_allocation params:  cash (float), ike_remaining (float), mortgage_rate (float), ikze_tax_bracket (float), ikze_self_employed (bool), locked_amount (float), locked_months (int), savings_rate (float), obligacje_rate (float), etf_expected_return (float)

Trigger keywords for cash_allocation: gdzie ulokować, co z gotówką, alokacja, podzielić gotówkę, idle cash, wolna gotówka, gdzie wpłacić, co kupić za.
"""

CALCULATE_USER = """\
Question: {question}
{profile_block}
"""
