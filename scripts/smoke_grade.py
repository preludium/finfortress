"""Quick smoke test for the grade node — verifies oMLX returns valid JSON scores."""

import asyncio
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from langchain_core.documents import Document
from agent.nodes.grade import build_grade_node

grade = build_grade_node()

state = {
    "question": "Jaki jest limit wpłat na IKE w 2025 roku?",
    "context": [
        Document(
            page_content="Limit wpłat na IKE w 2025 roku wynosi 23 472 zł, co stanowi trzykrotność przeciętnego prognozowanego wynagrodzenia miesięcznego.",
            metadata={"source": "inwestomat.eu", "date": "2025-01-15"},
        ),
        Document(
            page_content="Podatek Belki wynosi 19% od zysków kapitałowych i jest pobierany automatycznie przez biuro maklerskie.",
            metadata={"source": "inwestomat.eu", "date": "2024-03-10"},
        ),
    ],
    "rewrite_count": 0,
    "give_up": False,
}

result = asyncio.run(grade(state))
print("\n--- Grade result ---")
print(f"avg_grade:     {result['avg_grade']:.2f}")
print(f"needs_rewrite: {result['needs_rewrite']}")
print(f"stale_data:    {result['stale_data']}")
