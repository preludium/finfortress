"""
Extract and ingest local PDF files into the pipeline.

Usage:
    python scripts/ingest_local_pdfs.py data/raw/*.pdf
    python scripts/ingest_local_pdfs.py path/to/doc.pdf --source my_source --title "Doc title"

Output: data/raw/local_pdfs.jsonl (appended, dedup by filename)
Then run: python ingest/embed_and_store.py --source local_pdfs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ingest.download_pdfs import extract_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

OUT_PATH = ROOT / "data" / "raw" / "local_pdfs.jsonl"


def _load_seen() -> set[str]:
    if not OUT_PATH.exists():
        return set()
    seen = set()
    for line in OUT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            seen.add(json.loads(line)["url"])
        except Exception:
            pass
    return seen


def ingest_pdf(pdf_path: Path, source_id: str, title: str, author: str, date: str) -> int:
    url = f"file://{pdf_path.resolve()}"
    pages, meta_date, method = extract_pages(pdf_path)
    used_date = date or meta_date or ""
    year = int(used_date[:4]) if len(used_date) >= 4 else None
    scraped_at = datetime.now(timezone.utc).isoformat()

    records = []
    for i, text in enumerate(pages):
        text = text.strip()
        if len(text) < 50:
            continue
        records.append({
            "url":               url,
            "source_id":         source_id,
            "source":            source_id,
            "author":            author,
            "title":             title or pdf_path.stem.replace("_", " "),
            "date":              used_date,
            "year":              year,
            "language":          "pl",
            "content_type":      "pdf_local",
            "scraped_at":        scraped_at,
            "page":              i + 1,
            "page_total":        len(pages),
            "extraction_method": method,
            "page_content":      text,
        })

    if records:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUT_PATH.open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.info("%s: %d pages extracted via %s → local_pdfs.jsonl", pdf_path.name, len(records), method)
    else:
        log.warning("%s: no extractable text found", pdf_path.name)

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="PDF file paths")
    parser.add_argument("--source", default="local_pdfs", help="Source ID tag (default: local_pdfs)")
    parser.add_argument("--title",  default="", help="Override title for all files")
    parser.add_argument("--author", default="", help="Author/institution name")
    parser.add_argument("--date",   default="", help="Publication date YYYY-MM-DD")
    args = parser.parse_args()

    seen = _load_seen()
    total = 0

    for f in args.files:
        pdf_path = Path(f)
        if not pdf_path.exists():
            log.warning("File not found: %s", pdf_path)
            continue
        if pdf_path.suffix.lower() != ".pdf":
            log.warning("Not a PDF, skipping: %s", pdf_path)
            continue
        url = f"file://{pdf_path.resolve()}"
        if url in seen:
            log.info("Already indexed: %s", pdf_path.name)
            continue
        total += ingest_pdf(pdf_path, args.source, args.title, args.author, args.date)

    log.info("Done. %d page records written. Now run: just embed --source local_pdfs", total)


if __name__ == "__main__":
    main()
