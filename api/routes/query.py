from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.state import INITIAL_STATE
from api.schemas import QueryRequest, QueryResponse

log = logging.getLogger(__name__)
router = APIRouter()


def _build_result(state: dict) -> dict:
    return {
        "answer":       state.get("answer", ""),
        "citations":    state.get("citations") or [],
        "confidence":   state.get("confidence"),
        "disclaimer":   state.get("disclaimer"),
        "avg_grade":    state.get("avg_grade", 0.0),
        "query_type":   state.get("query_type", "factual"),
        "rewrite_count": state.get("rewrite_count", 0),
        "give_up":      state.get("give_up", False),
    }


# ---------------------------------------------------------------------------
# POST /query — full response (no streaming)
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, req: Request):
    app = req.app.state.agent
    state = {**INITIAL_STATE, "question": request.question}
    result = await app.ainvoke(state)
    return _build_result(result)


# ---------------------------------------------------------------------------
# POST /query/stream — SSE streaming, one event per node
# ---------------------------------------------------------------------------

@router.post("/query/stream")
async def query_stream(request: QueryRequest, req: Request):
    app = req.app.state.agent

    async def event_stream():
        state = {**INITIAL_STATE, "question": request.question}
        final_state: dict = {}

        try:
            async for update in app.astream(state, stream_mode="updates"):
                for node_name, node_output in update.items():
                    final_state.update(node_output)

                    # Emit a progress event per node
                    event: dict = {"node": node_name}
                    if node_name == "classify":
                        event["query_type"]     = node_output.get("query_type")
                        event["needs_live_data"] = node_output.get("needs_live_data")
                    elif node_name == "retrieve":
                        event["chunk_count"] = len(node_output.get("context", []))
                    elif node_name == "grade":
                        event["avg_grade"]    = node_output.get("avg_grade")
                        event["needs_rewrite"] = node_output.get("needs_rewrite")
                        event["stale_data"]   = node_output.get("stale_data")
                    elif node_name == "rewrite":
                        event["current_query"] = node_output.get("current_query")
                        event["rewrite_count"] = node_output.get("rewrite_count")

                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Final result event
            yield f"data: {json.dumps({'node': 'result', **_build_result(final_state)}, ensure_ascii=False)}\n\n"

        except Exception as exc:
            log.exception("Stream error: %s", exc)
            yield f"data: {json.dumps({'node': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # critical for nginx — prevents buffering
        },
    )
