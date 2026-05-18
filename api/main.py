from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from api.routes.health import router as health_router
from api.routes.query import router as query_router
from api.routes.sources import router as sources_router

app = FastAPI(
    title="FinFortress API",
    description="Polish personal finance RAG assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(sources_router)
app.include_router(query_router)


@app.on_event("startup")
async def startup():
    log.info("Building agent graph (loads e5-large + BM25 index)…")
    from agent.graph import build_graph
    app.state.agent = build_graph()
    log.info("Agent ready.")
