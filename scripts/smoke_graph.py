"""End-to-end smoke test — runs a question through the full agent graph.

classify → retrieve → grade → [rewrite →] generate | fallback

Usage:
    python scripts/smoke_graph.py
    python scripts/smoke_graph.py --question "Czym jest WIBOR?"
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from agent.graph import ask

DEFAULT_QUESTION = "Jaki jest limit wpłat na IKE w 2025 roku?"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()

    print(f"\nQ: {args.question}\n")
    result = ask(args.question)

    print("--- Answer ---")
    print(result["answer"])
    print(f"\nConfidence:  {result['confidence']}")
    print(f"Avg grade:   {result['avg_grade']:.2f}")
    print(f"Query type:  {result['query_type']}")
    print(f"Rewrites:    {result['rewrite_count']}")
    print(f"Give up:     {result['give_up']}")

    if result.get("citations"):
        print("\n--- Citations ---")
        for c in result["citations"]:
            print(f"  {c['source']} | {c['author']} | {c['date']} | {c['title'][:50]}")

    if result.get("disclaimer"):
        print(f"\n--- Disclaimer ---\n{result['disclaimer']}")


if __name__ == "__main__":
    main()
