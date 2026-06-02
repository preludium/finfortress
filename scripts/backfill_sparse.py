"""
One-time migration: add Qdrant native sparse (bm25) vectors to an existing collection.

What it does:
  1. Scrolls all existing points (keeping their dense vectors — no re-embedding).
  2. Recreates the collection with the same name + sparse_vectors_config.
  3. Re-upserts all points with both the original dense vector and a freshly computed
     TF sparse vector (Modifier.IDF applied server-side at query time).

Safe to re-run: if the collection already has sparse config it exits immediately.

Usage:
    python scripts/backfill_sparse.py
    python scripts/backfill_sparse.py --dry-run   # print stats, no writes
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from ingest.utils.embeddings import EMBED_DIM
from ingest.utils.sparse_vectorizer import text_to_sparse

QDRANT_URL        = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "polish_finance")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY") or None
BATCH_SIZE        = 256


def _get_client() -> QdrantClient:
    kwargs: dict = {"url": QDRANT_URL}
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    return QdrantClient(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill sparse vectors into Qdrant collection.")
    parser.add_argument("--dry-run", action="store_true", help="Print stats, no writes")
    parser.add_argument("--force", action="store_true", help="Re-index even if collection already has sparse vectors (use after tokenizer changes)")
    args = parser.parse_args()

    client = _get_client()

    if not client.collection_exists(QDRANT_COLLECTION):
        log.error("Collection '%s' does not exist", QDRANT_COLLECTION)
        sys.exit(1)

    info = client.get_collection(QDRANT_COLLECTION)
    if info.config.params.sparse_vectors and not args.force:
        log.info("Collection '%s' already has sparse vectors — nothing to do", QDRANT_COLLECTION)
        log.info("Use --force to re-index with the current tokenizer (needed after tokenizer changes)")
        return

    total_points = info.points_count
    log.info("Scrolling %d points from '%s'…", total_points, QDRANT_COLLECTION)

    # Scroll all points keeping their dense vectors (no re-embedding)
    records: list[tuple] = []  # (id, dense_vector, payload)
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            with_vectors=True,
            with_payload=True,
            limit=500,
            offset=offset,
        )
        for p in results:
            if p.vector is not None and p.payload:
                # When collection has named vectors (dense="" + sparse="bm25"),
                # p.vector is a dict — extract just the dense vector.
                dense = p.vector.get("") if isinstance(p.vector, dict) else p.vector
                if dense is not None:
                    records.append((p.id, dense, p.payload))
        if offset is None:
            break

    log.info("Scrolled %d points", len(records))

    if args.dry_run:
        log.info("[dry-run] Would recreate collection with sparse config and re-upsert %d points", len(records))
        return

    # Recreate collection with sparse config (same name, same dense params)
    log.info("Recreating collection '%s' with sparse_vectors_config…", QDRANT_COLLECTION)
    client.delete_collection(QDRANT_COLLECTION)
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)},
    )
    log.info("Collection recreated")

    # Re-upsert with both dense + sparse
    points: list[PointStruct] = []
    for pid, dense_vec, payload in records:
        text = payload.get("page_content", "")
        sparse = text_to_sparse(text) if text else None
        vec: dict | list = {"": dense_vec, "bm25": sparse} if sparse and sparse.indices else dense_vec
        points.append(PointStruct(id=pid, vector=vec, payload=payload))

    log.info("Upserting %d points with sparse vectors…", len(points))
    for i in tqdm(range(0, len(points), BATCH_SIZE), desc="Backfill", unit="batch"):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i : i + BATCH_SIZE])

    log.info("Done. %d points backfilled with sparse vectors.", len(points))


if __name__ == "__main__":
    main()
