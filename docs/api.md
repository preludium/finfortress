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
  "question": "Jaki jest limit wpłat na IKE w 2025 roku?"
}
```

| Field | Type | Constraints |
|---|---|---|
| `question` | string | 3–1000 characters |

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
  "give_up": false
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

When `give_up` is `true`, `answer` contains a structured Polish-language response explaining the limitation and listing authoritative sources the user can check directly.

**Example:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Jaki jest limit wpłat na IKE w 2025 roku?"}'
```

---

## `POST /query/stream`

SSE streaming — emits one event per graph node as it completes, then a final `result` event. Use this to show retrieval progress in a UI.

**Request body:** identical to `POST /query`.

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
       "rewrite_count": 0, "give_up": false}

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
