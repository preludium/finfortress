"""
Embed chunks from data/raw/*.jsonl and upsert into Qdrant.

Pipeline per record:
  raw JSONL record → Document → chunk_documents() → hash dedup → embed → Qdrant upsert

Idempotent: chunks whose content_hash already exists in Qdrant are skipped.

Usage:
    python ingest/embed_and_store.py                          # all raw sources
    python ingest/embed_and_store.py --source inwestomat_blog # one source
    python ingest/embed_and_store.py --dry-run                # count new chunks only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ingest.utils.chunker import chunk_documents
from ingest.utils.embeddings import E5Embeddings, EMBED_DIM
from ingest.utils.hasher import chunk_hash

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
BATCH_SIZE = 32

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "polish_finance")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def _get_client() -> QdrantClient:
    kwargs = {"url": QDRANT_URL}
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    return QdrantClient(**kwargs)


def _ensure_collection(client: QdrantClient, name: str) -> None:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection '%s'", name)
    else:
        log.info("Collection '%s' already exists", name)


def _load_existing_hashes(client: QdrantClient, collection: str) -> set[str]:
    """Scroll all payloads to build in-memory set of known content_hashes."""
    hashes: set[str] = set()
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=collection,
            with_payload=["content_hash"],
            with_vectors=False,
            limit=1000,
            offset=offset,
        )
        for r in results:
            if r.payload and (h := r.payload.get("content_hash")):
                hashes.add(h)
        if offset is None:
            break
    return hashes


# ---------------------------------------------------------------------------
# Raw JSONL → LangChain Documents
# ---------------------------------------------------------------------------

def _records_to_documents(records: list[dict]) -> list[Document]:
    docs = []
    for rec in records:
        metadata = {k: v for k, v in rec.items() if k != "page_content"}
        docs.append(Document(page_content=rec["page_content"], metadata=metadata))
    return docs


# ---------------------------------------------------------------------------
# Core embed + store
# ---------------------------------------------------------------------------

def embed_source(
    source_id: str,
    embedder: E5Embeddings,
    client: QdrantClient,
    existing_hashes: set[str],
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
    collection: str = QDRANT_COLLECTION,
) -> int:
    """Embed one source's raw JSONL. Returns count of newly stored chunks."""
    raw_path = RAW_DIR / f"{source_id}.jsonl"
    if not raw_path.exists():
        log.warning("No raw file for '%s' at %s", source_id, raw_path)
        return 0

    records: list[dict] = []
    with raw_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not records:
        log.warning("Empty raw file: %s", raw_path)
        return 0

    docs = _records_to_documents(records)
    chunks = chunk_documents(docs)
    log.info("%s: %d articles → %d chunks", source_id, len(records), len(chunks))

    new_chunks = []
    new_hashes = []
    for chunk in chunks:
        url = chunk.metadata.get("url", "")
        idx = chunk.metadata.get("chunk_index", 0)
        h = chunk_hash(url, idx, chunk.page_content)
        if h not in existing_hashes:
            new_chunks.append(chunk)
            new_hashes.append(h)

    log.info("%s: %d new chunks (skipping %d duplicates)", source_id, len(new_chunks), len(chunks) - len(new_chunks))

    if dry_run or not new_chunks:
        return len(new_chunks)

    # Embed in batches
    texts = [c.page_content for c in new_chunks]
    vectors = embedder.embed_documents(texts)

    # Build Qdrant points
    points: list[PointStruct] = []
    for chunk, vector, h in zip(new_chunks, vectors, new_hashes):
        payload = {**chunk.metadata, "page_content": chunk.page_content, "content_hash": h}
        points.append(PointStruct(id=str(uuid.uuid4()), vector=vector.tolist(), payload=payload))

    # Upsert in batches
    for i in tqdm(range(0, len(points), batch_size), desc=f"Upserting {source_id}", unit="batch"):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=collection, points=batch)
        existing_hashes.update(new_hashes[i : i + batch_size])

    log.info("%s: stored %d new chunks in Qdrant", source_id, len(points))
    return len(points)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Embed raw JSONL chunks into Qdrant.")
    parser.add_argument("--source", help="Process one source by id (e.g. inwestomat_blog)")
    parser.add_argument("--dry-run", action="store_true", help="Count new chunks only, no embedding")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Embedding batch size")
    args = parser.parse_args()
    batch_size = args.batch_size

    if args.source:
        source_ids = [args.source]
    else:
        source_ids = [p.stem for p in sorted(RAW_DIR.glob("*.jsonl"))]

    if not source_ids:
        log.error("No raw JSONL files found in %s", RAW_DIR)
        sys.exit(1)

    log.info("Sources to process: %s", source_ids)

    if args.dry_run:
        for sid in source_ids:
            raw_path = RAW_DIR / f"{sid}.jsonl"
            if raw_path.exists():
                records = [json.loads(ln) for ln in raw_path.read_text().splitlines() if ln.strip()]
                docs = _records_to_documents(records)
                chunks = chunk_documents(docs)
                log.info("[dry-run] %s: %d articles → %d chunks", sid, len(records), len(chunks))
        return

    embedder = E5Embeddings()
    client = _get_client()
    _ensure_collection(client, QDRANT_COLLECTION)

    log.info("Loading existing hashes from Qdrant…")
    existing_hashes = _load_existing_hashes(client, QDRANT_COLLECTION)
    log.info("Found %d existing chunks in collection", len(existing_hashes))

    total = 0
    for sid in source_ids:
        total += embed_source(sid, embedder, client, existing_hashes, dry_run=False, batch_size=batch_size)

    log.info("Done. Total new chunks stored: %d", total)


if __name__ == "__main__":
    main()
