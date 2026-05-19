# FinFortress — AI assistant context

## What this project is

A Polish personal finance RAG (Retrieval-Augmented Generation) assistant for non-technical users. It answers questions about Polish taxes, mortgages, ETFs, retirement accounts (IKE/IKZE), and government bonds (obligacje skarbowe) — grounded in authoritative Polish sources, not generic LLM knowledge.

The core differentiator is an **agentic self-correcting loop** (LangGraph): after retrieval, a grader LLM scores each chunk for relevance and detects temporal mismatches (e.g. a 2022 WIBOR document answering a question about current rates). Low-confidence retrievals trigger a query rewrite and re-retrieval before generating an answer.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Agent orchestration | LangGraph | Stateful graph with conditional retry loop |
| LLM | OpenAI GPT-4o (main), GPT-4o-mini (grader) | Cost-efficient grading with smaller model |
| Embeddings | `intfloat/multilingual-e5-large` | Handles Polish financial vocabulary correctly |
| Vector store | Qdrant | Persistent, Docker-native, metadata filtering |
| Keyword search | BM25 (rank-bm25) | Hybrid retrieval alongside dense vectors |
| Retrieval fusion | Reciprocal Rank Fusion | Merges dense + sparse ranked lists |
| Evaluation | RAGAS | Faithfulness, answer relevance, context recall |
| API | FastAPI | Streaming SSE endpoint |
| Demo UI | Streamlit | Deployable to Streamlit Cloud for public URL |
| Observability | LangSmith | Traces every node, LLM call, and retrieved chunk |

## Project structure

```
finfortress/
├── CLAUDE.md                  # this file
├── README.md
├── pyproject.toml
├── .env.example               # copy to .env, fill in keys
├── .gitignore
│
├── docs/
│   ├── architecture.md        # design decisions and rationale
│   ├── data-sources.md        # all indexed sources with metadata
│   └── evaluation.md          # RAGAS benchmark methodology
│
├── data/
│   ├── sources_manifest.json  # index of sources (committed)
│   ├── eval/
│   │   └── test_questions.json # golden Q&A set (committed)
│   ├── raw/                   # downloaded HTML/PDFs (gitignored)
│   ├── chunks/                # processed JSONL chunks (gitignored)
│   └── snapshots/             # daily API snapshots (gitignored)
│
├── ingest/
│   ├── scrape_blogs.py        # inwestomat.eu + marciniwuc.com
│   ├── download_pdfs.py       # KNF, NBP, podatki.gov.pl, BGK
│   ├── fetch_excel.py         # obligacje rates, NBP rate tables
│   ├── transcribe_videos.py   # yt-dlp + Whisper
│   ├── process_chunks.py      # clean, chunk, tag metadata
│   ├── embed_and_store.py     # embed → Qdrant (idempotent)
│   └── utils/
│       ├── chunker.py
│       ├── cleaner.py
│       └── hasher.py
│
├── agent/
│   ├── graph.py               # LangGraph graph definition
│   ├── state.py               # AgentState TypedDict
│   ├── nodes/
│   │   ├── classify.py        # query classification node
│   │   ├── retrieve.py        # hybrid retrieval node
│   │   ├── grade.py           # context grading node
│   │   ├── rewrite.py         # query rewrite node
│   │   ├── generate.py        # answer generation node
│   │   └── fallback.py        # graceful no-answer node
│   ├── tools/
│   │   ├── nbp_rates.py       # live NBP API tool
│   │   └── obligacje_rates.py # live bond rates tool
│   └── prompts/
│       ├── classify.py
│       ├── grade.py
│       ├── rewrite.py
│       └── generate.py
│
├── api/
│   ├── main.py                # FastAPI app
│   ├── routes/
│   │   ├── query.py           # POST /query (streaming SSE)
│   │   ├── sources.py         # GET /sources
│   │   └── health.py          # GET /health
│   └── schemas.py             # Pydantic request/response models
│
├── app/
│   └── streamlit_app.py       # Streamlit demo UI
│
├── eval/
│   ├── run_ragas.py           # RAGAS evaluation runner
│   └── results/               # benchmark output (gitignored)
│
├── scripts/
│   ├── smoke_test.py          # verify retrieval quality manually
│   ├── weekly_update.py       # incremental re-index
│   └── daily_snapshot.py      # snapshot live API data
│
└── tests/
    ├── test_nodes.py           # unit tests per LangGraph node
    ├── test_retrieval.py
    └── test_api.py
```

## Environment variables

```bash
# LLM
OPENAI_API_KEY=

# Vector store
QDRANT_URL=http://localhost:6333          # or Qdrant Cloud URL
QDRANT_COLLECTION=polish_finance
QDRANT_API_KEY=                           # only needed for Qdrant Cloud

# Embeddings (HuggingFace — needed if using gated model)
HUGGINGFACE_TOKEN=

# Observability
LANGCHAIN_API_KEY=                        # LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=finfortress

# Ingestion
OPENAI_WHISPER_MODEL=base                 # or medium for better Polish
```

## Running locally

```bash
# 1. Start Qdrant
docker run -d -p 6333:6333 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run ingestion (first time — takes hours)
python ingest/scrape_blogs.py
python ingest/download_pdfs.py
python ingest/process_chunks.py
python ingest/embed_and_store.py

# 4. Smoke test retrieval
python scripts/smoke_test.py

# 5a. Run Streamlit demo
streamlit run app/streamlit_app.py

# 5b. Run FastAPI backend
uvicorn api.main:app --reload --port 8000
```

## Key design decisions

See `docs/architecture.md` for full rationale. See `docs/implementation-notes.md`
for practical gotchas, common errors, and non-obvious implementation details —
read this before starting each major component. Quick reference:

- **multilingual-e5-large over OpenAI ada-002**: OpenAI embeddings degrade on Polish financial vocabulary (WIBOR, ulga mieszkaniowa, kredyt hipoteczny). e5-large runs locally, free, and understands Polish.
- **Qdrant over Chroma**: Chroma is easier to start but struggles with metadata filtering at scale. Qdrant's payload filtering is essential for temporal mismatch detection.
- **Grading threshold 0.6**: Empirically tuned on the golden test set. Below this, retrieved chunks consistently fail to support accurate answers.
- **Max 2 rewrites**: Prevents infinite retry loops. After 2 rewrites, the agent returns a graceful fallback with source suggestions.
- **GPT-4o-mini for grading**: The grader doesn't need full reasoning capability — just relevance scoring. Mini is 10x cheaper and fast enough.
- **Live API calls for NBP/obligacje rates**: Rate data changes daily. Indexing it would make it stale within hours. Tools are always called fresh at query time.

## Data sources

See `docs/data-sources.md` for full list. Primary sources:

| Source | Type | Update frequency |
|---|---|---|
| inwestomat.eu | Blog HTML | Weekly |
| marciniwuc.com | Blog HTML + video transcripts | Weekly |
| knf.gov.pl / inwestoredukacja.pl | Gov HTML + PDF | Monthly |
| podatki.gov.pl | PDF | Yearly (+ on law change) |
| isap.sejm.gov.pl | Legal text | On law change |
| obligacjeskarbowe.pl | HTML + Excel | Monthly (rates) |
| nbp.pl | HTML + API | Daily (live tool) |
| uokik.gov.pl | HTML | Quarterly |
| bgk.pl | PDF | On program change |

## Agent state shape

```python
class AgentState(TypedDict):
    question:      str
    query_type:    str           # "factual" | "calculation" | "comparison" | "advice"
    needs_live_data: bool
    context:       List[Document]
    avg_grade:     float
    needs_rewrite: bool
    stale_data:    bool
    rewrite_count: int           # max 2
    live_data:     Optional[str]
    answer:        Optional[str]
    citations:     Optional[List[Citation]]
    confidence:    Optional[str] # "high" | "medium" | "low"
    disclaimer:    Optional[str] # non-None when query_type == "advice"
    give_up:       bool
```

## Chunk metadata schema

Every chunk stored in Qdrant carries:

```json
{
  "source": "inwestomat.eu",
  "author": "Mateusz Samołyk",
  "url": "https://inwestomat.eu/...",
  "title": "ETF w IKE — kompletny przewodnik",
  "date": "2024-11-22",
  "year": 2024,
  "scraped_at": "2025-05-17T10:00:00Z",
  "content_type": "blog_article",
  "language": "pl",
  "chunk_index": 3,
  "chunk_total": 12,
  "topics": ["IKE", "ETF", "Belka"]
}
```

## What NOT to do

- Do not commit `.env`, `qdrant_data/`, `data/raw/`, `data/chunks/` — see `.gitignore`
- Do not embed full articles as single vectors — chunk first
- Do not use English-only embedding models — Polish vocabulary degrades badly
- Do not index NBP/obligacje rates — always fetch live at query time
- Do not skip the grading step — retrieval alone is not reliable enough for financial Q&A
- Do not answer "advice" queries (should I invest in X?) without a disclaimer
