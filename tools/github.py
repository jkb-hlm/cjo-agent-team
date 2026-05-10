"""GitHub tools for Tessa — fetch AB test snippets from a private repo.

Env vars: GITHUB_TOKEN, GITHUB_REPO (format: org/repo), GITHUB_BRANCH
  np_popup/popup_nl_HTML          — HTML: newsletter popup markup
  np_popup/popup_nl_JS            — JS: newsletter popup logic
  np_popup/popup_nl_README.md     — README: newsletter popup docs
  pdp.html                        — HTML: full PDP page snapshot (large, 2.9MB)
  UserInsightsMonthly_Feb_Mar_2026.html — HTML: user insights report (Feb-Mar 2026)
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN = os.getenv("GITHUB_TOKEN")
REPO  = os.getenv("GITHUB_REPO", "jkb-hlm/ryzon_files")

API_BASE = "https://api.github.com"
HEADERS  = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def list_files(path: str = "") -> list[dict]:
    """List files/folders at the given path in the repo."""
    url = f"{API_BASE}/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    items = r.json()
    return [
        {"name": i["name"], "path": i["path"], "type": i["type"], "size": i.get("size", 0)}
        for i in items
    ]


def get_snippet(path: str) -> str:
    """Fetch the raw content of a file from the repo by its path."""
    url = f"{API_BASE}/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    download_url = data.get("download_url")
    if not download_url:
        raise ValueError(f"No download URL for {path}")
    raw = requests.get(download_url, timeout=10)
    raw.raise_for_status()
    return raw.text
