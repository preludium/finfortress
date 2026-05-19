# Getting started

## Prerequisites

- Python 3.11+
- Docker (for Qdrant)
- One of:
  - **Apple Silicon Mac with 32–48 GB unified memory** — for local LLMs via oMLX (recommended)
  - **OpenAI API key** — for cloud LLMs (works on any machine)

---

## Install

```bash
git clone https://github.com/your-username/finfortress
cd finfortress
uv sync          # or: pip install -e .
```

---

## Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your LLM config. Pick one option:

### Option A — local LLMs via oMLX (default)

Runs entirely locally on Apple Silicon. No data sent to external APIs.

See [`docs/local-llm-setup.md`](local-llm-setup.md) for oMLX installation and model download.

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=omlx-<your-key>       # from http://localhost:8000/admin → API Keys
LLM_MODEL=Qwen2.5-32B-Instruct-4bit
GRADER_MODEL=Qwen2.5-7B-Instruct-4bit
```

### Option B — OpenAI

```bash
OPENAI_API_KEY=sk-...
# LLM_MODEL and GRADER_MODEL default to gpt-4o and gpt-4o-mini
```

Both options use the same Qdrant and embedding configuration. Embeddings always run locally via `sentence-transformers` — they are not sent to any API regardless of which LLM option you choose.

All other settings (`GRADE_THRESHOLD`, `MAX_REWRITES`, `QDRANT_URL`, etc.) are pre-filled with reasonable defaults. See [`docs/configuration.md`](configuration.md) for the full reference.

---

## Start Qdrant

```bash
docker compose up -d
```

Starts Qdrant at `localhost:6333` with data persisted to `./qdrant_data/`. Never run Qdrant without the volume mount — data is lost on container stop.

Verify it's running:

```bash
curl http://localhost:6333/healthz
```

---

## Run ingestion

Ingestion scrapes all sources and embeds them into Qdrant. On first run this takes 30–90 minutes depending on connection speed. Sources are scraped concurrently; embedding runs sequentially after.

```bash
bash scripts/ingest_all.sh
```

Logs go to `data/logs/`. Watch progress:

```bash
tail -f data/logs/scrape_inwestomat.log
tail -f data/logs/embed.log
```

When done, the script prints the final point count from Qdrant. Expect ~15,000–25,000 vectors depending on how many PDF pages download successfully.

### Ingesting individual sources

If you want to index a specific source only:

```bash
# Blog sources
python ingest/scrape_blogs.py --source inwestomat_blog
python ingest/scrape_blogs.py --source marciniwuc_blog

# PDF / government sources
python ingest/download_pdfs.py --source podatki_gov_pl
python ingest/download_pdfs.py --source isap_ustawa_pit
python ingest/download_pdfs.py --source isap_ustawa_ike_ikze

# After scraping, embed everything not yet in Qdrant
python ingest/embed_and_store.py
```

Source IDs are defined in `data/sources_manifest.json`.

### Ingestion is idempotent

Each chunk is hashed with `SHA-256(url + chunk_index + content)`. On subsequent runs, chunks already in Qdrant are skipped. It's safe to re-run `ingest_all.sh` — it won't duplicate data.

### Test a single article (without ingesting)

```bash
python ingest/scrape_blogs.py --url https://inwestomat.eu/ike-przewodnik/
```

Prints the scraped record as JSON including a 300-character content preview. Useful for verifying the scraper handles a specific article correctly.

---

## Verify retrieval

Before starting the UI, run the smoke tests to confirm the pipeline works end-to-end.

```bash
python scripts/smoke_retrieval.py   # hybrid retrieval on 5 known questions
python scripts/smoke_grade.py       # grader on known good/bad chunks
python scripts/smoke_generate.py    # generation with fixed context
python scripts/smoke_graph.py       # full graph run on a sample question
```

If `smoke_retrieval.py` returns footer text, cookie banners, or nav links as top results, the HTML cleaner needs attention — don't proceed to the UI until retrieval is clean.

---

## Run the demo UI

```bash
streamlit run app/streamlit_app.py
```

Opens at `http://localhost:8501`.

On first run, `multilingual-e5-large` (~2.2 GB) downloads to `~/.cache/huggingface/`. This is a one-time download — subsequent starts load from cache and are fast.

The agent graph (e5-large + BM25 index) is built once at startup and cached across Streamlit reruns via `@st.cache_resource`.

---

## Run the API

```bash
uvicorn api.main:app --reload --port 8000
```

The API starts at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

On startup the API builds the agent graph (same as the Streamlit UI). Expect 10–30 seconds before the first request is ready.

Test with curl:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Jaki jest limit wpłat na IKE w 2025 roku?"}'
```

For SSE streaming:

```bash
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question": "Czym różni się WIRON od WIBOR?"}' \
  --no-buffer
```

See [`docs/api.md`](api.md) for full API reference.

---

## Common setup errors

| Error | Cause | Fix |
|---|---|---|
| `Collection not found` | Qdrant empty — ingestion not run | Run `bash scripts/ingest_all.sh` |
| Slow first startup | e5-large model downloading (~2.2 GB) | Wait — cached after first download |
| Empty retrieval results | e5 prefix missing | Check `ingest/utils/embeddings.py` |
| Qdrant data lost on restart | Container started without volume | Always use `docker compose up` |
| `KeyError: 'rewrite_count'` | AgentState not initialised | Pass `{**INITIAL_STATE, "question": ...}` |
| Grader JSON parse error | LLM returned markdown fences | Strip fences before `json.loads()` |
| SSE not streaming through nginx | Missing response header | Add `X-Accel-Buffering: no` |

See [`docs/implementation-notes.md`](implementation-notes.md) for the full error table and detailed explanations.
