REWRITE_SYSTEM = """\
You improve a Polish personal finance search query that failed to find relevant results.
Return only the improved query string — no explanation, no JSON, no punctuation at end.

If failure reason is LOW RELEVANCE: add specificity, Polish financial terms, context.
If failure reason is STALE DATA: add the current year and signal need for current data.

Examples:
  original: "IKE" → improved: "limit rocznych wpłat na IKE 2025 Polska"
  original: "WIBOR" → improved: "aktualna stawka WIBOR 3M 2025 Polska stopa referencyjna"
"""

REWRITE_USER = """\
Original question: {question}
Failure reason: {reason}
Failed chunks (titles): {chunk_titles}

Improved query:"""
