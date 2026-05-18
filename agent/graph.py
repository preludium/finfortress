from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Api key is used with an insecure connection")

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.state import AgentState, INITIAL_STATE
from agent.nodes.classify import classify
from agent.nodes.fallback import fallback
from agent.nodes.fetch_live import fetch_live
from agent.nodes.generate import build_generate_node
from agent.nodes.grade import build_grade_node
from agent.nodes.retrieve import build_retrieve_node
from agent.nodes.rewrite import rewrite
from ingest.utils.embeddings import E5Embeddings

log = logging.getLogger(__name__)

MAX_REWRITES    = int(os.getenv("MAX_REWRITES", "2"))
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "polish_finance")
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY") or None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_grade(state: AgentState) -> str:
    # Live data provides authoritative answer — context quality is supplementary
    if state.get("live_data"):
        log.info("Live data present — proceeding to generate regardless of grade")
        return "generate"
    if not state.get("needs_rewrite", False):
        return "generate"
    if state.get("rewrite_count", 0) >= MAX_REWRITES:
        log.info("Max rewrites (%d) reached — falling back", MAX_REWRITES)
        return "fallback"
    return "rewrite"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(qdrant_client: QdrantClient | None = None, embedder: E5Embeddings | None = None):
    """Build and compile the agent graph. Accepts optional pre-built dependencies for testing."""

    if qdrant_client is None:
        kwargs = {"url": QDRANT_URL}
        if QDRANT_API_KEY:
            kwargs["api_key"] = QDRANT_API_KEY
        qdrant_client = QdrantClient(**kwargs)
    if embedder is None:
        embedder = E5Embeddings()

    retrieve_node = build_retrieve_node(qdrant_client, QDRANT_COLLECTION, embedder)
    grade_node    = build_grade_node()
    generate_node = build_generate_node()

    graph = StateGraph(AgentState)

    graph.add_node("classify",   classify)
    graph.add_node("fetch_live", fetch_live)
    graph.add_node("retrieve",   retrieve_node)
    graph.add_node("grade",      grade_node)
    graph.add_node("rewrite",    rewrite)
    graph.add_node("generate",   generate_node)
    graph.add_node("fallback",   fallback)

    graph.add_edge(START,        "classify")
    graph.add_edge("classify",   "fetch_live")
    graph.add_edge("fetch_live", "retrieve")
    graph.add_edge("retrieve",  "grade")
    graph.add_conditional_edges(
        "grade",
        _route_after_grade,
        {"generate": "generate", "rewrite": "rewrite", "fallback": "fallback"},
    )
    graph.add_edge("rewrite",   "retrieve")
    graph.add_edge("generate",  END)
    graph.add_edge("fallback",  END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Convenience: run a single question
# ---------------------------------------------------------------------------

def ask(question: str, app=None) -> dict:
    """Run a question through the compiled graph. Builds graph if not provided."""
    if app is None:
        app = build_graph()
    state = {**INITIAL_STATE, "question": question}
    return app.invoke(state)
