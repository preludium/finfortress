from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agent.state import INITIAL_STATE
from api.schemas import QueryRequest, QueryResponse

log = logging.getLogger(__name__)
router = APIRouter()


def _build_result(state: dict, thread_id: str | None = None) -> dict:
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations") or [],
        "confidence": state.get("confidence"),
        "disclaimer": state.get("disclaimer"),
        "avg_grade": state.get("avg_grade", 0.0),
        "query_type": state.get("query_type", "factual"),
        "rewrite_count": state.get("rewrite_count", 0),
        "give_up": state.get("give_up", False),
        "thread_id": thread_id,
    }


def _reset_input(question: str) -> dict:
    return {k: v for k, v in INITIAL_STATE.items() if k != "history"} | {"question": question}


# ---------------------------------------------------------------------------
# POST /query — full response (no streaming)
# ---------------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, req: Request):
    app = req.app.state.agent
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = await app.ainvoke(_reset_input(request.question), config)
    return _build_result(result, thread_id)


# ---------------------------------------------------------------------------
# POST /query/stream — SSE streaming, one event per node
# ---------------------------------------------------------------------------


@router.post("/query/stream")
async def query_stream(request: QueryRequest, req: Request):
    app = req.app.state.agent
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async def event_stream():
        final_state: dict = {}

        try:
            async for update in app.astream(_reset_input(request.question), config, stream_mode="updates"):
                for node_name, node_output in update.items():
                    final_state.update(node_output)

                    # Emit a progress event per node
                    event: dict = {"node": node_name}
                    if node_name == "classify":
                        event["query_type"] = node_output.get("query_type")
                        event["needs_live_data"] = node_output.get("needs_live_data")
                    elif node_name == "retrieve":
                        event["chunk_count"] = len(node_output.get("context", []))
                    elif node_name == "grade":
                        event["avg_grade"] = node_output.get("avg_grade")
                        event["needs_rewrite"] = node_output.get("needs_rewrite")
                        event["stale_data"] = node_output.get("stale_data")
                    elif node_name == "rewrite":
                        event["current_query"] = node_output.get("current_query")
                        event["rewrite_count"] = node_output.get("rewrite_count")

                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Final result event
            yield f"data: {json.dumps({'node': 'result', **_build_result(final_state, thread_id)}, ensure_ascii=False)}\n\n"

        except Exception:
            log.exception("Stream error")
            yield f"data: {json.dumps({'node': 'error', 'message': 'Internal error'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # critical for nginx — prevents buffering
        },
    )
