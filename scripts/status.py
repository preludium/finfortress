"""Print chunk counts per source in the Qdrant collection."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv(ROOT / ".env")

c = QdrantClient(os.getenv("QDRANT_URL", "http://localhost:6333"))
collection = os.getenv("QDRANT_COLLECTION", "polish_finance")

info = c.get_collection(collection)
print(f"Collection : {collection}")
print(f"Total      : {info.points_count:,} chunks")
print(f"Status     : {info.status}")
print()

sources: dict[str, int] = {}
offset = None
while True:
    points, offset = c.scroll(
        collection, limit=1000, offset=offset, with_payload=True, with_vectors=False
    )
    if not points:
        break
    for p in points:
        src = p.payload.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    if offset is None:
        break

print("Sources:")
for src, n in sorted(sources.items(), key=lambda x: -x[1]):
    print(f"  {src:<40} {n:>6} chunks")
