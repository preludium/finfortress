"""Show indexed sources grouped by domain with document and chunk counts."""

import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv(ROOT / ".env")

c = QdrantClient(os.getenv("QDRANT_URL", "http://localhost:6333"))
collection = os.getenv("QDRANT_COLLECTION", "polish_finance")

# domain → {urls seen, chunk count}
domains: dict[str, dict] = defaultdict(lambda: {"urls": set(), "chunks": 0})

offset = None
while True:
    points, offset = c.scroll(
        collection, limit=1000, offset=offset, with_payload=True, with_vectors=False
    )
    if not points:
        break
    for p in points:
        url = p.payload.get("url") or p.payload.get("source_url") or ""
        domain = urlparse(url).netloc or p.payload.get("source", "unknown")
        domains[domain]["urls"].add(url)
        domains[domain]["chunks"] += 1
    if offset is None:
        break

total_docs   = sum(len(d["urls"]) for d in domains.values())
total_chunks = sum(d["chunks"] for d in domains.values())

print(f"Knowledge base: {total_docs} documents, {total_chunks:,} chunks\n")
print(f"  {'Domain':<40} {'Docs':>6}  {'Chunks':>8}")
print(f"  {'─' * 40} {'─' * 6}  {'─' * 8}")

for domain, data in sorted(domains.items(), key=lambda x: -x[1]["chunks"]):
    doc_count = len(data["urls"])
    print(f"  {domain:<40} {doc_count:>6}  {data['chunks']:>8,}")
