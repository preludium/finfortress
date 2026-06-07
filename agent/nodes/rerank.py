from __future__ import annotations

import logging
import os
from typing import Callable

from sentence_transformers import CrossEncoder

from agent.state import AgentState

log = logging.getLogger(__name__)

RERANK_MODEL   = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_TOP_K   = int(os.getenv("RERANK_TOP_K", "6"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() not in ("0", "false", "no")


def build_rerank_node() -> Callable[[AgentState], dict]:
    if not RERANK_ENABLED:
        log.info("Reranker disabled (RERANK_ENABLED=false) — passing context through, trimming to %d", RERANK_TOP_K)

        def passthrough(state: AgentState) -> dict:
            return {"context": state.get("context", [])[:RERANK_TOP_K]}

        return passthrough

    log.info("Loading cross-encoder reranker %s …", RERANK_MODEL)
    model = CrossEncoder(RERANK_MODEL)

    def rerank(state: AgentState) -> dict:
        question = state.get("current_query") or state["question"]
        context  = state.get("context", [])
        if not context:
            return {"context": context}

        scores = model.predict([(question, doc.page_content) for doc in context])
        ranked = sorted(zip(scores, context), key=lambda pair: pair[0], reverse=True)
        top = [doc for _, doc in ranked[:RERANK_TOP_K]]

        log.info("Rerank | %d → %d chunks", len(context), len(top))
        for i, (score, doc) in enumerate(ranked[:RERANK_TOP_K]):
            src   = doc.metadata.get("source", "?")
            title = doc.metadata.get("title", "")[:50]
            log.info("    [%d] score=%.3f %s — %s", i + 1, score, src, title)

        return {"context": top}

    return rerank
