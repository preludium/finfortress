# API reference

The FastAPI backend exposes three endpoints. Interactive docs are available at `http://localhost:8000/docs` when the server is running.

Start the server:

```bash
uvicorn api.main:app --reload --port 8000
```

---

## `POST /query`

Synchronous — runs the full agent graph and returns the complete answer.

**Request body:**

```json
{
  "question": "Jaki jest limit wpłat na IKE w 2025 roku?",
  "thread_id": "a1b2c3d4-..."
}
```

| Field | Type | Constraints |
|---|---|---|
| `question` | string | 3–1000 characters |
| `thread_id` | string \| null | Optional. Pass the `thread_id` from a previous response to continue a conversation. Omit (or pass `null`) to start a new session. |

**Response:**

```json
{
  "answer": "Limit wpłat na IKE w 2025 roku wynosi 23 472 zł. Kwota jest równa trzykrotności przeciętnego wynagrodzenia w gospodarce narodowej...",
  "citations": [
    {
      "source": "KNF / inwestoredukacja.pl",
      "author": "KNF",
      "url": "https://inwestoredukacja.pl/ike/",
      "title": "Indywidualne Konto Emerytalne — limity wpłat",
      "date": "2025-01-10"
    }
  ],
  "confidence": "high",
  "disclaimer": null,
  "avg_grade": 0.87,
  "query_type": "factual",
  "rewrite_count": 0,
  "give_up": false,
  "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `answer` | string | Generated answer in the language of the question |
| `citations` | array | Source citations for factual claims in the answer |
| `confidence` | `"high"` \| `"medium"` \| `"low"` | Based on `avg_grade` across retrieved chunks |
| `disclaimer` | string \| null | Non-null when `query_type == "advice"` — financial advice disclaimer |
| `avg_grade` | float | Average grader score across retrieved chunks (0–1) |
| `query_type` | `"factual"` \| `"calculation"` \| `"comparison"` \| `"advice"` | Classified query type |
| `rewrite_count` | int | Number of query rewrites performed (0–2) |
| `give_up` | bool | `true` if agent could not find reliable context and returned a fallback response |
| `thread_id` | string | Thread identifier for this conversation. Pass it back in the next request to continue the session. |

When `give_up` is `true`, `answer` contains a structured response explaining the limitation and listing authoritative sources the user can check directly.

**Example:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Jaki jest limit wpłat na IKE w 2025 roku?"}'
```

---

## `POST /query/stream`

SSE streaming — emits one event per graph node as it completes, then a final `result` event. Use this to show retrieval progress in a UI.

**Request body:** identical to `POST /query` — same `question` + optional `thread_id`.

**Response:** `text/event-stream`. Each line is `data: <json>\n\n`.

**Event sequence:**

```
data: {"node": "classify", "query_type": "factual", "needs_live_data": false}

data: {"node": "fetch_live"}

data: {"node": "retrieve", "chunk_count": 6}

data: {"node": "grade", "avg_grade": 0.79, "needs_rewrite": false, "stale_data": false}

data: {"node": "generate"}

data: {"node": "result", "answer": "...", "citations": [...], "confidence": "high",
       "disclaimer": null, "avg_grade": 0.79, "query_type": "factual",
       "rewrite_count": 0, "give_up": false, "thread_id": "a1b2c3d4-..."}

data: [DONE]
```

If grading fails and the query is rewritten, you'll see additional `rewrite` + `retrieve` + `grade` events before `generate`:

```
data: {"node": "rewrite", "current_query": "limit rocznych wpłat IKE 2025 Polska", "rewrite_count": 1}

data: {"node": "retrieve", "chunk_count": 6}

data: {"node": "grade", "avg_grade": 0.83, "needs_rewrite": false, "stale_data": false}

data: {"node": "generate"}
```

**Node-specific event fields:**

| Node | Extra fields |
|---|---|
| `classify` | `query_type`, `needs_live_data` |
| `retrieve` | `chunk_count` |
| `grade` | `avg_grade`, `needs_rewrite`, `stale_data` |
| `rewrite` | `current_query`, `rewrite_count` |
| `result` | full response — same fields as `POST /query` |
| `error` | `message: "Internal error"` |

The stream always ends with `data: [DONE]\n\n`, even on error.

**Important:** If the API runs behind nginx, add `X-Accel-Buffering: no` to the proxy config — nginx buffers SSE by default and the user sees nothing until the full answer is ready.

**Example:**

```bash
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question": "Czym różni się WIRON od WIBOR?"}' \
  --no-buffer
```

---

## Conversation memory

Both endpoints support multi-turn conversations via `thread_id`. The agent remembers previous questions and answers within a thread and injects up to 5 prior turns into the generation prompt.

**How to use it:**

1. Send the first message without a `thread_id` (or with `null`).
2. The response includes a `thread_id`. Store it on the client.
3. Pass the same `thread_id` in every subsequent request to continue the conversation.

```bash
# First message — no thread_id
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Jaki jest limit IKE w 2025?"}'
# → response includes "thread_id": "abc-123"

# Follow-up — same thread
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "A co z IKZE?", "thread_id": "abc-123"}'
# Agent knows the previous question was about IKE limits
```

Thread history is persisted to `data/memory.sqlite` on disk and survives API restarts. Omitting `thread_id` always starts a fresh stateless session.

---

## `GET /health`

Liveness check.

**Response:**

```json
{ "status": "ok" }
```

---

## `GET /sources`

Returns the list of indexed sources from `data/sources_manifest.json`.

---

## CORS

The API accepts cross-origin requests from origins listed in `CORS_ORIGINS` (`.env`). Default: `http://localhost:8501` (Streamlit local port). To allow additional origins:

```bash
CORS_ORIGINS=http://localhost:8501,https://your-frontend.example.com
```

---

## Notes

- Both `/query` and `/query/stream` share the same agent graph instance, built once at API startup.
- The agent graph loads `multilingual-e5-large` and builds the BM25 index at startup. First startup takes 10–30 seconds; subsequent restarts are faster (model cached by HuggingFace).
- All text responses (answers, citations) are in the language of the question — Polish or English.
