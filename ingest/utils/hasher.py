from __future__ import annotations

import hashlib


def chunk_hash(url: str, chunk_index: int, page_content: str) -> str:
    """SHA-256 of (url + chunk_index + first 100 chars of content). Used for dedup in Qdrant."""
    raw = url + str(chunk_index) + page_content[:100]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
