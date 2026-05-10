"""Hotjar API tools for Mara — qualitative behavior signals.

Auth:     Personal Access Token (generate at hotjar.com → Account → API Tokens)
Env vars: HOTJAR_SITE_ID, HOTJAR_API_TOKEN
API docs: https://api.hotjar.com/api/v3/

What IS available via API:
  - Recording metadata: page URL, device, duration, rage clicks, dead clicks, country
  - Heatmap list: which pages have heatmaps, click/move/scroll types
  - Survey responses: open-text answers, NPS scores (if surveys are set up)

What is NOT available via API (view in Hotjar UI):
  - Actual recording video playback
  - Visual heatmap images
  - Session replay

Note on Microsoft Clarity: Clarity has no practical data API (Azure AD OAuth2 only,
aggregate-only data, no heatmap or recording content). Use the Clarity UI directly.
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SITE_ID   = os.getenv("HOTJAR_SITE_ID", "")
TOKEN     = os.getenv("HOTJAR_API_TOKEN", "")
BASE      = "https://api.hotjar.com/api/v3"
HEADERS   = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


def _get(path: str, params: dict = None) -> dict | list:
    if not TOKEN:
        raise EnvironmentError("HOTJAR_API_TOKEN not set in .env")
    resp = requests.get(f"{BASE}{path}", headers=HEADERS, params=params or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Recordings ────────────────────────────────────────────────────────────────

def get_recordings(
    limit: int = 20,
    rage_click: bool = False,
    dead_click: bool = False,
    device: str = "",          # "phone" | "tablet" | "desktop"
    min_duration: int = 0,     # seconds
) -> list[dict]:
    """
    List recent session recordings with metadata.

    Filter examples:
        get_recordings(rage_click=True)           → sessions with rage clicks
        get_recordings(device="phone", limit=10)  → mobile sessions
        get_recordings(min_duration=60)           → sessions > 1 min

    Returns compact metadata — use the Hotjar UI to watch the actual recordings.
    """
    params = {"limit": limit, "sort": "-date_created"}
    if rage_click:
        params["has_rage_click"] = "true"
    if dead_click:
        params["has_dead_click"] = "true"
    if device:
        params["device_type"] = device
    if min_duration:
        params["min_duration"] = min_duration

    data = _get(f"/sites/{SITE_ID}/recordings", params)
    records = data.get("recordings", data) if isinstance(data, dict) else data

    return [
        {
            "id":           r.get("id"),
            "page":         r.get("landing_page", {}).get("href", ""),
            "device":       r.get("device_type", ""),
            "country":      r.get("country_code", ""),
            "duration_s":   r.get("duration", 0),
            "rage_clicks":  r.get("activity", {}).get("rage_clicks", 0),
            "dead_clicks":  r.get("activity", {}).get("dead_clicks", 0),
            "date":         r.get("created_epoch_timestamp", ""),
            "url":          f"https://insights.hotjar.com/sites/{SITE_ID}/recordings/{r.get('id')}",
        }
        for r in records
    ]


def get_rage_click_summary(limit: int = 50) -> dict:
    """
    Aggregate rage click data across recent recordings.
    Returns pages ranked by rage click frequency — useful for finding friction points.
    """
    recordings = get_recordings(limit=limit, rage_click=True)
    from collections import Counter
    page_counts = Counter(r["page"] for r in recordings if r["page"])
    return {
        "total_rage_click_sessions": len(recordings),
        "pages_ranked": [
            {"page": page, "sessions_with_rage_clicks": count}
            for page, count in page_counts.most_common(15)
        ],
    }


# ── Heatmaps ──────────────────────────────────────────────────────────────────

def get_heatmaps(limit: int = 20) -> list[dict]:
    """
    List heatmaps that exist for this site.
    Returns metadata only — view visuals in the Hotjar UI.
    """
    data = _get(f"/sites/{SITE_ID}/heatmaps", {"limit": limit})
    items = data.get("heatmaps", data) if isinstance(data, dict) else data
    return [
        {
            "id":      h.get("id"),
            "page":    h.get("page_url", ""),
            "type":    h.get("type", ""),      # click / move / scroll
            "samples": h.get("sample_count", 0),
            "status":  h.get("status", ""),
            "url":     f"https://insights.hotjar.com/sites/{SITE_ID}/heatmaps/{h.get('id')}",
        }
        for h in items
    ]


# ── Surveys ───────────────────────────────────────────────────────────────────

def get_surveys(limit: int = 10) -> list[dict]:
    """List active and past surveys for this site."""
    data = _get(f"/sites/{SITE_ID}/surveys", {"limit": limit})
    items = data.get("surveys", data) if isinstance(data, dict) else data
    return [
        {
            "id":       s.get("id"),
            "name":     s.get("name", ""),
            "status":   s.get("state", ""),
            "responses": s.get("response_count", 0),
            "url":      f"https://insights.hotjar.com/sites/{SITE_ID}/surveys/{s.get('id')}",
        }
        for s in items
    ]


def get_survey_responses(survey_id: int, limit: int = 50) -> list[dict]:
    """
    Get open-text responses for a specific survey.
    Most useful for exit surveys, NPS follow-up text, post-purchase feedback.
    """
    data = _get(f"/sites/{SITE_ID}/surveys/{survey_id}/responses", {"limit": limit})
    items = data.get("responses", data) if isinstance(data, dict) else data
    return [
        {
            "date":     r.get("created_epoch_timestamp", ""),
            "device":   r.get("device_type", ""),
            "country":  r.get("country_code", ""),
            "answers":  [
                {"question": a.get("text", ""), "answer": a.get("answer", {}).get("text", "")}
                for a in r.get("answers", [])
            ],
        }
        for r in items
    ]
