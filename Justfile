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

# Run the full ingestion pipeline: scrape blogs + download PDFs + embed into Qdrant
# First run takes 30–90 min. Safe to re-run — already-indexed chunks are skipped.
ingest:
    bash scripts/ingest_all.sh

# Scrape blog sources only (inwestomat.eu + marciniwuc.com)
ingest-blogs:
    {{python}} ingest/scrape_blogs.py --source inwestomat_blog
    {{python}} ingest/scrape_blogs.py --source marciniwuc_blog

# Download government PDFs only (podatki.gov.pl, KNF, ISAP, BGK)
ingest-pdfs:
    {{python}} ingest/download_pdfs.py --source podatki_gov_pl
    {{python}} ingest/download_pdfs.py --source isap_ustawa_pit
    {{python}} ingest/download_pdfs.py --source isap_ustawa_ike_ikze

# Embed all raw chunks into Qdrant (run after scraping; skips already-indexed chunks)
embed:
    {{python}} ingest/embed_and_store.py

# Scrape and preview a single article without ingesting (useful for debugging scrapers)
scrape-url url:
    {{python}} ingest/scrape_blogs.py --url {{url}}

# ── Status ────────────────────────────────────────────────────────────────────

# Show chunk counts per source in the Qdrant collection
status:
    {{python}} scripts/status.py

# List indexed domains with document and chunk counts
sources:
    {{python}} scripts/sources.py

# Check whether a URL is already indexed in Qdrant
# Usage: just check-url https://inwestomat.eu/ike-przewodnik/
check-url url:
    {{python}} scripts/check_url.py {{url}}

# ── Smoke tests ───────────────────────────────────────────────────────────────

# Run all smoke tests in sequence
smoke: smoke-retrieval smoke-grade smoke-generate smoke-graph

# Test hybrid retrieval (Qdrant dense + BM25 + RRF) — no LLM calls
smoke-retrieval:
    {{python}} scripts/smoke_retrieval.py

# Test the grader LLM (Qwen2.5-7B / GPT-4o-mini) — verifies JSON score output
smoke-grade:
    {{python}} scripts/smoke_grade.py

# Test the generator LLM (Qwen2.5-32B / GPT-4o) — verifies structured answer output
smoke-generate:
    {{python}} scripts/smoke_generate.py

# Run one question end-to-end through the full agent graph
smoke-graph:
    {{python}} scripts/smoke_graph.py

# ── Run ───────────────────────────────────────────────────────────────────────

# Generate a visual diagram of the agent graph and open it
graph:
    {{python}} scripts/graph.py
    open /tmp/finfortress_graph.png

# Start the Streamlit demo UI at http://localhost:8501
ui:
    streamlit run app/streamlit_app.py

# Start the FastAPI backend at http://localhost:8000 (hot reload enabled)
api:
    uvicorn api.main:app --reload --port 8000
