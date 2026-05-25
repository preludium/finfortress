# FinFortress task runner
# Install: brew install just
# Usage:   just          → list all recipes
#          just <recipe> → run a recipe

set dotenv-load := true

python := ".venv/bin/python"

# ── Default ───────────────────────────────────────────────────────────────────

# List available recipes
default:
    @just --list

# ── Dependencies & vector store ───────────────────────────────────────────────

# Install Python dependencies
install:
    uv sync

# Start Qdrant vector store (data persisted to ./qdrant_data/)
qdrant:
    docker compose up -d
    @echo "Qdrant running at http://localhost:6333"

# Stop Qdrant
qdrant-stop:
    docker compose down

# ── Profile ───────────────────────────────────────────────────────────────────
# Open your personal financial profile in the default editor

# Copy the example first: cp data/user_profile.example.md data/user_profile.md
profile:
    @test -f data/user_profile.md || (echo "No profile found. Run: cp data/user_profile.example.md data/user_profile.md" && exit 1)
    $EDITOR data/user_profile.md

# ── Ingestion ─────────────────────────────────────────────────────────────────
# Ingest all sources from data/my_sources/ and embed into Qdrant:
#   data/my_sources/*.pdf    — local PDFs
#   data/my_sources/urls.txt — individual article URLs
#   data/my_sources/blogs.txt — full-site blog crawls (entire sitemap)

# Safe to re-run — already-indexed items are skipped.
ingest-sources:
    {{ python }} scripts/ingest_my_sources.py
    {{ python }} ingest/embed_and_store.py

# Preview what would be ingested from data/my_sources/ without writing anything
ingest-sources-dry:
    {{ python }} scripts/ingest_my_sources.py --dry-run

# Embed all raw JSONL chunks into Qdrant (low-level, skips already-indexed chunks)
embed:
    {{ python }} ingest/embed_and_store.py

# Scrape and preview a single article without ingesting (useful for debugging scrapers)
scrape-url url:
    {{ python }} ingest/scrape_blogs.py --url {{ url }}

# ── Status ────────────────────────────────────────────────────────────────────

# Show chunk counts per source in the Qdrant collection
status:
    {{ python }} scripts/status.py

# List indexed domains with document and chunk counts
sources:
    {{ python }} scripts/sources.py

# Check whether a URL is already indexed in Qdrant

# Usage: just check-url https://inwestomat.eu/ike-przewodnik/
check-url url:
    {{ python }} scripts/check_url.py {{ url }}

# List all sources currently in Qdrant with chunk counts
list-sources:
    {{ python }} scripts/delete_source.py --list

# ── Smoke tests ───────────────────────────────────────────────────────────────

# Run all smoke tests in sequence
smoke: smoke-retrieval smoke-grade smoke-generate smoke-graph smoke-calculate

# Test hybrid retrieval (Qdrant dense + BM25 + RRF) — no LLM calls
smoke-retrieval:
    {{ python }} scripts/smoke_retrieval.py

# Test the grader LLM (Qwen2.5-7B / GPT-4o-mini) — verifies JSON score output
smoke-grade:
    {{ python }} scripts/smoke_grade.py

# Test the generator LLM (Qwen2.5-32B / GPT-4o) — verifies structured answer output
smoke-generate:
    {{ python }} scripts/smoke_generate.py

# Run one question end-to-end through the full agent graph
smoke-graph:
    {{ python }} scripts/smoke_graph.py

# Test financial calculators — pure unit assertions + one LLM dispatch check
smoke-calculate:
    {{ python }} scripts/smoke_calculate.py

# ── Run ───────────────────────────────────────────────────────────────────────

# Generate a visual diagram of the agent graph and open it
graph:
    {{ python }} scripts/graph.py
    open /tmp/finfortress_graph.png

# Start the Streamlit demo UI at http://localhost:8501
ui:
    streamlit run app/streamlit_app.py

# Start the FastAPI backend at http://localhost:8000 (hot reload enabled)
api:
    uvicorn api.main:app --reload --port 8000
