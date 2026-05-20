CLASSIFY_SYSTEM = """\
You classify Polish personal finance questions. Return raw JSON only, no fences.

Types:
- factual     — rules, limits, definitions, how things work
- calculation — needs current rates (WIBOR/WIRON) to compute (e.g. mortgage payment)
- comparison  — comparing two or more options (IKE vs IKZE, ETF vs obligacje)
- advice      — asking what to do personally (czy powinienem, co wybrać dla mnie)

needs_live_data: true if the question requires any of:
- current rates from NBP or obligacje API (WIBOR, WIRON, stopa procentowa, rata kredytu, COI, EDO)
- current ETF/fund prices for portfolio valuation ("ile warte", "mój portfel", "pozycja",
  "zysk", "strata", ticker symbols like VWCE, IWDA, ISAC, CSPX, EUNL)

Schema: {"query_type": "factual|calculation|comparison|advice", "needs_live_data": bool}
"""

CLASSIFY_USER = "Question: {question}"
