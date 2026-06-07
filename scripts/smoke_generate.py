"""Smoke test for generate node — verifies gemma-4-26B-A4B returns valid structured answer."""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from langchain_core.documents import Document
from agent.nodes.generate import build_generate_node

generate = build_generate_node()

state = {
    "question": "Jaki jest limit wpłat na IKE w 2025 roku?",
    "query_type": "factual",
    "avg_grade": 0.85,
    "live_data": None,
    "context": [
        Document(
            page_content="Limit wpłat na IKE w 2025 roku wynosi 23 472 zł, co stanowi trzykrotność przeciętnego prognozowanego wynagrodzenia miesięcznego w gospodarce narodowej.",
            metadata={"source": "inwestomat.eu", "author": "Mateusz Samołyk", "url": "https://inwestomat.eu/ike/", "title": "IKE — kompletny przewodnik", "date": "2025-01-10"},
        ),
    ],
    "rewrite_count": 0,
    "give_up": False,
}

result = generate(state)
print("\n--- Answer ---")
print(result["answer"])
print("\n--- Citations ---")
for c in result["citations"]:
    print(f"  {c['source']} | {c['author']} | {c['date']}")
print(f"\nConfidence: {result['confidence']}")
print(f"Disclaimer: {result['disclaimer']}")
