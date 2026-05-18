from __future__ import annotations

from bs4 import BeautifulSoup, Tag

_ARTICLE_SELECTORS = ["article", ".entry-content", ".post-content"]

_STRIP_TAGS = [
    "nav",
    "header",
    "footer",
    "aside",
    "script",
    "style",
    "noscript",
    "iframe",
]

_STRIP_CLASSES = [
    "sidebar",
    "widget",
    "cookie",
    "cookie-banner",
    "cookie-notice",
    "comment",
    "comments",
    "comment-section",
    "related-posts",
    "newsletter",
    "social-share",
    "breadcrumb",
    "pagination",
]


def extract_article_text(html: str) -> str:
    """Extract article body text from raw HTML. Returns empty string if no article found."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in _STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    for css_class in _STRIP_CLASSES:
        for el in soup.find_all(class_=css_class):
            el.decompose()

    article: Tag | None = None
    for selector in _ARTICLE_SELECTORS:
        article = soup.select_one(selector)
        if article:
            break

    if article is None:
        return ""

    text = article.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
