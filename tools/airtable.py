"""Airtable tools for Tessa — Experimentation Lab.

Tables (configurable via env):
  IdeaBase  — all test ideas, pipeline, results (different views = different statuses)
  Results   — detailed test results

Status values in IdeaBase:
  Hypo-generation → Next: Prio → Move to Pipeline → Ready for Dev →
  QS → Ready to start → Running → Finished/in analysis → Done
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_ID  = os.environ["AIRTABLE_BASE_ID"]
TOKEN    = os.getenv("AIRTABLE_TOKEN")

IDEABASE = os.getenv("AIRTABLE_IDEABASE_TABLE_ID", "")
RESULTS  = os.getenv("AIRTABLE_RESULTS_TABLE_ID", "")

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _get_records(table_id: str, filter_formula: str = "", max_records: int = 20) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    params = {"maxRecords": max_records}
    if filter_formula:
        params["filterByFormula"] = filter_formula
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json().get("records", [])


KEEP_FIELDS = {
    "Short Description", "Status", "Hypotheses", "Research / Background",
    "Impact", "Confidence", "Ease (1=easy, 10=hard)", "ICE-Score",
    "PageType", "Device", "Test-ID", "Test-Name", "Start Date", "End Date",
    "Result", "Learnings", "Contributor", "Follow-up Testideen",
    # Results table
    "ARPU Change", "Revenue Change", "observed confidence", "Test Results",
    "Sample Size Control", "Sample Size Variant",
}

def _format_record(r: dict) -> dict:
    fields = {k: v for k, v in r.get("fields", {}).items() if k in KEEP_FIELDS}
    return {"id": r["id"], **fields}


# ── Read ──────────────────────────────────────────────────────────────────────

def get_ideabase(status: str = "") -> list[dict]:
    """
    Get IdeaBase records. Filter by status to get the right "view":
      - 'Running'              → currently live tests
      - 'Next: Prio'           → prioritized, not yet started
      - 'Ready for Dev'        → approved, needs build
      - 'Finished/in analysis' → wrapped up, awaiting analysis
      - ''                     → all records
    """
    formula = f"{{Status}}='{status}'" if status else ""
    records = _get_records(IDEABASE, formula)
    return [_format_record(r) for r in records]


def get_results(limit: int = 10) -> list[dict]:
    """Get recent test results from the Results table."""
    records = _get_records(RESULTS, max_records=limit)
    return [_format_record(r) for r in records]


# ── Write ─────────────────────────────────────────────────────────────────────

def create_idea(
    short_description: str,
    research: str = "",
    impact: int = None,
    confidence: int = None,
    ease: int = None,
    page_type: list[str] = None,
    device: list[str] = None,
    contributor: str = "Tessa (AI)",
) -> dict:
    """Create a new idea in IdeaBase."""
    fields = {"Short Description": short_description, "Contributor": contributor}
    if research:
        fields["Research / Background"] = research
    if impact is not None:
        fields["Impact"] = impact
    if confidence is not None:
        fields["Confidence"] = confidence
    if ease is not None:
        fields["Ease (1=easy, 10=hard)"] = ease
    if page_type:
        fields["PageType"] = page_type
    if device:
        fields["Device"] = device

    url = f"https://api.airtable.com/v0/{BASE_ID}/{IDEABASE}"
    resp = requests.post(url, headers=HEADERS, json={"fields": fields})
    resp.raise_for_status()
    return _format_record(resp.json())


def update_idea(record_id: str, fields: dict) -> dict:
    """Update an existing IdeaBase record by record ID."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{IDEABASE}/{record_id}"
    resp = requests.patch(url, headers=HEADERS, json={"fields": fields})
    resp.raise_for_status()
    return _format_record(resp.json())
