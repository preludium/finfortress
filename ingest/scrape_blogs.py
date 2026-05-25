"""
Scrape blog_html entries from sources_manifest.json.

Outputs one JSONL file per source to data/raw/{source_id}.jsonl.
Each line: {url, source_id, source, author, title, date, year, language,
            content_type, scraped_at, page_content}

Usage:
    python ingest/scrape_blogs.py                            # all blog_html sources
    python ingest/scrape_blogs.py --source inwestomat_blog   # one source
    python ingest/scrape_blogs.py --url https://...          # single article (test)
    python ingest/scrape_blogs.py --dry-run                  # discover URLs, skip fetch
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ingest.utils.cleaner import extract_article_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

MANIFEST_PATH = ROOT / "data" / "sources_manifest.json"
RAW_DIR = ROOT / "data" / "raw"
BOT_UA = "finfortress-bot/1.0 (personal RAG project, non-commercial)"
POLITE_DELAY = 1.5
REQUEST_TIMEOUT = 15

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": BOT_UA})

# Sitemap locations to probe, in order
SITEMAP_CANDIDATES = [
    "/wp-sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap.xml",
    "/feed",  # RSS fallback
]

_skip_pattern = os.getenv("SCRAPER_SKIP_PATTERN", "")
URL_SKIP_RE = re.compile(_skip_pattern) if _skip_pattern else None


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

_robots_cache: dict[str, RobotFileParser] = {}


def _robots(base_url: str) -> RobotFileParser:
    if base_url not in _robots_cache:
        log.info("Fetching robots.txt for %s", base_url)
        rp = RobotFileParser()
        robots_url = urljoin(base_url, "/robots.txt")
        rp.set_url(robots_url)
        try:
            resp = _get(robots_url)
            if resp:
                # Python's RobotFileParser treats empty "Disallow:" as
                # "Disallow: " (empty prefix matches everything → blocks all).
                # The spec says empty Disallow means "allow all" — strip them.
                lines = [
                    ln for ln in resp.text.splitlines()
                    if not (ln.strip().lower().startswith("disallow:") and ln.split(":", 1)[1].strip() == "")
                ]
                rp.parse(lines)
            else:
                rp.read()
        except Exception as exc:
            log.warning("robots.txt fetch failed for %s: %s", base_url, exc)
        _robots_cache[base_url] = rp
    return _robots_cache[base_url]


def can_fetch(url: str) -> bool:
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    return _robots(base).can_fetch(BOT_UA, url)


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


# ---------------------------------------------------------------------------
# Sitemap / URL discovery
# ---------------------------------------------------------------------------

def _parse_sitemap_xml(xml_text: str, base_url: str, _depth: int = 0, _seen: set | None = None) -> list[str]:
    """Extract <loc> URLs from a sitemap or sitemap index. Recurses into sub-sitemaps."""
    if _depth > 3:
        log.warning("Sitemap recursion depth > 3 — stopping")
        return []
    if _seen is None:
        _seen = set()

    urls: list[str] = []
    # Strip BOM, leading whitespace, and HTML comments injected before XML declaration
    import re as _re
    xml_clean = xml_text.lstrip("﻿").strip()
    xml_clean = _re.sub(r"<!--.*?-->", "", xml_clean, flags=_re.DOTALL).strip()
    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError as exc:
        log.warning("Sitemap XML parse error: %s", exc)
        return urls

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tag = root.tag.lower()

    if "sitemapindex" in tag:
        sub_sitemaps = root.findall("sm:sitemap", ns)
        log.info("Sitemap index: %d sub-sitemaps found", len(sub_sitemaps))
        for i, sitemap in enumerate(sub_sitemaps, 1):
            loc = sitemap.findtext("sm:loc", namespaces=ns)
            if loc:
                loc = loc.strip()
                if loc in _seen:
                    log.warning("  Sitemap cycle detected: %s — skipping", loc)
                    continue
                _seen.add(loc)
                log.info("  Fetching sub-sitemap [%d/%d]: %s", i, len(sub_sitemaps), loc)
                resp = _get(loc)
                if resp:
                    time.sleep(0.5)
                    sub_urls = _parse_sitemap_xml(resp.text, base_url, _depth=_depth + 1, _seen=_seen)
                    log.info("  → %d URLs", len(sub_urls))
                    urls.extend(sub_urls)
    else:
        for url_el in root.findall("sm:url", ns):
            loc = url_el.findtext("sm:loc", namespaces=ns)
            if loc:
                urls.append(loc.strip())

    return urls


def _parse_rss(xml_text: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls
    for item in root.findall(".//item"):
        link = item.findtext("link")
        if link:
            urls.append(link.strip())
    return urls


def discover_article_urls(base_url: str) -> list[str]:
    """Try sitemap candidates in order; return all article URLs found."""
    for path in SITEMAP_CANDIDATES:
        url = urljoin(base_url, path)
        log.info("Probing sitemap candidate: %s", url)
        resp = _get(url)
        if resp is None:
            log.info("  → not found, trying next")
            continue
        ct = resp.headers.get("Content-Type", "")
        if "xml" in ct or path.endswith(".xml"):
            urls = _parse_sitemap_xml(resp.text, base_url)
        elif "rss" in ct or path == "/feed":
            log.info("  → RSS feed found")
            urls = _parse_rss(resp.text)
        else:
            log.info("  → unexpected content-type '%s', skipping", ct)
            continue
        if urls:
            log.info("Discovered %d URLs via %s", len(urls), path)
            return urls
    log.warning("No sitemap found for %s", base_url)
    return []


# ---------------------------------------------------------------------------
# Per-article metadata extraction
# ---------------------------------------------------------------------------

def _og(soup: BeautifulSoup, prop: str) -> str:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return ""


def _extract_title(soup: BeautifulSoup) -> str:
    title = _og(soup, "og:title")
    if title:
        return title
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return soup.title.get_text(strip=True) if soup.title else ""


def _extract_date(soup: BeautifulSoup) -> str:
    """Return ISO date string 'YYYY-MM-DD' or empty string."""
    raw = (
        _og(soup, "article:published_time")
        or _og(soup, "article:modified_time")
        or _og(soup, "og:updated_time")
    )
    if not raw:
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            raw = time_tag["datetime"]
    if not raw:
        return ""
    try:
        dt = dateparser.parse(raw)
        return dt.strftime("%Y-%m-%d") if dt else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Scrape single article
# ---------------------------------------------------------------------------

def scrape_article(url: str, source_entry: dict) -> dict | None:
    """Fetch, clean, and return a record for one article. None if failed."""
    if not can_fetch(url):
        log.warning("robots.txt disallows: %s", url)
        return None

    resp = _get(url)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = extract_article_text(resp.text)
    if not text or len(text) < 200:
        log.debug("Too short or empty after clean: %s", url)
        return None

    title = _extract_title(soup)
    date_str = _extract_date(soup)
    year = int(date_str[:4]) if len(date_str) >= 4 else None

    record = {
        "url": url,
        "source_id": source_entry["id"],
        "source": urlparse(url).netloc,
        "author": source_entry.get("author", ""),
        "title": title,
        "date": date_str,
        "year": year,
        "language": source_entry.get("language", "pl"),
        "content_type": source_entry.get("type", "blog_html"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "page_content": text,
    }
    if topics := source_entry.get("topics"):
        record["topics"] = topics
    return record


# ---------------------------------------------------------------------------
# Scrape one manifest source
# ---------------------------------------------------------------------------

def scrape_source(
    entry: dict,
    dry_run: bool = False,
    limit: int | None = None,
    out_path_override: Path | None = None,
) -> int:
    """Scrape articles for one source entry. Returns count of new records."""
    source_id = entry["id"]
    out_path = out_path_override or RAW_DIR / f"{source_id}.jsonl"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Load already-scraped URLs to skip duplicates
    seen_urls: set[str] = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen_urls.add(json.loads(line)["url"])
                except Exception:
                    pass

    urls = discover_article_urls(entry["url"])
    if not urls:
        log.error("No URLs found for %s", source_id)
        return 0

    # Filter to same-domain URLs (avoid following external links in sitemaps)
    base_host = urlparse(entry["url"]).netloc
    urls = [u for u in urls if urlparse(u).netloc == base_host]

    # Skip non-article URLs via global regex + optional per-source patterns
    extra_skip = entry.get("url_skip_patterns", [])
    extra_re = re.compile("|".join(re.escape(p) for p in extra_skip)) if extra_skip else None
    before_skip = len(urls)
    urls = [
        u for u in urls
        if not (URL_SKIP_RE and URL_SKIP_RE.search(u))
        and not (extra_re and extra_re.search(u))
    ]
    skipped_patterns = before_skip - len(urls)
    if skipped_patterns:
        log.info("%s: skipped %d non-article URLs", source_id, skipped_patterns)

    new_urls = [u for u in urls if u not in seen_urls]
    if limit:
        new_urls = new_urls[:limit]
    log.info("%s: %d total, %d new (limit=%s)", source_id, len(urls), len(new_urls), limit or "none")

    if dry_run:
        for u in new_urls:
            log.info("  [dry-run] %s", u)
        return len(new_urls)

    title_filter = entry.get("title_filter", False)
    filter_keywords = [kw.lower() for kw in entry.get("topics", [])] if title_filter else []

    count = 0
    skipped_filter = 0
    total_new = len(new_urls)
    with out_path.open("a", encoding="utf-8") as fh:
        for i, url in enumerate(new_urls, 1):
            log.info("[%d/%d] fetching: %s", i, total_new, url)
            record = scrape_article(url, entry)
            if record:
                if filter_keywords:
                    title_lower = record.get("title", "").lower()
                    if not any(kw in title_lower for kw in filter_keywords):
                        log.debug("  ✗ title filter skip: %r", record["title"][:60])
                        skipped_filter += 1
                        time.sleep(POLITE_DELAY)
                        continue
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                log.info("  ✓ saved  title=%r  date=%s  len=%d chars",
                         record["title"][:60], record["date"], len(record["page_content"]))
            else:
                log.warning("  ✗ skipped (empty/short after clean)")
            time.sleep(POLITE_DELAY)

    if skipped_filter:
        log.info("%s: title filter skipped %d articles", source_id, skipped_filter)

    log.info("%s: wrote %d new records → %s", source_id, count, out_path)
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_manifest() -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape blog HTML sources.")
    parser.add_argument("--source", help="Scrape one source by manifest id")
    parser.add_argument("--url", help="Scrape a single article URL (test mode)")
    parser.add_argument("--dry-run", action="store_true", help="Discover URLs only, no fetch")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to scrape per source (dev/test)")
    args = parser.parse_args()

    if args.url:
        # Test mode: no manifest needed
        entry = {"id": "manual", "author": "unknown", "language": "pl", "type": "blog_html"}
        record = scrape_article(args.url, entry)
        if record:
            print(json.dumps(record, ensure_ascii=False, indent=2))
            print("\n--- page_content preview (first 300 chars) ---")
            print(record["page_content"][:300])
        else:
            log.error("Failed to scrape %s", args.url)
        return

    manifest = _load_manifest()
    blog_entries = [e for e in manifest if e.get("type") == "blog_html"]

    if args.source:
        entries = [e for e in blog_entries if e["id"] == args.source]
        if not entries:
            log.error("Source '%s' not found in manifest", args.source)
            sys.exit(1)
    else:
        entries = blog_entries

    total = 0
    for entry in entries:
        total += scrape_source(entry, dry_run=args.dry_run, limit=args.limit)

    log.info("Done. Total new records: %d", total)


if __name__ == "__main__":
    main()
