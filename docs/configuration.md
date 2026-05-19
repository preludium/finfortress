# Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in the values for your setup.

```bash
cp .env.example .env
```

---

## LLM

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | API key. For OpenAI: `sk-...`. For oMLX: `omlx-...` (find in admin dashboard). |
| `OPENAI_BASE_URL` | *(unset — uses OpenAI)* | Set to `http://localhost:8000/v1` to point at a local oMLX server. |
| `LLM_MODEL` | `Qwen2.5-32B-Instruct-4bit` | Generator model. Set to `gpt-4o` for OpenAI. |
| `GRADER_MODEL` | `Qwen2.5-7B-Instruct-4bit` | Grader model — fires up to 6× per query so use a smaller/faster model. Set to `gpt-4o-mini` for OpenAI. |

The grader and generator use the same `OPENAI_BASE_URL`. If you use oMLX, both models must be downloaded in oMLX. See [`docs/local-llm-setup.md`](local-llm-setup.md).

---

## Vector store

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant instance URL. For Qdrant Cloud: `https://<cluster-id>.us-east4-0.gcp.cloud.qdrant.io`. |
| `QDRANT_COLLECTION` | `polish_finance` | Collection name within Qdrant. |
| `QDRANT_API_KEY` | *(unset)* | Required only for Qdrant Cloud. Leave unset for local Docker. |

---

## Embeddings

| Variable | Default | Description |
|---|---|---|
| `HUGGINGFACE_TOKEN` | *(unset)* | Only needed for gated HuggingFace models. `multilingual-e5-large` is public — no token required. |

Embeddings always run locally via `sentence-transformers`. They are never sent to any external API regardless of LLM configuration.

---

## Agent behaviour

| Variable | Default | Description |
|---|---|---|
| `GRADE_THRESHOLD` | `0.6` | Minimum average chunk score to proceed to generation without rewriting. Below this, a query rewrite is triggered. Tune upward for stricter retrieval, downward to reduce fallbacks on harder topics. |
| `MAX_REWRITES` | `2` | Maximum query rewrite attempts before falling back. After this limit, if `avg_grade ≥ GRADE_THRESHOLD` the agent generates with `confidence: "low"`; otherwise it falls back entirely. |
| `STALE_MONTHS` | `18` | Document age threshold (months) for temporal mismatch detection. A document older than this is flagged as potentially stale when the question implies current data (e.g. mentions "teraz", "aktualny", "2025"). |

---

## API

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:8501` | Comma-separated list of allowed CORS origins for the FastAPI backend. Add your frontend URL here. |

---

## Observability

| Variable | Default | Description |
|---|---|---|
| `LANGCHAIN_API_KEY` | *(unset)* | LangSmith API key. Leave unset to disable tracing. |
| `LANGCHAIN_TRACING_V2` | `false` | Set to `true` to send traces to LangSmith. Requires `LANGCHAIN_API_KEY`. |
| `LANGCHAIN_PROJECT` | `finfortress` | LangSmith project name. Traces for each run appear under this project. |

LangSmith traces every node execution, LLM call, and retrieved chunk. Useful for debugging grading decisions and rewrite behaviour.

---

## Ingestion

| Variable | Default | Description |
|---|---|---|
| `SCRAPE_DELAY_SECONDS` | `1.5` | Delay between HTTP requests during blog scraping. Increase if you get rate-limited. Do not set below 1.0 — be polite to bloggers' servers. |
| `WHISPER_MODEL` | `base` | Whisper model size for video transcript generation: `tiny`, `base`, `small`, `medium`, `large`. `base` is a good default for Polish; `medium` is meaningfully better on financial terms but ~4× slower. |
