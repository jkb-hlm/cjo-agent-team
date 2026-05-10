"""etracker Reporting API tools for Kai.

Base URL:  https://ws.etracker.com/api/v7
Auth:      X-ET-Token header
Rate:      50 calls/5min · 10 parallel · 100k rows max

Known report IDs (call list_reports() to discover all):
  EAGeo         — by country/region        (attribute: geo_country)
  EADeviceType  — by device type           (attribute: device_type)
  EAPage        — by page URL              (attribute: page_url)
  EATime        — by month/year            (attribute: time_month)

Default figures (full KPI set, incl. conversion via attribution funnel):
  unique_visits, unique_visitors, page_impressions, bounces_per_visit,
  staytime_per_unique_visits_v3, pi_per_unique_visits,
  conversion_count_af_position({funnel_id}),
  conversion_value_af_position({funnel_id}),
  conversion_rate_af_position({funnel_id})
"""

import json
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN     = os.getenv("ETRACKER_TOKEN")
FUNNEL_ID = os.getenv("ETRACKER_ATTRIBUTION_FUNNEL_ID", "2767063")
BASE_URL  = "https://ws.etracker.com/api/v7"

DEFAULT_FIGURES = [
    "unique_visits",
    "unique_visitors",
    "page_impressions",
    "bounces_per_visit",
    "staytime_per_unique_visits_v3",
    "pi_per_unique_visits",
    f"conversion_count_af_position({FUNNEL_ID})",
    f"conversion_value_af_position({FUNNEL_ID})",
    f"conversion_rate_af_position({FUNNEL_ID})",
]


def _headers() -> dict:
    return {"X-ET-Token": TOKEN, "Accept": "application/json"}


def list_reports() -> list[dict]:
    """List all available report IDs in the etracker account."""
    try:
        resp = requests.get(f"{BASE_URL}/report", headers=_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return [{"error": str(e)}]


def get_report_info(report_id: str) -> dict:
    """Get metadata for a report — available attributes and figures with their IDs."""
    try:
        resp = requests.get(f"{BASE_URL}/report/{report_id}/info", headers=_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def get_report_data(
    report_id: str,
    start_date: str,
    end_date: str,
    attributes: Optional[list] = None,
    figures: Optional[list] = None,
    filters: Optional[list] = None,
    sort_column: str = "unique_visits",
    sort_order: int = 1,
    limit: int = 100,
    attribution_model: Optional[str] = "position",
) -> dict:
    """
    Fetch report data from etracker.

    Args:
        report_id:   Report identifier, e.g. 'EAGeo', 'EADeviceType', 'EAPage', 'EATime'
        start_date:  YYYY-MM-DD
        end_date:    YYYY-MM-DD
        attributes:  Dimension columns, e.g. ['geo_country'], ['device_type'], ['page_url']
        figures:     KPI columns — defaults to full KPI set (visits, CR, revenue, etc.)
        filters:     List of filter dicts:
                       {"attributeId": "geo_country", "input": ["Germany"], "filter": "include", "type": "exact"}
                       {"keyfigure": "unique_visits", "input": 100, "type": "gt", "filter": "include"}
        sort_column: Column to sort by (default: unique_visits)
        sort_order:  1=descending, 2=ascending
        limit:       Max rows returned (max 100,000)
    """
    if figures is None:
        figures = DEFAULT_FIGURES

    params = {
        "startDate": start_date,
        "endDate": end_date,
        "figures": ",".join(figures),
        "sortColumn": sort_column,
        "sortOrder": str(sort_order),
        "displayType": "flat",
        "requestSource": "rest_request",
        "limit": limit,
        "extendedFilters": json.dumps(filters) if filters else "[]",
    }
    if attribution_model:
        params["attributionModel"] = attribution_model
    if attributes:
        params["attributes"] = ",".join(attributes)

    try:
        resp = requests.get(
            f"{BASE_URL}/report/{report_id}/data",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── Convenience wrappers (pre-built queries for common Kai tasks) ─────────────

def get_by_country(start_date: str, end_date: str, limit: int = 20) -> dict:
    """Sessions, visitors, CR, revenue segmented by country."""
    return get_report_data(
        "EAGeo", start_date, end_date, attributes=["geo_country"], limit=limit
    )


def get_by_device(start_date: str, end_date: str) -> dict:
    """Sessions, visitors, CR, revenue segmented by device type."""
    return get_report_data(
        "EADeviceType", start_date, end_date, attributes=["device_type"]
    )


def get_by_page(start_date: str, end_date: str, limit: int = 50) -> dict:
    """Sessions, CR, revenue by page URL — top pages by visits."""
    return get_report_data(
        "EAPage", start_date, end_date, attributes=["page_url"], limit=limit
    )


def get_by_time(start_date: str, end_date: str) -> dict:
    """Sessions, CR, revenue aggregated over time (month/year)."""
    return get_report_data(
        "EATime", start_date, end_date, attributes=["time_month"]
    )
