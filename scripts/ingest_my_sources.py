"""
Ingest personal sources from data/my_sources/.

Reads three JSON manifests (all gitignored):
  data/my_sources/pdfs.json   — local PDFs with metadata
  data/my_sources/blogs.json  — full-site blog crawls
  data/my_sources/urls.json   — individual article URLs

Copy the example templates to get started:
  cp data/my_sources/pdfs.example.json data/my_sources/pdfs.json
  cp data/my_sources/blogs.example.json data/my_sources/blogs.json
  cp data/my_sources/urls.example.json data/my_sources/urls.json

Extracted text (PDFs + individual URLs) is saved to data/my_sources/extracted/
as editable .txt files. Edit them to fix OCR errors or garbled scraping, then
delete the corresponding data/raw/<name>.jsonl and re-run to re-embed.

Output:
  data/raw/<pdf_stem>.jsonl    — one file per PDF
  data/raw/<blog_domain>.jsonl — one file per blog
  data/raw/my_sources.jsonl    — all individual URLs

Usage:
    python scripts/ingest_my_sources.py
    python scripts/ingest_my_sources.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

MY_DIR        = ROOT / "data" / "my_sources"
EXTRACTED_DIR = MY_DIR / "extracted"
RAW_DIR       = ROOT / "data" / "raw"
ARTICLES_OUT  = RAW_DIR / "my_sources.jsonl"


def _read_manifest(filename: str) -> list[dict]:
    path = MY_DIR / filename
    if not path.exists():
        log.info("%s not found — skipping", filename)
        return []
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            seen.add(json.loads(line)["url"])
        except Exception:
            pass
    return seen


def _append_records(records: list[dict], out_path: Path) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _source_id_from_path(p: Path) -> str:
    return re.sub(r"[^\w]", "_", p.stem).strip("_").lower()


def _source_id_from_url(url: str) -> str:
    netloc = urlparse(url).netloc
    return re.sub(r"[^\w]", "_", netloc).strip("_")


def _url_slug(url: str) -> str:
    parsed = urlparse(url)
    slug = (parsed.netloc + parsed.path).rstrip("/")
    return re.sub(r"[^\w]", "_", slug).strip("_")[:120]


# ---------------------------------------------------------------------------
# Extracted .txt helpers
# ---------------------------------------------------------------------------

def _txt_path_pdf(pdf_path: Path) -> Path:
    return EXTRACTED_DIR / f"{pdf_path.stem}.txt"


def _txt_path_url(url: str) -> Path:
    return EXTRACTED_DIR / f"{_url_slug(url)}.txt"


def _save_pdf_txt(txt_path: Path, pages: list[str]) -> None:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, page in enumerate(pages, 1):
        text = page.strip()
        if text:
            lines.append(f"--- Page {i} ---")
            lines.append(text)
            lines.append("")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Saved extracted text → %s", txt_path.relative_to(ROOT))


def _load_pdf_txt(txt_path: Path) -> list[str]:
    """Split .txt back into per-page strings."""
    content = txt_path.read_text(encoding="utf-8")
    pages: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        if re.match(r"^--- Page \d+ ---$", line.strip()):
            if current:
                pages.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        pages.append("\n".join(current).strip())
    return [p for p in pages if p]


def _save_url_txt(txt_path: Path, text: str) -> None:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(text, encoding="utf-8")
    log.info("Saved extracted text → %s", txt_path.relative_to(ROOT))


# ---------------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------------

def _ingest_pdfs(dry_run: bool) -> int:
    from ingest.download_pdfs import extract_pages

    entries: list[dict] = _read_manifest("pdfs.json")
    meta_by_file = {e["file"]: e for e in entries if "file" in e}

    pdfs = sorted(MY_DIR.glob("*.pdf"))
    log.info("PDFs: %d file(s) in data/my_sources/", len(pdfs))
    total = 0

    for pdf_path in pdfs:
        source_id = _source_id_from_path(pdf_path)
        out_path  = RAW_DIR / f"{source_id}.jsonl"
        url       = f"file://{pdf_path.resolve()}"
        txt_path  = _txt_path_pdf(pdf_path)
        meta      = meta_by_file.get(pdf_path.name, {})

        if url in _load_seen(out_path):
            log.info("Already indexed: %s", pdf_path.name)
            continue

        if dry_run:
            status = "has extracted .txt" if txt_path.exists() else "will extract"
            log.info("[dry-run] PDF: %s (%s) → %s.jsonl  topics=%s",
                     pdf_path.name, status, source_id, meta.get("topics", []))
            total += 1
            continue

        if txt_path.exists():
            log.info("%s: using existing extracted text from %s",
                     pdf_path.name, txt_path.relative_to(ROOT))
            pages = _load_pdf_txt(txt_path)
            method = "txt_override"
        else:
            pages_raw, meta_date_extracted, method = extract_pages(pdf_path)
            pages = [p.strip() for p in pages_raw if p.strip()]
            _save_pdf_txt(txt_path, pages)

        date  = meta.get("date") or ""
        year  = int(date[:4]) if len(date) >= 4 else None
        scraped_at = datetime.now(timezone.utc).isoformat()

        records = []
        for i, text in enumerate(pages):
            if len(text) < 50:
                continue
            rec = {
                "url":               url,
                "source_id":         source_id,
                "source":            source_id,
                "author":            meta.get("author", ""),
                "title":             meta.get("title") or pdf_path.stem.replace("_", " "),
                "date":              date,
                "year":              year,
                "language":          "pl",
                "content_type":      "pdf_local",
                "scraped_at":        scraped_at,
                "page":              i + 1,
                "page_total":        len(pages),
                "extraction_method": method,
                "page_content":      text,
            }
            if topics := meta.get("topics"):
                rec["topics"] = topics
            records.append(rec)

        if records:
            _append_records(records, out_path)
            log.info("%s: %d pages → %s.jsonl  (edit: %s)",
                     pdf_path.name, len(records), source_id,
                     txt_path.relative_to(ROOT))
        else:
            log.warning("%s: no extractable text", pdf_path.name)

        total += len(records)

    return total


# ---------------------------------------------------------------------------
# Full-site blog crawls
# ---------------------------------------------------------------------------

def _ingest_blogs(dry_run: bool) -> int:
    from ingest.scrape_blogs import scrape_source

    entries = _read_manifest("blogs.json")
    log.info("Blog crawls: %d entry(ies) in blogs.json", len(entries))
    total = 0

    for entry in entries:
        url       = entry.get("url", "")
        source_id = _source_id_from_url(url)
        out_path  = RAW_DIR / f"{source_id}.jsonl"

        source_entry = {
            "id":       source_id,
            "url":      url,
            "author":   entry.get("author", ""),
            "language": "pl",
            "type":     "blog_html",
            "topics":   entry.get("topics", []),
        }

        if dry_run:
            log.info("[dry-run] blog: %s → %s.jsonl  author=%r topics=%s",
                     url, source_id, entry.get("author", ""), entry.get("topics", []))
            total += 1
            continue

        count = scrape_source(source_entry, dry_run=False, out_path_override=out_path)
        log.info("Blog %s: %d new articles → %s.jsonl", url, count, source_id)
        total += count

    return total


# ---------------------------------------------------------------------------
# Individual article URLs
# ---------------------------------------------------------------------------

def _ingest_urls(dry_run: bool) -> int:
    from ingest.scrape_blogs import scrape_article

    entries = _read_manifest("urls.json")
    log.info("URLs: %d entry(ies) in urls.json", len(entries))
    seen  = _load_seen(ARTICLES_OUT)
    total = 0

    for entry in entries:
        url = entry.get("url", "")
        if not url:
            continue

        txt_path = _txt_path_url(url)

        if url in seen:
            log.info("Already indexed: %s", url)
            continue

        if dry_run:
            status = "has extracted .txt" if txt_path.exists() else "will scrape"
            log.info("[dry-run] URL: %s (%s)  topics=%s",
                     url, status, entry.get("topics", []))
            total += 1
            continue

        source_entry = {
            "id":       "my_sources",
            "author":   entry.get("author", ""),
            "language": "pl",
            "type":     "blog_html",
            "topics":   entry.get("topics", []),
        }

        if txt_path.exists():
            log.info("Using existing extracted text: %s", txt_path.relative_to(ROOT))
            text = txt_path.read_text(encoding="utf-8").strip()
            record = {
                "url":          url,
                "source_id":    "my_sources",
                "source":       urlparse(url).netloc,
                "author":       entry.get("author", ""),
                "title":        "",
                "date":         "",
                "year":         None,
                "language":     "pl",
                "content_type": "blog_html",
                "scraped_at":   datetime.now(timezone.utc).isoformat(),
                "page_content": text,
            }
            if topics := entry.get("topics"):
                record["topics"] = topics
        else:
            try:
                record = scrape_article(url, source_entry)
            except Exception as exc:
                log.warning("Scrape failed for %s: %s", url, exc)
                continue

            if not record:
                log.warning("No content extracted from %s", url)
                continue

            _save_url_txt(txt_path, record.get("page_content", ""))

        _append_records([record], ARTICLES_OUT)
        log.info("Indexed: %s (%d chars)  (edit: %s)",
                 url, len(record.get("page_content", "")),
                 txt_path.relative_to(ROOT))
        total += 1

    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    MY_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    total += _ingest_pdfs(args.dry_run)
    total += _ingest_blogs(args.dry_run)
    total += _ingest_urls(args.dry_run)

    if args.dry_run:
        log.info("[dry-run] %d item(s) would be processed", total)
    else:
        log.info("Done. %d record(s) written.", total)
        log.info("Extracted text files: %s", EXTRACTED_DIR.relative_to(ROOT))
        log.info("To fix OCR errors: edit .txt → delete data/raw/<name>.jsonl → re-run")


if __name__ == "__main__":
    main()
