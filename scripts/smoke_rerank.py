"""
Rerank smoke test — runs Polish finance questions through retrieval + cross-encoder
rerank and prints the top chunks with scores. No grader/generator LLM calls.

Usage:
    python scripts/smoke_rerank.py
    python scripts/smoke_rerank.py --query "Czym jest WIBOR?"
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
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

from ingest.utils.embeddings import E5Embeddings
from agent.nodes.retrieve import build_retrieve_node
from agent.nodes.rerank import build_rerank_node

COLLECTION = os.getenv("QDRANT_COLLECTION", "polish_finance")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

TEST_QUESTIONS: list[tuple[str, str]] = [
    ("Jaki jest limit wpłat na IKE w 2025 roku?", "factual"),
    ("Czym różni się WIRON od WIBOR?", "factual"),
    ("Czy ETF w IKE płaci podatek Belki?", "factual"),
    ("Jak działa kredyt hipoteczny w Polsce?", "factual"),
    ("Co to są obligacje skarbowe COI?", "factual"),
    ("W co inwestować przy horyzoncie 30 lat i umiarkowanym ryzyku?", "advice"),
]


def _state(query: str, query_type: str) -> dict:
    return {
        "question": query,
        "current_query": None,
        "query_type": query_type,
        "context": [],
    }


def run(query: str, retrieve_fn, rerank_fn, query_type: str = "factual") -> None:
    state = _state(query, query_type)
    state.update(retrieve_fn(state))
    pool = len(state["context"])
    state.update(rerank_fn(state))
    context = state["context"]

    print(f"\n{'='*70}")
    print(f"Q: {query}   (pool={pool} → top={len(context)})")
    print(f"{'='*70}")
    if not context:
        print("  !! NO RESULTS — check Qdrant has data")
        return
    for i, doc in enumerate(context, 1):
        src     = doc.metadata.get("source", "?")
        title   = doc.metadata.get("title", "")[:55]
        date    = doc.metadata.get("date", "")
        preview = doc.page_content[:200].replace("\n", " ")
        print(f"  [{i}] {src} | {date} | {title}")
        print(f"      {preview}…")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Single custom query instead of test set")
    parser.add_argument("--type", default="factual",
                        choices=["factual", "calculation", "comparison", "advice"],
                        help="query_type for --query (default: factual)")
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
    rerank   = build_rerank_node()

    if args.query:
        run(args.query, retrieve, rerank, query_type=args.type)
    else:
        for q, qtype in TEST_QUESTIONS:
            run(q, retrieve, rerank, query_type=qtype)

    print()


if __name__ == "__main__":
    main()
