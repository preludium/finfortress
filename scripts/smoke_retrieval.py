"""
Quick retrieval smoke test — runs 5 Polish finance questions and prints top chunks.
No LLM calls, no grading. Verifies Qdrant + BM25 + RRF are working.

Usage:
    python scripts/smoke_retrieval.py
    python scripts/smoke_retrieval.py --query "Czym jest WIBOR?"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

from ingest.utils.embeddings import E5Embeddings
from agent.nodes.retrieve import build_retrieve_node

COLLECTION = os.getenv("QDRANT_COLLECTION", "polish_finance")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

TEST_QUESTIONS = [
    "Jaki jest limit wpłat na IKE w 2025 roku?",
    "Czym różni się WIRON od WIBOR?",
    "Czy ETF w IKE płaci podatek Belki?",
    "Jak działa kredyt hipoteczny w Polsce?",
    "Co to są obligacje skarbowe COI?",
]


def run(query: str, retrieve_fn) -> None:
    state = {
        "question": query,
        "current_query": None,
        "query_type": "factual",
        "needs_live_data": False,
        "context": [],
        "avg_grade": 0.0,
        "needs_rewrite": False,
        "stale_data": False,
        "rewrite_count": 0,
        "live_data": None,
        "answer": None,
        "citations": None,
        "confidence": None,
        "disclaimer": None,
        "give_up": False,
    }
    result = retrieve_fn(state)
    context = result["context"]

    print(f"\n{'='*70}")
    print(f"Q: {query}")
    print(f"{'='*70}")
    if not context:
        print("  !! NO RESULTS — check Qdrant has data")
        return
    for i, doc in enumerate(context, 1):
        src    = doc.metadata.get("source", "?")
        title  = doc.metadata.get("title", "")[:55]
        date   = doc.metadata.get("date", "")
        preview = doc.page_content[:200].replace("\n", " ")
        print(f"  [{i}] {src} | {date} | {title}")
        print(f"      {preview}…")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Single custom query instead of test set")
    args = parser.parse_args()

    log.info("Connecting to Qdrant at %s", QDRANT_URL)
    client = QdrantClient(url=QDRANT_URL)

    info = client.get_collection(COLLECTION)
    log.info("Collection '%s': %d points, status=%s", COLLECTION, info.points_count, info.status)

    if info.points_count == 0:
        log.error("Collection is empty — run embed_and_store.py first")
        sys.exit(1)

    log.info("Loading embedding model…")
    embedder = E5Embeddings()

    retrieve = build_retrieve_node(client, COLLECTION, embedder)

    questions = [args.query] if args.query else TEST_QUESTIONS
    for q in questions:
        run(q, retrieve)

    print()


if __name__ == "__main__":
    main()
