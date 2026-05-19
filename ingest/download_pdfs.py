"""
Download and extract text from PDF sources in sources_manifest.json.

Extraction chain per PDF:
  Level 1: PyMuPDF (fitz)    — fast, handles most PDFs
  Level 2: pdfplumber        — better on complex layouts and tables
  Level 3: pytesseract OCR   — for scanned government documents

Output: data/raw/{source_id}.jsonl — one record per page, same schema as scrape_blogs.py.

Usage:
    python ingest/download_pdfs.py                          # all pdf_gov + legal_text sources
    python ingest/download_pdfs.py --source podatki_gov_pl  # one source
    python ingest/download_pdfs.py --url https://...        # single PDF (test mode)
    python ingest/download_pdfs.py --crawl https://...      # crawl page for PDF links
    python ingest/download_pdfs.py --dry-run                # list PDFs without downloading
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

MANIFEST_PATH = ROOT / "data" / "sources_manifest.json"
RAW_DIR       = ROOT / "data" / "raw"
CACHE_DIR     = ROOT / "data" / "raw" / "_pdf_cache"
BOT_UA        = "finfortress-bot/1.0 (personal RAG project, non-commercial)"
POLITE_DELAY  = 1.0
REQUEST_TIMEOUT = 30
MIN_PAGE_TEXT = 50   # chars — below this, page is likely scanned

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": BOT_UA})

# ---------------------------------------------------------------------------
# Known PDF URLs per source
# These are stable government documents. Add more as needed.
# ---------------------------------------------------------------------------

KNOWN_PDFS: dict[str, list[dict]] = {
    "isap_ustawa_pit": [
        # DocDetails pages — script resolves the actual PDF link
        {"doc_page": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU19910800350",
         "title": "Ustawa o podatku dochodowym od osób fizycznych", "date": "1991-07-26"},
    ],
    "isap_ustawa_ike_ikze": [
        {"doc_page": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20041161205",
         "title": "Ustawa o indywidualnych kontach emerytalnych oraz indywidualnych kontach zabezpieczenia emerytalnego", "date": "2004-05-20"},
    ],
    # Add direct PDF URLs for other sources as you locate them:
    # "podatki_gov_pl": [
    #     {"url": "https://www.podatki.gov.pl/...", "title": "PIT-38 broszura informacyjna", "date": "2024-01-01"},
    # ],
    # "nbp_reports": [
    #     {"url": "https://nbp.pl/...", "title": "Raport o inflacji", "date": "2025-03-01"},
    # ],
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> requests.Response | None:
    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


def _download_pdf(url: str) -> Path | None:
    """Download PDF to cache dir. Returns local path or None on failure."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.-]", "_", urlparse(url).path.split("/")[-1]) or "doc.pdf"
    dest = CACHE_DIR / safe_name
    if dest.exists():
        log.info("  cached: %s", dest.name)
        return dest
    resp = _get(url)
    if resp is None:
        return None
    if "pdf" not in resp.headers.get("Content-Type", "").lower() and not url.lower().endswith(".pdf"):
        log.warning("  URL does not appear to be a PDF: %s", url)
    dest.write_bytes(resp.content)
    log.info("  downloaded: %s (%.1f KB)", dest.name, len(resp.content) / 1024)
    return dest


# ---------------------------------------------------------------------------
# ISAP special handling — DocDetails page → PDF link
# ---------------------------------------------------------------------------

def _resolve_isap_pdf(doc_page_url: str) -> str | None:
    """Fetch ISAP DocDetails page and extract the unified text PDF link."""
    resp = _get(doc_page_url)
    if resp is None:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    # ISAP has download links like: download.xsp/...Lj.pdf (unified/consolidated text)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "download.xsp" in href and href.endswith(".pdf"):
            # Prefer unified text (Lj suffix) over original (O suffix)
            if "Lj" in href or "lj" in href:
                return urljoin(doc_page_url, href)
    # fallback: any download.xsp PDF
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "download.xsp" in href and href.endswith(".pdf"):
            return urljoin(doc_page_url, href)
    log.warning("No PDF link found on ISAP page: %s", doc_page_url)
    return None


# ---------------------------------------------------------------------------
# PDF crawler — finds all .pdf links on a page
# ---------------------------------------------------------------------------

def crawl_pdf_links(page_url: str) -> list[str]:
    resp = _get(page_url)
    if resp is None:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            found.append(urljoin(page_url, href))
    log.info("Found %d PDF links on %s", len(found), page_url)
    return found


# ---------------------------------------------------------------------------
# Text extraction — three-level fallback chain
# ---------------------------------------------------------------------------

def _parse_pdf_date(raw: str) -> str:
    """Parse PDF metadata date 'D:20240115...' → 'YYYY-MM-DD'."""
    if not raw:
        return ""
    if raw.startswith("D:"):
        raw = raw[2:]
    try:
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    except Exception:
        return ""


def _date_from_url(url: str) -> str:
    """Extract 4-digit year from URL as fallback date."""
    m = re.search(r"(20\d{2})", url)
    return f"{m.group(1)}-01-01" if m else ""


def _try_pymupdf(pdf_path: Path) -> tuple[list[str], str]:
    """Returns (pages_text_list, metadata_date)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        date = _parse_pdf_date(doc.metadata.get("creationDate", ""))
        pages = [page.get_text() for page in doc]
        doc.close()
        return pages, date
    except Exception as exc:
        log.debug("PyMuPDF failed: %s", exc)
        return [], ""


def _try_pdfplumber(pdf_path: Path) -> tuple[list[str], str]:
    try:
        import pdfplumber
        pages = []
        date = ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            raw_date = (pdf.metadata or {}).get("CreationDate", "")
            date = _parse_pdf_date(raw_date)
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return pages, date
    except Exception as exc:
        log.debug("pdfplumber failed: %s", exc)
        return [], ""


def _try_ocr(pdf_path: Path) -> tuple[list[str], str]:
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io
        doc = fitz.open(str(pdf_path))
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang="pol")
            pages.append(text)
        doc.close()
        log.info("  OCR extracted %d pages", len(pages))
        return pages, ""
    except Exception as exc:
        log.warning("OCR failed: %s", exc)
        return [], ""


def extract_pages(pdf_path: Path, url: str = "") -> tuple[list[str], str, str]:
    """Extract page texts from PDF. Returns (pages, date, method)."""
    pages, date = _try_pymupdf(pdf_path)
    if pages and any(len(p.strip()) >= MIN_PAGE_TEXT for p in pages):
        return pages, date, "pymupdf"

    log.info("  PyMuPDF insufficient — trying pdfplumber")
    pages, date = _try_pdfplumber(pdf_path)
    if pages and any(len(p.strip()) >= MIN_PAGE_TEXT for p in pages):
        return pages, date, "pdfplumber"

    log.info("  pdfplumber insufficient — trying OCR")
    pages, date = _try_ocr(pdf_path)
    return pages, date, "ocr"


# ---------------------------------------------------------------------------
# Process one PDF → JSONL records
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_url: str,
    source_entry: dict,
    known_meta: dict | None = None,
) -> list[dict]:
    """Download + extract one PDF. Returns list of per-page records."""
    known_meta = known_meta or {}
    log.info("Processing: %s", pdf_url)

    pdf_path = _download_pdf(pdf_url)
    if pdf_path is None:
        return []

    pages, meta_date, method = extract_pages(pdf_path, pdf_url)
    log.info("  extracted %d pages via %s", len(pages), method)

    date = known_meta.get("date") or meta_date or _date_from_url(pdf_url)
    year = int(date[:4]) if len(date) >= 4 else None
    title = known_meta.get("title", pdf_path.stem.replace("_", " "))
    scraped_at = datetime.now(timezone.utc).isoformat()

    records = []
    total = len(pages)
    for i, page_text in enumerate(pages):
        text = page_text.strip()
        if len(text) < MIN_PAGE_TEXT:
            continue
        records.append({
            "url":          pdf_url,
            "source_id":    source_entry["id"],
            "source":       urlparse(pdf_url).netloc,
            "author":       source_entry.get("author", ""),
            "title":        title,
            "date":         date,
            "year":         year,
            "language":     source_entry.get("language", "pl"),
            "content_type": source_entry.get("type", "pdf_gov"),
            "scraped_at":   scraped_at,
            "page":         i + 1,
            "page_total":   total,
            "extraction_method": method,
            "page_content": text,
        })

    log.info("  → %d non-empty pages saved", len(records))
    return records


# ---------------------------------------------------------------------------
# Process one manifest source
# ---------------------------------------------------------------------------

def process_source(entry: dict, dry_run: bool = False) -> int:
    source_id = entry["id"]
    out_path  = RAW_DIR / f"{source_id}.jsonl"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    known = KNOWN_PDFS.get(source_id, [])
    if not known:
        log.warning("%s: no known PDF URLs configured — skipping (add to KNOWN_PDFS or use --crawl)", source_id)
        return 0

    seen_urls: set[str] = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen_urls.add(json.loads(line)["url"])
                except Exception:
                    pass

    count = 0
    with out_path.open("a", encoding="utf-8") as fh:
        for item in known:
            # ISAP: resolve DocDetails → actual PDF URL
            if "doc_page" in item:
                log.info("%s: resolving ISAP page %s", source_id, item["doc_page"])
                pdf_url = _resolve_isap_pdf(item["doc_page"])
                if not pdf_url:
                    continue
                time.sleep(POLITE_DELAY)
            else:
                pdf_url = item["url"]

            if pdf_url in seen_urls:
                log.info("%s: already processed %s", source_id, pdf_url)
                continue

            if dry_run:
                log.info("  [dry-run] %s", pdf_url)
                count += 1
                continue

            records = process_pdf(pdf_url, entry, known_meta=item)
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += len(records)
            time.sleep(POLITE_DELAY)

    log.info("%s: wrote %d page records → %s", source_id, count, out_path)
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_manifest() -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and extract PDF sources.")
    parser.add_argument("--source",  help="Process one source by manifest id")
    parser.add_argument("--url",     help="Download and extract a single PDF URL (test mode)")
    parser.add_argument("--crawl",   help="Crawl a page for PDF links and list them")
    parser.add_argument("--dry-run", action="store_true", help="List PDFs without downloading")
    args = parser.parse_args()

    manifest = _load_manifest()
    pdf_entries = [e for e in manifest if e.get("type") in ("pdf_gov", "legal_text")]

    if args.crawl:
        links = crawl_pdf_links(args.crawl)
        for link in links:
            print(link)
        return

    if args.url:
        entry = {"id": "manual", "author": "unknown", "language": "pl", "type": "pdf_gov"}
        records = process_pdf(args.url, entry)
        if records:
            print(f"\n{len(records)} pages extracted")
            print(f"Date: {records[0]['date']} | Method: {records[0]['extraction_method']}")
            print(f"\nPage 1 preview:\n{records[0]['page_content'][:400]}")
        return

    if args.source:
        entries = [e for e in pdf_entries if e["id"] == args.source]
        if not entries:
            log.error("Source '%s' not found in manifest", args.source)
            sys.exit(1)
    else:
        entries = pdf_entries

    total = 0
    for entry in entries:
        total += process_source(entry, dry_run=args.dry_run)

    log.info("Done. Total page records: %d", total)


if __name__ == "__main__":
    main()
