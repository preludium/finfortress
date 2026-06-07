from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

ROOT = Path(__file__).parent.parent.parent
from agent.state import AgentState
from ingest.utils.embeddings import E5Embeddings
from ingest.utils.sparse_vectorizer import query_to_sparse

log = logging.getLogger(__name__)

# Retrieval over-fetches a wide candidate pool; the rerank node narrows it to its
# top-k before grading. Keep these >= the reranker's output (RERANK_TOP_K, default 6).
DENSE_TOP_K  = 12
BM25_TOP_K   = 12
FUSION_TOP_K = 12
RRF_K        = 60
DENSE_WEIGHT = 0.6
BM25_WEIGHT  = 0.4

_BLOGS_JSON = ROOT / "data" / "my_sources" / "blogs.json"


def _load_blog_sources() -> set[str]:
    """Derive blog domains from blogs.json so the filter stays in sync with the corpus.

    blogs.json is the source of truth for which URLs are indexed as blogs. Reading it
    here avoids _BLOG_SOURCES drifting silently when new blogs are added to the manifest.
    Falls back to an empty set (no filtering) if the file is missing or unreadable.
    """
    try:
        entries = json.loads(_BLOGS_JSON.read_text(encoding="utf-8"))
        domains = set()
        for entry in entries:
            host = urlparse(entry.get("url", "")).hostname or ""
            # strip www. prefix — Qdrant payload stores bare domain (e.g. "infakt.pl")
            domains.add(host.removeprefix("www."))
        domains.discard("")
        log.info("Blog sources for advice filter: %s", sorted(domains))
        return domains
    except Exception as exc:
        log.warning("Could not load blog sources from %s: %s — advice filter disabled", _BLOGS_JSON, exc)
        return set()


def _source_filter(query_type: str, blog_sources: set[str]) -> Filter | None:
    """Return Qdrant filter for the given query type.

    Advice queries are scoped to blog sources — statute text (isap.sejm.gov.pl)
    doesn't give personal finance advice and adds noise to recommendation answers.
    All other types search the full corpus: factual/calculation/comparison answers
    appear across blogs and legal sources alike.
    """
    if query_type == "advice" and blog_sources:
        return Filter(must=[FieldCondition(key="source", match=MatchAny(any=sorted(blog_sources)))])
    return None


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


def build_retrieve_node(
    client: QdrantClient,
    collection: str,
    embedder: E5Embeddings,
) -> Callable[[AgentState], dict]:
    coll_info = client.get_collection(collection)
    has_sparse = bool(coll_info.config.params.sparse_vectors)
    if not has_sparse:
        log.warning(
            "Collection '%s' has no sparse vectors — run `just backfill-sparse` to enable hybrid search",
            collection,
        )

    # Load blog domains once at startup — derived from blogs.json so the filter
    # stays in sync automatically when new blogs are added to the manifest.
    blog_sources = _load_blog_sources()

    def retrieve(state: AgentState) -> dict:
        query      = state.get("current_query") or state["question"]
        query_type = state.get("query_type", "factual")
        qdrant_filter = _source_filter(query_type, blog_sources)
        log.info(
            "Retrieve | query: %r  type=%s  filter=%s",
            query[:80], query_type, "advice→blogs" if qdrant_filter else "none",
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

        id_to_doc: dict[str, Document] = {}
        for r in dense_results:
            pid = str(r.id)
            if r.payload:
                text = r.payload.get("page_content", "")
                meta = {k: v for k, v in r.payload.items() if k != "page_content"}
                id_to_doc[pid] = Document(page_content=text, metadata=meta)

        log.info("  dense hits: %d", len(dense_ids))

        # --- Sparse (BM25) retrieval via Qdrant native sparse index ---
        bm25_ids: list[str] = []
        if has_sparse:
            sparse_query = query_to_sparse(query)
            if sparse_query.indices:
                sparse_response = client.query_points(
                    collection_name=collection,
                    query=sparse_query,
                    using="bm25",
                    limit=BM25_TOP_K,
                    with_payload=True,
                    query_filter=qdrant_filter,
                )
                for r in sparse_response.points:
                    pid = str(r.id)
                    bm25_ids.append(pid)
                    if pid not in id_to_doc and r.payload:
                        text = r.payload.get("page_content", "")
                        meta = {k: v for k, v in r.payload.items() if k != "page_content"}
                        id_to_doc[pid] = Document(page_content=text, metadata=meta)
            log.info("  sparse hits: %d", len(bm25_ids))
        else:
            log.warning("  sparse index unavailable — dense only")

        # --- Weighted RRF merge ---
        merged_ids = _weighted_rrf(dense_ids, bm25_ids)[:FUSION_TOP_K]
        context = [id_to_doc[did] for did in merged_ids if did in id_to_doc]

        log.info("  merged context: %d chunks", len(context))
        for i, doc in enumerate(context):
            src   = doc.metadata.get("source", "?")
            title = doc.metadata.get("title", "")[:50]
            log.info("    [%d] %s — %s", i + 1, src, title)

        return {"context": context}

    return retrieve
