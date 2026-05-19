"""Check whether a URL is already indexed in Qdrant.

Usage:
    python scripts/check_url.py https://inwestomat.eu/ike-przewodnik/
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

load_dotenv(ROOT / ".env")

if len(sys.argv) < 2:
    print("Usage: python scripts/check_url.py <url>")
    sys.exit(1)

url        = sys.argv[1].rstrip("/")
url_slash  = url + "/"

c          = QdrantClient(os.getenv("QDRANT_URL", "http://localhost:6333"))
collection = os.getenv("QDRANT_COLLECTION", "polish_finance")


def search(target: str) -> list:
    points, _ = c.scroll(
        collection,
        scroll_filter=Filter(must=[FieldCondition(key="url", match=MatchValue(value=target))]),
        limit=500,
        with_payload=True,
        with_vectors=False,
    )
    return points


points = search(url) or search(url_slash)

if not points:
    print(f"NOT INDEXED  {url}")
    sys.exit(0)

meta = points[0].payload
print(f"INDEXED  ({len(points)} chunks)")
print(f"  Title   : {meta.get('title', '—')}")
print(f"  Source  : {meta.get('source', '—')}")
print(f"  Author  : {meta.get('author', '—')}")
print(f"  Date    : {meta.get('date', '—')}")
print(f"  Scraped : {meta.get('scraped_at', '—')[:10]}")
