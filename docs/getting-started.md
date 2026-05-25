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

## Set up your personal profile

Without a profile FinFortress answers general questions about Polish finance — correct and cited, but generic. With a profile it knows your specific situation and adapts every answer to it.

```bash
cp data/user_profile.example.md data/user_profile.md
```

Open `data/user_profile.md` and describe your financial situation in free-form text — no required fields, no schema. The agent understands natural language.

```markdown
## Sytuacja dochodowa
- Wiek: 35 lat
- Forma zatrudnienia: JDG z podatkiem liniowym 19%
- Dochód roczny brutto: ok. 144 000 zł (netto ~9 000 zł/mies)

## Kredyt hipoteczny
Saldo 400 000 zł, WIRON 3M + 1,5% marży, rata ok. 2 200 zł/mies.

## IKE (otwarte czerwiec 2021)
- VWCE: 12 szt., śr. cena 112,50 EUR, pierwsza transakcja marzec 2022

## IKZE
- COI0325: 30 obligacji COI, zakup marzec 2023, oprocentowanie rok 1: 6,55%

## Inne inwestycje
- IWDA: 5 szt., śr. cena 85 EUR, zakup styczeń 2024
- Gotówka: ok. 5 000 zł

## Ogólnie
Horyzont 25 lat, cel: emerytura, profil ryzyka: umiarkowany, poduszka 6 miesięcy.
```

Write anything — a job change next year, a spouse with a separate IKE, a planned home purchase. There is no schema constraining what you can include.

### What changes

The profile is injected verbatim into the generator prompt for every query:

> **Bez profilu:** "ETF w IKE pozwala uniknąć podatku Belki od zysków kapitałowych..."
>
> **Z profilem (JDG liniowy):** "Przy JDG liniowym IKZE daje Ci odliczenie od dochodu opodatkowanego 19% — to ~1 430 zł rocznie korzyści podatkowych przy maksymalnej wpłacie. Biorąc pod uwagę kredyt WIRON+1,5% i COI0325 w IKZE, pytanie czy realny koszt kredytu bije efektywną stopę obligacji po uwzględnieniu tej tarczy..."

Generic questions ("what is the IKE limit in 2025?") are answered the same regardless of the profile. Personal questions ("should I overpay my mortgage or buy ETFs?") get an answer grounded in your specific situation without needing to repeat it every message.

### Keeping the profile up to date

The profile is loaded once at agent startup. After editing `data/user_profile.md`, restart the app or click **Clear cache** in the Streamlit menu. The sidebar shows a preview of the loaded profile.

`data/user_profile.md` is in `.gitignore` — it will never be committed to the repository.

---

## Conversation memory

Conversation memory is on by default. Within a single Streamlit session, the agent remembers previous messages and can answer follow-up questions without repeating context:

> "What is the IKE limit?" → "23 472 zł in 2025..."
> "And for IKZE?" → agent knows you're still talking about contribution limits

History is persisted to `data/memory.sqlite` (auto-created on first run, gitignored). Each Streamlit session gets its own `thread_id` — closing the browser and reopening starts a fresh conversation.

For the API, pass `thread_id` from a previous response to continue a conversation. See [`docs/api.md`](api.md#conversation-memory) for details.

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

## Add your sources

All sources live in `data/my_sources/` — fully gitignored so nothing about your data appears in the repository. Three JSON manifests control what gets indexed:

| Manifest | What | How handled |
|---|---|---|
| `data/my_sources/pdfs.json` | Local PDFs | Text extracted via PyMuPDF → pdfplumber → OCR |
| `data/my_sources/blogs.json` | Full-site blog crawls | Entire sitemap indexed |
| `data/my_sources/urls.json` | Individual articles | Single page scraped |

Copy the templates to get started:

```bash
cp data/my_sources/pdfs.example.json data/my_sources/pdfs.json
cp data/my_sources/blogs.example.json data/my_sources/blogs.json
cp data/my_sources/urls.example.json data/my_sources/urls.json
```

**`pdfs.json`** — drop the PDF in `data/my_sources/`, add an entry with metadata:

```json
[
  {
    "file": "Umowa_kredytowa.pdf",
    "title": "Umowa kredytowa PKO BP",
    "author": "PKO BP",
    "date": "2024-03-01",
    "topics": ["kredyt hipoteczny"],
    "notes": "Moja umowa, marża 1.5%, WIRON 3M"
  }
]
```

PDFs without a matching entry are still indexed — they just get filename-derived title and no author or topics.

**`blogs.json`** — base URL of the blog, scraper auto-discovers the sitemap:

```json
[
  {
    "url": "https://exampleblog.pl/",
    "author": "Author Name",
    "topics": ["ETF", "IKE", "IKZE"],
    "notes": "Main ETF blog"
  }
]
```

**`urls.json`** — individual articles:

```json
[
  {
    "url": "https://example.com/kredyt-hipoteczny-poradnik/",
    "author": "Author Name",
    "topics": ["kredyt hipoteczny"],
    "notes": "Good overpayment explainer"
  }
]
```

`topics` is stored in Qdrant per chunk — available for filtering at retrieval time. `notes` is for your reference only, not stored in Qdrant.

---

## Run ingestion

```bash
just ingest-sources
```

This processes everything in `data/my_sources/` (PDFs, URLs, blog crawls) and embeds into Qdrant. First run takes 30–90 minutes depending on how many articles your blogs have. Already-indexed items are skipped on re-runs.

Preview what would be processed without writing anything:

```bash
just ingest-sources-dry
```

### Ingestion is idempotent

Each chunk is hashed with `SHA-256(url + chunk_index + content)`. On subsequent runs, chunks already in Qdrant are skipped. It's safe to re-run `just ingest-sources` — it will not duplicate data.

### Fixing extraction errors

After processing, each PDF and individual URL is saved as an editable `.txt` file in `data/my_sources/extracted/`:

```
data/my_sources/extracted/
  Umowa_kredytowa.txt          ← extracted PDF text, one --- Page N --- per page
  example_com_article.txt      ← scraped article text
```

If OCR produced garbled text or the scraper missed content:

1. Open the `.txt` file and fix the text directly
2. Delete the corresponding `data/raw/<name>.jsonl` to clear the old indexed version
3. Run `just ingest-sources` — reads the corrected `.txt` instead of re-extracting

Blog crawls (from `blogs.json`) do not produce editable `.txt` files — they have too many articles to manage individually.

### Test a single article (without ingesting)

```bash
just scrape-url https://example.com/some-article/
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
| `Collection not found` | Qdrant empty — ingestion not run | Run `just ingest-sources` |
| Slow first startup | e5-large model downloading (~2.2 GB) | Wait — cached after first download |
| Empty retrieval results | e5 prefix missing | Check `ingest/utils/embeddings.py` |
| Qdrant data lost on restart | Container started without volume | Always use `docker compose up` |
| `KeyError: 'rewrite_count'` | AgentState not initialised | Pass `{**INITIAL_STATE, "question": ...}` |
| Memory not persisting across restarts | `data/memory.sqlite` missing or corrupt | Delete the file and restart — it is recreated automatically |
| Grader JSON parse error | LLM returned markdown fences | Strip fences before `json.loads()` |
| SSE not streaming through nginx | Missing response header | Add `X-Accel-Buffering: no` |

See [`docs/implementation-notes.md`](implementation-notes.md) for the full error table and detailed explanations.
