from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path
from typing import Callable

import numpy as np
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from agent.state import AgentState
from ingest.utils.embeddings import E5Embeddings

BM25_CACHE_PATH = ROOT / "data" / "bm25_cache.pkl"

log = logging.getLogger(__name__)

DENSE_TOP_K = 6
BM25_TOP_K = 6
FINAL_TOP_K = 6
RRF_K = 60
DENSE_WEIGHT = 0.6
BM25_WEIGHT = 0.4


# Sources that contain blog/advice content (as stored in Qdrant payload["source"])
_BLOG_SOURCES = {"inwestomat.eu", "marciniwuc.com"}


def _source_filter(query_type: str) -> tuple[Filter | None, set[str] | None]:
    """Return (qdrant_filter, allowed_sources) for the given query type.

    Advice queries are scoped to blog sources — statute text (isap.sejm.gov.pl)
    doesn't give personal finance advice and adds noise to recommendation answers.
    All other types search the full corpus: factual/calculation/comparison answers
    appear across blogs and legal sources alike.
    """
    if query_type == "advice":
        return (
            Filter(must=[FieldCondition(key="source", match=MatchAny(any=list(_BLOG_SOURCES)))]),
            _BLOG_SOURCES,
        )
    return None, None


# ---------------------------------------------------------------------------
# BM25 index — built once from Qdrant at startup
# ---------------------------------------------------------------------------


def _build_bm25_index(
    client: QdrantClient,
    collection: str,
) -> tuple[BM25Okapi | None, list[str], dict[str, Document]]:
    """Scroll all Qdrant payloads, build BM25 corpus. Caches to disk — only rebuilds when
    the collection point count changes (i.e. after ingestion)."""

    current_count: int = client.get_collection(collection).points_count

    # Try loading from disk cache
    if BM25_CACHE_PATH.exists():
        try:
            with BM25_CACHE_PATH.open("rb") as f:
                cached = pickle.load(f)
            if cached.get("points_count") == current_count:
                log.info("BM25 index loaded from cache: %d documents", len(cached["ids"]))
                return cached["bm25"], cached["ids"], cached["id_to_doc"]
            log.info(
                "BM25 cache stale (%d → %d points) — rebuilding",
                cached.get("points_count"),
                current_count,
            )
        except Exception as exc:
            log.warning("BM25 cache load failed: %s — rebuilding", exc)

    log.info("Building BM25 index from Qdrant collection '%s'…", collection)

    texts: list[str] = []
    ids: list[str] = []
    id_to_doc: dict[str, Document] = {}

    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=collection,
            with_payload=True,
            with_vectors=False,
            limit=500,
            offset=offset,
        )
        for point in results:
            if not point.payload:
                continue
            text = point.payload.get("page_content", "")
            if not text:
                continue
            pid = str(point.id)
            texts.append(text)
            ids.append(pid)
            metadata = {k: v for k, v in point.payload.items() if k != "page_content"}
            id_to_doc[pid] = Document(page_content=text, metadata=metadata)

        if offset is None:
            break

    if not texts:
        log.warning("BM25 index empty — no documents in Qdrant yet")
        return None, [], {}

    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    log.info("BM25 index built: %d documents", len(texts))

    # Persist to disk
    try:
        BM25_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with BM25_CACHE_PATH.open("wb") as f:
            pickle.dump(
                {"points_count": current_count, "bm25": bm25, "ids": ids, "id_to_doc": id_to_doc},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        log.info("BM25 index cached → %s", BM25_CACHE_PATH)
    except Exception as exc:
        log.warning("BM25 cache save failed: %s", exc)

    return bm25, ids, id_to_doc


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def _weighted_rrf(
    dense_ids: list[str],
    bm25_ids: list[str],
    k: int = RRF_K,
) -> list[str]:
    scores: dict[str, float] = {}
    for rank, doc_id in enumerate(dense_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + DENSE_WEIGHT / (k + rank + 1)
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + BM25_WEIGHT / (k + rank + 1)
    return sorted(scores, key=lambda d: scores[d], reverse=True)


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------


def build_retrieve_node(
    client: QdrantClient,
    collection: str,
    embedder: E5Embeddings,
) -> Callable[[AgentState], dict]:
    """Build retrieve node with BM25 index captured in closure (built once at startup)."""

    bm25, corpus_ids, id_to_doc = _build_bm25_index(client, collection)

    def retrieve(state: AgentState) -> dict:
        query      = state.get("current_query") or state["question"]
        query_type = state.get("query_type", "factual")
        qdrant_filter, allowed_sources = _source_filter(query_type)
        log.info(
            "Retrieve | query: %r  type=%s  filter=%s",
            query[:80], query_type, "advice→blogs" if allowed_sources else "none",
        )

        # --- Dense retrieval ---
        # embed_query applies the required "query:" prefix for E5 — never call
        # embedder.model.encode() directly, it would skip the prefix and degrade recall.
        query_vector = embedder.embed_query(query)
        dense_response = client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=DENSE_TOP_K,
            with_payload=True,
            query_filter=qdrant_filter,
        )
        dense_results = dense_response.points
        dense_ids = [str(r.id) for r in dense_results]

        # Ensure id_to_doc covers dense hits (may not be in BM25 corpus if index was stale)
        for r in dense_results:
            pid = str(r.id)
            if pid not in id_to_doc and r.payload:
                text = r.payload.get("page_content", "")
                meta = {k: v for k, v in r.payload.items() if k != "page_content"}
                id_to_doc[pid] = Document(page_content=text, metadata=meta)

        log.info("  dense hits: %d", len(dense_ids))

        # --- BM25 retrieval ---
        bm25_ids: list[str] = []
        if bm25 is not None and corpus_ids:
            tokenized_query = query.lower().split()
            scores = bm25.get_scores(tokenized_query)
            # Zero out excluded sources before argsort so the slice always
            # draws from allowed sources — filtering after the slice would
            # silently return fewer than BM25_TOP_K candidates.
            if allowed_sources is not None:
                for i, cid in enumerate(corpus_ids):
                    if id_to_doc.get(cid, Document(page_content="", metadata={})).metadata.get("source") not in allowed_sources:
                        scores[i] = 0.0
            top_indices = np.argsort(scores)[::-1][:BM25_TOP_K]
            bm25_ids = [corpus_ids[i] for i in top_indices if scores[i] > 0]
            log.info("  BM25 hits: %d", len(bm25_ids))
        else:
            log.warning("  BM25 index empty — using dense only")

        # --- Weighted RRF merge ---
        merged_ids = _weighted_rrf(dense_ids, bm25_ids)[:FINAL_TOP_K]

        context: list[Document] = []
        for doc_id in merged_ids:
            doc = id_to_doc.get(doc_id)
            if doc:
                context.append(doc)

        log.info("  merged context: %d chunks", len(context))
        for i, doc in enumerate(context):
            src = doc.metadata.get("source", "?")
            title = doc.metadata.get("title", "")[:50]
            log.info("    [%d] %s — %s", i + 1, src, title)

        return {"context": context}

    return retrieve
