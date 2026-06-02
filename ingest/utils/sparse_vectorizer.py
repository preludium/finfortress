from __future__ import annotations

import re
import zlib

import simplemma
from qdrant_client.models import SparseVector


def _token_id(token: str) -> int:
    """Stable unsigned-32-bit token ID via CRC32. Collision probability negligible for ≤200k unique tokens."""
    return zlib.crc32(token.encode("utf-8")) & 0xFFFF_FFFF


def tokenize(text: str) -> list[str]:
    # Split on non-word chars so "WIBOR," → "wibor" (no trailing punct).
    # Lemmatize each token so kredytu/kredytów/kredytem all → kredyt.
    # Single-char tokens ("w", "i", "z") filtered — too short to carry signal.
    tokens = re.findall(r"\w+", text.lower())
    return [simplemma.lemmatize(t, lang="pl") for t in tokens if len(t) > 1]


def text_to_sparse(text: str) -> SparseVector:
    """TermFrequency sparse vector for a document chunk. Qdrant applies IDF (Inverse Document Frequency) server-side (Modifier.IDF)."""
    tokens = tokenize(text)
    if not tokens:
        return SparseVector(indices=[], values=[])
    term_frequency: dict[int, float] = {}
    for token in tokens:
        token_id = _token_id(token)
        term_frequency[token_id] = term_frequency.get(token_id, 0) + 1.0
    total = float(len(tokens))
    indices = list(term_frequency.keys())
    values = [term_frequency[i] / total for i in indices]
    return SparseVector(indices=indices, values=values)


def query_to_sparse(query: str) -> SparseVector:
    """Binary sparse vector for a query: unique token IDs with weight 1.0."""
    tokens = tokenize(query)
    if not tokens:
        return SparseVector(indices=[], values=[])
    ids = list({_token_id(t) for t in tokens})
    return SparseVector(indices=ids, values=[1.0] * len(ids))
