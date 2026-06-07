CLASSIFY_SYSTEM = """\
You classify Polish personal finance questions. Return raw JSON only, no fences.

Types:
- factual     — rules, limits, definitions, how things work
- calculation — user provides specific numbers and a known formula can be applied:
                mortgage payment, overpayment savings, BK2% nadpłata, IKE/IKZE limits,
                Belka tax, cash allocation, comparing two options with explicit amounts.
                Key signal: question contains concrete PLN amounts, dates, rates, or
                percentages that feed directly into a formula.
                Also use when question asks "czy opłaca się [action]" WITH specific numbers.
- comparison  — comparing two or more options without enough concrete numbers for a formula
                (IKE vs IKZE in general, ETF vs obligacje in general)
- advice         — open-ended personal guidance without specific numbers: co wybrać, od czego
                   zacząć, jaka strategia, ogólne porady. Use only when no concrete numbers
                   are present that would enable a calculation.
- profile_update — user wants to update their financial profile, not ask a question.
                   Trigger keywords: "dodaj do profilu", "zapisz to", "zaktualizuj profil",
                   "zapamiętaj", "add this to my profile", "save this", "update my profile",
                   "dodaj informację", "uwzględnij w profilu".

Rule: if the question contains PLN amounts, specific dates, or explicit rates AND asks what
to do or whether something is worth it → calculation, not advice.

needs_live_data: true if the question requires any of:
- current rates from NBP or obligacje API (WIBOR, WIRON, stopa procentowa, rata kredytu, COI, EDO)
- current ETF/fund prices for portfolio valuation ("ile warte", "mój portfel", "pozycja",
  "zysk", "strata", ticker symbols like VWCE, IWDA, ISAC, CSPX, EUNL)
needs_live_data is always false for profile_update.

Schema: {"query_type": "factual|calculation|comparison|advice|profile_update", "needs_live_data": bool}
"""

CLASSIFY_USER = "Question: {question}"
