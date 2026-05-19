# FinFortress — AI assistant context

## What this project is

Polish personal finance RAG assistant. Answers questions about Polish taxes, mortgages, ETFs, IKE/IKZE retirement accounts, and government bonds — grounded in indexed Polish sources, not LLM training data.

Core differentiator: **self-correcting agentic loop** (LangGraph). After retrieval a grader LLM scores each chunk for relevance and detects temporal mismatches. Low-confidence retrievals trigger query rewrite + re-retrieval before generating an answer. Max 2 rewrites, then graceful fallback.

User profile (`data/user_profile.md`) is injected into every generate prompt — agent answers in context of user's specific financial situation without requiring repetition in each message.

## LLM stack

Default: **oMLX local** (Apple Silicon). OpenAI as alternative — same code, just swap env vars.

| Role | Default model | OpenAI alternative |
|---|---|---|
| Generator | `Qwen2.5-32B-Instruct-4bit` via oMLX | `gpt-4o` |
| Grader | `Qwen2.5-7B-Instruct-4bit` via oMLX | `gpt-4o-mini` |
| Embeddings | `intfloat/multilingual-e5-large` (local, always) | — |

See `docs/local-llm-setup.md` for oMLX setup and model tiers by RAM.

## Project structure (actual files)

```
finfortress/
├── Justfile                   # task runner — use `just` for all commands
├── .env.example               # copy to .env, fill keys
├── docker-compose.yml         # Qdrant service
│
├── agent/
│   ├── graph.py               # LangGraph graph + routing logic
│   ├── state.py               # AgentState TypedDict + INITIAL_STATE
│   ├── profile.py             # load_profile() + format_profile_block()
│   ├── nodes/
│   │   ├── classify.py        # sets query_type + needs_live_data
│   │   ├── fetch_live.py      # calls NBP / obligacje tools if needed
│   │   ├── retrieve.py        # hybrid dense+BM25 retrieval, RRF fusion
│   │   ├── grade.py           # per-chunk relevance scoring + stale detection
│   │   ├── rewrite.py         # rewrites query on grade failure
│   │   ├── generate.py        # build_generate_node(profile_block="")
│   │   └── fallback.py        # graceful no-answer with source suggestions
│   ├── tools/
│   │   ├── nbp_rates.py       # live WIBOR/WIRON + exchange rates
│   │   └── obligacje_rates.py # live bond rates (HTML scrape, no API)
│   └── prompts/               # classify.py, grade.py, rewrite.py, generate.py
│
├── ingest/
│   ├── scrape_blogs.py        # inwestomat.eu + marciniwuc.com (sitemap → article)
│   ├── download_pdfs.py       # KNF, NBP, podatki.gov.pl, BGK (PyMuPDF→pdfplumber→OCR)
│   ├── embed_and_store.py     # chunk + embed + upsert to Qdrant (idempotent)
│   └── utils/
│       ├── chunker.py         # RecursiveCharacterTextSplitter wrapper
│       ├── cleaner.py         # HTML article body extractor
│       ├── embeddings.py      # E5Embeddings with query:/passage: prefixes
│       └── hasher.py          # SHA-256 dedup hash
│
├── api/
│   ├── main.py                # FastAPI + CORS + startup (loads graph + BM25)
│   ├── schemas.py             # QueryRequest, QueryResponse
│   └── routes/
│       ├── query.py           # POST /query (sync) + POST /query/stream (SSE)
│       ├── health.py          # GET /health
│       └── sources.py         # GET /sources
│
├── app/
│   └── streamlit_app.py       # Chat UI + sidebar profile viewer
│
├── scripts/
│   ├── ingest_all.sh          # full pipeline: scrape (parallel) → embed
│   ├── smoke_retrieval.py     # test hybrid retrieval, no LLM calls
│   ├── smoke_grade.py         # test grader JSON output
│   ├── smoke_generate.py      # test generator structured output
│   ├── smoke_graph.py         # end-to-end graph run on sample question
│   ├── status.py              # chunk counts per source in Qdrant
│   ├── sources.py             # indexed domains with doc + chunk counts
│   ├── check_url.py           # check if URL already indexed
│   └── graph.py               # generate agent graph diagram PNG
│
├── data/
│   ├── sources_manifest.json  # source registry (committed)
│   ├── user_profile.example.md # template — copy to user_profile.md
│   └── user_profile.md        # GITIGNORED — personal financial data
│
└── docs/
    ├── getting-started.md     # install, configure, ingest, run
    ├── api.md                 # POST /query, POST /query/stream, SSE events
    ├── configuration.md       # all env vars with defaults
    ├── architecture.md        # design decisions with rationale
    ├── data-sources.md        # every source + trust hierarchy
    ├── local-llm-setup.md     # oMLX + model tiers by RAM
    ├── implementation-notes.md # gotchas (e5 prefixes, Qdrant volume, etc.)
    ├── evaluation.md          # RAGAS methodology
    └── assets/agent_graph.png # LangGraph diagram (regenerate: just graph)
```

## Running locally

Use `just` for all commands. Run `just` to list all recipes.

```bash
just install          # uv sync
just qdrant           # docker compose up -d
just ingest           # full pipeline (30-90 min first run)
just smoke            # all smoke tests
just ui               # streamlit run app/streamlit_app.py
just api              # uvicorn api.main:app --reload --port 8000
just status           # chunk counts per source
just sources          # indexed domains summary
just check-url <url>  # is this URL already indexed?
just graph            # generate + open agent graph diagram
```

## User profile

`data/user_profile.md` — free-text markdown. User writes their financial situation in natural language. No schema, no required fields. Loaded once at agent startup, injected verbatim into every generate prompt.

```bash
cp data/user_profile.example.md data/user_profile.md
# write your situation, restart app
```

File is gitignored. Sidebar in Streamlit shows loaded profile summary.

## Knowledge base (current state)

```
inwestomat.eu      334 docs   26,478 chunks   (ETF, IKE/IKZE, Belka, pasywne)
marciniwuc.com     776 docs   35,180 chunks   (kredyty, planowanie, ubezpieczenia)
isap.sejm.gov.pl     2 docs    1,350 chunks   (ustawa PIT, ustawa IKE/IKZE)
─────────────────────────────────────────────
TOTAL             1112 docs   63,008 chunks
```

Missing (not yet indexed): podatki.gov.pl, KNF, obligacjeskarbowe.pl, NBP reports, UOKiK, BGK.

## Key design decisions

- **multilingual-e5-large**: OpenAI ada-002 degrades on Polish financial vocab. e5-large runs locally, free, understands Polish. MUST add `query:`/`passage:` prefixes — custom E5Embeddings wrapper handles this.
- **Hybrid retrieval (dense + BM25, RRF)**: dense finds synonyms, BM25 finds exact product codes (COI0325, WIRON 3M). RRF merges without calibrating scores. BM25 40%, dense 60%.
- **Grading threshold 0.6**: below this, retrieved chunks don't support accurate answers → rewrite.
- **Max 2 rewrites**: prevents infinite loops. After 2 failures: if avg_grade still ≥ threshold → generate with low confidence; else → fallback.
- **Grader = small model**: grader fires 6× per query. Using 32B for it would be 5-10× more expensive. 7B is sufficient for binary relevance classification.
- **Never index rate data**: WIBOR/WIRON/bond rates change daily. Always fetch live via tools. Indexing creates stale data grader would catch anyway.
- **Free-text profile over Pydantic schema**: LLM understands natural language better than deserialized structs. No schema maintenance, no enum values to remember, user can add nuance that doesn't fit any field.

## AgentState

```python
class AgentState(TypedDict):
    question:        str
    current_query:   Optional[str]   # None = use question; set by rewrite node
    query_type:      str             # factual|calculation|comparison|advice
    needs_live_data: bool
    context:         List[Document]
    avg_grade:       float
    needs_rewrite:   bool
    stale_data:      bool
    rewrite_count:   int             # max 2
    live_data:       Optional[str]
    answer:          Optional[str]
    citations:       Optional[List[Citation]]
    confidence:      Optional[str]   # high|medium|low
    disclaimer:      Optional[str]   # non-None for advice queries
    give_up:         bool
```

## What NOT to do

- Do not commit `.env`, `data/user_profile.md`, `qdrant_data/`, `data/raw/` — see `.gitignore`
- Do not embed full articles as single vectors — chunk first (512 tokens, 64 overlap)
- Do not use English-only embeddings — Polish vocab degrades badly
- Do not index NBP/obligacje rates — always fetch live
- Do not skip grading — retrieval alone unreliable for financial Q&A
- Do not answer "advice" queries without disclaimer

## Open GitHub issues (next steps)

| # | Title | Priority |
|---|---|---|
| #1 | feat: conversation memory across turns | High — needed for strategy sessions |
| #2 | feat: financial calculator tool | High — agent can't do arithmetic |
| #3 | feat: live ETF price fetching | Medium — profile has positions, no prices |
| #4 | feat: strategy session mode | Medium — depends on #1 + #2 |
| #5 | chore: index remaining gov sources | Medium — podatki.gov.pl, KNF, etc. |
| #6 | fix: filter tag/category pages from scraper | Low — 43 stub pages in index |

Repo: https://github.com/preludium/finfortress
