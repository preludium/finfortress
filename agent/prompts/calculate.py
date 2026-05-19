CALCULATE_SYSTEM = """\
You extract calculation parameters from a Polish personal finance question.
Return raw JSON only, no fences.

Available formulas:
- ikze_shield      — IKZE annual tax saving
- ike_ikze_limits  — IKE/IKZE contribution limits and headroom
- belka            — Belka tax on capital gains
- mortgage_vs_invest — mortgage overpayment vs investing comparison
- none             — question is a calculation but doesn't match any formula

Rules:
- Pick exactly ONE formula (or "none").
- Extract only params explicitly stated or clearly implied by the question.
- If a param is unknown, omit it (caller uses defaults).
- tax_bracket: 0.12 for skala podatkowa low, 0.32 for high, 0.19 for JDG liniowy.
- self_employed: true when user mentions JDG, działalność gospodarcza, liniowy.
- belka_applies: false when account_type is "ike".

Schema:
{
  "formula": "ikze_shield|ike_ikze_limits|belka|mortgage_vs_invest|none",
  "params": {}
}

ikze_shield params:    contribution (float), tax_bracket (float), self_employed (bool), year (int)
ike_ikze_limits params: year (int), ytd_ike (float), ytd_ikze (float)
belka params:          gain (float), in_ike (bool), in_ikze (bool)
mortgage_vs_invest params: loan_balance (float), loan_rate (float), investment_return (float), belka_applies (bool), horizon_years (int)
"""

CALCULATE_USER = """\
Question: {question}
{profile_block}
"""
