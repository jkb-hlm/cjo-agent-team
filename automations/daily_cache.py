#!/usr/bin/env python3
"""Daily data cache: pull etracker + GA4 → PostgreSQL.

Scheduled via n8n at 06:00 daily.
Pulls yesterday's data from all sources and stores in PostgreSQL.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# Add parent dir for tools access
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.etracker import get_report_data
from tools.ga4 import run_report
from db import upsert_etracker_rows, upsert_ga4_rows, init_schema

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def cache_etracker():
    """Pull key etracker reports for yesterday."""
    # Reports that support full figures including conversion funnel
    reports_full = [
        ("EADeviceType", "device_type"),
        ("EAGeo", "geo_country"),
        ("EAMedium", "etcc_med"),
        ("EATimeDay", "utm_date"),
    ]
    # Page reports support conversion figures but NOT pi_per_unique_visits
    PAGE_FIGURES = [
        "unique_visits", "unique_visitors", "page_impressions",
        "bounces_per_visit", "staytime_per_unique_visits_v3",
        f"conversion_count_af_position({__import__('config').ETRACKER_FUNNEL_ID})",
        f"conversion_value_af_position({__import__('config').ETRACKER_FUNNEL_ID})",
        f"conversion_rate_af_position({__import__('config').ETRACKER_FUNNEL_ID})",
    ]
    reports_page = [
        ("EAPage", "page_name"),
        ("EAEntry", "page_name"),
        ("EAExit", "page_name"),
    ]
    # Product report has its own figure set
    PRODUCT_FIGURES = [
        "product_count_ordered", "product_value_ordered", "product_quantity_ordered",
        "product_count_in_basket_distinct", "product_viewed_distinct",
    ]

    total = 0
    for report_id, attribute in reports_full:
        print(f"  etracker {report_id}...", end=" ", flush=True)
        try:
            data = get_report_data(report_id, YESTERDAY, YESTERDAY, attributes=[attribute], limit=100)
            if isinstance(data, dict) and "error" in data:
                print(f"ERROR: {data['error']}")
                continue
            rows = data if isinstance(data, list) else data.get("data", [])
            n = upsert_etracker_rows(report_id, attribute, rows, date.fromisoformat(YESTERDAY))
            print(f"{n} rows")
            total += n
        except Exception as e:
            print(f"ERROR: {e}")

    for report_id, attribute in reports_page:
        print(f"  etracker {report_id}...", end=" ", flush=True)
        try:
            data = get_report_data(
                report_id, YESTERDAY, YESTERDAY,
                attributes=[attribute], figures=PAGE_FIGURES, limit=100,
            )
            if isinstance(data, dict) and "error" in data:
                print(f"ERROR: {data['error']}")
                continue
            rows = data if isinstance(data, list) else data.get("data", [])
            n = upsert_etracker_rows(report_id, attribute, rows, date.fromisoformat(YESTERDAY))
            print(f"{n} rows")
            total += n
        except Exception as e:
            print(f"ERROR: {e}")

    # Product performance report
    print(f"  etracker EAPPR...", end=" ", flush=True)
    try:
        data = get_report_data(
            "EAPPR", YESTERDAY, YESTERDAY,
            attributes=["product_name"], figures=PRODUCT_FIGURES,
            sort_column="product_count_ordered", limit=100, attribution_model=None,
        )
        if isinstance(data, dict) and "error" in data:
            print(f"ERROR: {data['error']}")
        else:
            rows = data if isinstance(data, list) else data.get("data", [])
            n = upsert_etracker_rows("EAPPR", "product_name", rows, date.fromisoformat(YESTERDAY))
            print(f"{n} rows")
            total += n
    except Exception as e:
        print(f"ERROR: {e}")

    return total


def cache_ga4_web():
    """Pull key GA4 web reports for yesterday."""
    dimensions = [
        "deviceCategory",
        "sessionDefaultChannelGroup",
        "newVsReturning",
        "country",
    ]

    total = 0
    for dim in dimensions:
        print(f"  GA4 web {dim}...", end=" ", flush=True)
        try:
            data = run_report(YESTERDAY, YESTERDAY, dimensions=[dim], property="web")
            if "error" in data:
                print(f"ERROR: {data['error']}")
                continue
            rows = data.get("rows", [])
            n = upsert_ga4_rows("kpi_daily_ga4_web", dim, rows, date.fromisoformat(YESTERDAY))
            print(f"{n} rows")
            total += n
        except Exception as e:
            print(f"ERROR: {e}")

    return total


def cache_ga4_app():
    """Pull key GA4 app reports for yesterday."""
    dimensions = ["deviceCategory"]

    total = 0
    for dim in dimensions:
        print(f"  GA4 app {dim}...", end=" ", flush=True)
        try:
            data = run_report(YESTERDAY, YESTERDAY, dimensions=[dim], property="app")
            if "error" in data:
                print(f"ERROR: {data['error']}")
                continue
            rows = data.get("rows", [])
            n = upsert_ga4_rows("kpi_daily_ga4_app", dim, rows, date.fromisoformat(YESTERDAY))
            print(f"{n} rows")
            total += n
        except Exception as e:
            print(f"ERROR: {e}")

    return total


def main():
    print(f"=== Daily Cache — {YESTERDAY} ===")

    # Ensure schema exists
    init_schema()

    print("\n[etracker]")
    et_rows = cache_etracker()

    print("\n[GA4 Web]")
    ga4_web_rows = cache_ga4_web()

    print("\n[GA4 App]")
    ga4_app_rows = cache_ga4_app()

    print(f"\n=== Done: {et_rows} etracker + {ga4_web_rows} GA4 web + {ga4_app_rows} GA4 app rows cached ===")


if __name__ == "__main__":
    main()
