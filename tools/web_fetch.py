"""Web fetching tool for Mara — fetch and extract readable content from URLs.

Use cases:
- Competitor UX audits (Rapha, Endura, PNS, Castelli, Café du Cycliste, etc.)
- Analysing RYZON pages from a user's perspective
- Fetching PDPs, collection pages, checkout flows, landing pages

Returns cleaned text content, stripping nav/script/style noise.
Not suitable for JavaScript-heavy SPAs — returns server-rendered HTML only.
"""

import re
import requests
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

NOISE_TAGS = ["script", "style", "nav", "footer", "head", "noscript", "iframe", "svg"]


def fetch_page(url: str, max_chars: int = 8000, timeout: int = 15) -> dict:
    """
    Fetch a single web page and return cleaned text for UX analysis.

    Args:
        url:       Full URL to fetch (must include https://)
        max_chars: Truncate output at this length (default 8000)
        timeout:   Request timeout in seconds

    Returns:
        {
            "url":     str,
            "title":   str,
            "content": str,   # cleaned readable text
            "status":  int,   # HTTP status code (0 = request failed)
            "error":   str | None
        }
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # Extract <title>
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).strip() if title_m else ""

        # Remove noisy tags entirely
        for tag in NOISE_TAGS:
            html = re.sub(
                rf"<{tag}[^>]*>.*?</{tag}>", "", html,
                flags=re.DOTALL | re.IGNORECASE,
            )

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + " … [truncated]"

        return {"url": url, "title": title, "content": text, "status": resp.status_code, "error": None}

    except requests.exceptions.Timeout:
        return {"url": url, "title": "", "content": "", "status": 0, "error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        return {"url": url, "title": "", "content": "", "status": e.response.status_code, "error": str(e)}
    except Exception as e:
        return {"url": url, "title": "", "content": "", "status": 0, "error": str(e)}


def fetch_multiple(urls: list[str], max_chars: int = 5000) -> list[dict]:
    """
    Fetch multiple pages for side-by-side UX comparison.
    Useful for competitive audits across 3–5 competitors.

    Args:
        urls:      List of URLs to fetch
        max_chars: Per-page character limit (lower default to stay manageable)
    """
    return [fetch_page(url, max_chars=max_chars) for url in urls]
