# FinSense PL

A Polish personal finance RAG assistant for non-technical users. Answers questions about Polish taxes, mortgages, ETFs, retirement accounts, and government bonds — grounded in authoritative Polish sources with source citations and confidence scoring.

## Why this exists

Generic LLMs (ChatGPT, Gemini) handle Polish financial questions poorly. They have no reliable knowledge of current WIBOR/WIRON rates, yearly IKE/IKZE contribution limits, Belka tax rules, or BGK housing programs. They hallucinate specifics confidently.

This assistant is grounded in indexed Polish sources (KNF, NBP, podatki.gov.pl, inwestomat.eu, marciniwuc.com) and uses a self-correcting agent loop to verify retrieval quality before generating an answer.

## Architecture

```
Ingestion (offline, scheduled)
  Sources → Loaders → Chunker → Embedder → Qdrant

Query (online, per request)
  Question → Classify → Retrieve → Grade → [Rewrite →] Generate → Answer + Citations
```

The self-correcting loop: after retrieval, a grader LLM scores each chunk for relevance (0–1) and detects temporal mismatches. Low-confidence retrievals trigger a query rewrite and re-retrieval before generation. Maximum 2 retries, then a graceful fallback with source suggestions.

See [`docs/architecture.md`](docs/architecture.md) for full design rationale.

## Stack

- **Agent**: LangGraph (stateful graph with conditional retry loop)
- **LLM**: GPT-4o (generation), GPT-4o-mini (grading)
- **Embeddings**: `intfloat/multilingual-e5-large` — handles Polish financial vocabulary
- **Vector store**: Qdrant with hybrid retrieval (dense + BM25, RRF fusion)
- **API**: FastAPI with streaming SSE
- **Demo UI**: Streamlit
- **Evaluation**: RAGAS (faithfulness ≥ 0.85, context recall ≥ 0.80)
- **Observability**: LangSmith

## Data sources

| Source | Type | Topics |
|---|---|---|
| inwestomat.eu | Blog | ETFs, IKE/IKZE, Belka tax |
| marciniwuc.com | Blog + video | Mortgages, retirement planning |
| KNF / inwestoredukacja.pl | Gov HTML | IKE/IKZE rules, fund regulation |
| podatki.gov.pl | PDF | PIT, capital gains, PIT-38 |
| isap.sejm.gov.pl | Legal text | Ustawa o PIT, IKE/IKZE |
| NBP | Reports + live API | WIBOR/WIRON, inflation |
| obligacjeskarbowe.pl | HTML + live | COI/EDO bond rates |
| UOKiK | Gov HTML | Mortgage consumer rights |
| BGK | PDF | Housing programs |

Current WIBOR/WIRON and bond rates are fetched live at query time — never indexed.

See [`docs/data-sources.md`](docs/data-sources.md) for full source list with metadata.

## Getting started

```bash
# Clone
git clone https://github.com/your-username/finsense-pl
cd finsense-pl

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Start Qdrant
docker run -d -p 6333:6333 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant

# Run initial ingestion (takes hours on first run)
python ingest/scrape_blogs.py
python ingest/download_pdfs.py
python ingest/process_chunks.py
python ingest/embed_and_store.py

# Verify retrieval quality
python scripts/smoke_test.py

# Run demo UI
streamlit run app/streamlit_app.py

# Or run API
uvicorn api.main:app --reload --port 8000
```

## Evaluation

```bash
# Run RAGAS benchmark
python eval/run_ragas.py

# Check against thresholds
python eval/check_thresholds.py --input eval/results/latest.json
```

RAGAS evaluation runs automatically on every PR to main. Results are posted as PR comments. Merges that drop faithfulness below 0.85 or context recall below 0.80 are blocked.

See [`docs/evaluation.md`](docs/evaluation.md) for methodology.

## Project structure

```
finsense-pl/
├── CLAUDE.md              # AI assistant context (read by Claude Code)
├── docs/                  # Architecture, data sources, evaluation
├── data/
│   ├── sources_manifest.json   # Indexed sources index (committed)
│   └── eval/test_questions.json # Golden test set (committed)
├── ingest/                # Scraping and ingestion scripts
├── agent/                 # LangGraph agent nodes and graph
├── api/                   # FastAPI backend
├── app/                   # Streamlit demo
├── eval/                  # RAGAS evaluation runner
├── scripts/               # Smoke test, weekly update, snapshots
└── tests/                 # Unit and integration tests
```

## Design decisions

Key decisions with rationale in [`docs/architecture.md`](docs/architecture.md):

- **multilingual-e5-large** over OpenAI ada-002: Polish vocabulary, free, local inference, no data sent to embedding API
- **Qdrant** over Chroma: payload filtering required for temporal mismatch detection
- **Grading threshold 0.6**: tuned on golden test set
- **GPT-4o-mini for grading**: 10x cheaper than GPT-4o, sufficient for relevance classification
- **Live API calls for rates**: never index daily-changing data

## License

MIT
