#!/usr/bin/env bash
# Full ingestion pipeline — runs all scrapers concurrently, then embeds.
# Usage: bash scripts/ingest_all.sh

set -e
cd "$(dirname "$0")/.."

LOGS=data/logs
mkdir -p "$LOGS"

echo "=== FinFortress ingestion pipeline ==="
echo "Logs: $LOGS/"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — scrape blogs + download PDFs concurrently
# ---------------------------------------------------------------------------
echo "[1/3] Scraping blogs and downloading PDFs..."

python ingest/scrape_blogs.py --source inwestomat_blog  > "$LOGS/scrape_inwestomat.log"  2>&1 &
PID_INWEST=$!

python ingest/scrape_blogs.py --source marciniwuc_blog  > "$LOGS/scrape_marciniwuc.log"  2>&1 &
PID_MARCIN=$!

python ingest/download_pdfs.py --source isap_ustawa_pit      > "$LOGS/pdf_isap_pit.log"      2>&1 &
PID_PIT=$!

python ingest/download_pdfs.py --source isap_ustawa_ike_ikze > "$LOGS/pdf_isap_ike_ikze.log" 2>&1 &
PID_IKE=$!

echo "  inwestomat_blog  (pid $PID_INWEST) → $LOGS/scrape_inwestomat.log"
echo "  marciniwuc_blog  (pid $PID_MARCIN) → $LOGS/scrape_marciniwuc.log"
echo "  isap_ustawa_pit  (pid $PID_PIT)    → $LOGS/pdf_isap_pit.log"
echo "  isap_ustawa_ike_ikze (pid $PID_IKE) → $LOGS/pdf_isap_ike_ikze.log"
echo ""
echo "  Waiting for all to finish..."

wait $PID_INWEST && echo "  ✓ inwestomat done" || echo "  ✗ inwestomat FAILED (check log)"
wait $PID_MARCIN && echo "  ✓ marciniwuc done" || echo "  ✗ marciniwuc FAILED (check log)"
wait $PID_PIT    && echo "  ✓ isap_pit done"   || echo "  ✗ isap_pit FAILED (check log)"
wait $PID_IKE    && echo "  ✓ isap_ike done"   || echo "  ✗ isap_ike FAILED (check log)"

# ---------------------------------------------------------------------------
# Step 2 — count raw records
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Raw record counts:"
for f in data/raw/*.jsonl; do
    count=$(wc -l < "$f")
    echo "  $(basename $f): $count records"
done

# ---------------------------------------------------------------------------
# Step 3 — embed everything into Qdrant
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Embedding into Qdrant..."
python ingest/embed_and_store.py 2>&1 | tee "$LOGS/embed.log"

echo ""
echo "=== Done. Checking Qdrant ==="
python -c "
from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
load_dotenv('.env')
c = QdrantClient(os.getenv('QDRANT_URL', 'http://localhost:6333'))
info = c.get_collection(os.getenv('QDRANT_COLLECTION', 'polish_finance'))
print(f'  points: {info.points_count}')
print(f'  status: {info.status}')
"
