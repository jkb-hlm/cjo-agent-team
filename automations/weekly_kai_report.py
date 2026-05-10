#!/usr/bin/env python3
"""Weekly Kai report: full analysis → Slack + Obsidian.

Scheduled via n8n Monday 07:00.
Pulls cached data from PostgreSQL, sends to Claude API with Kai's prompt,
generates audience-tailored summaries, posts to Slack, writes to Obsidian.
"""

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import VAULT_PATH
from db import query
from slack import post

# Load Kai's system prompt
KAI_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "kai.md"
KAI_PROMPT = KAI_PROMPT_PATH.read_text() if KAI_PROMPT_PATH.exists() else ""


def get_weekly_data() -> dict:
    """Pull this week vs. last week data from PostgreSQL cache."""
    today = date.today()
    # This week = last 7 days, last week = 7-14 days ago
    this_week_end = (today - timedelta(days=1)).isoformat()
    this_week_start = (today - timedelta(days=7)).isoformat()
    last_week_end = (today - timedelta(days=8)).isoformat()
    last_week_start = (today - timedelta(days=14)).isoformat()

    data = {}

    # etracker by device
    data["etracker_device_this_week"] = query("""
        SELECT attribute_value AS device,
               SUM(unique_visits) AS sessions,
               AVG(conversion_rate) AS avg_cr,
               SUM(conversion_value) AS total_revenue,
               AVG(bounces_per_visit) AS avg_bounce
        FROM kpi_daily_etracker
        WHERE date BETWEEN %s AND %s AND report_id = 'EADeviceType'
        GROUP BY attribute_value ORDER BY sessions DESC
    """, (this_week_start, this_week_end))

    data["etracker_device_last_week"] = query("""
        SELECT attribute_value AS device,
               SUM(unique_visits) AS sessions,
               AVG(conversion_rate) AS avg_cr,
               SUM(conversion_value) AS total_revenue,
               AVG(bounces_per_visit) AS avg_bounce
        FROM kpi_daily_etracker
        WHERE date BETWEEN %s AND %s AND report_id = 'EADeviceType'
        GROUP BY attribute_value ORDER BY sessions DESC
    """, (last_week_start, last_week_end))

    # etracker by geo
    data["etracker_geo_this_week"] = query("""
        SELECT attribute_value AS country,
               SUM(unique_visits) AS sessions,
               AVG(conversion_rate) AS avg_cr,
               SUM(conversion_value) AS total_revenue
        FROM kpi_daily_etracker
        WHERE date BETWEEN %s AND %s AND report_id = 'EAGeo'
        GROUP BY attribute_value ORDER BY sessions DESC LIMIT 10
    """, (this_week_start, this_week_end))

    # etracker top pages
    data["etracker_pages_this_week"] = query("""
        SELECT attribute_value AS page,
               SUM(unique_visits) AS sessions,
               AVG(conversion_rate) AS avg_cr
        FROM kpi_daily_etracker
        WHERE date BETWEEN %s AND %s AND report_id = 'EAPage'
        GROUP BY attribute_value ORDER BY sessions DESC LIMIT 20
    """, (this_week_start, this_week_end))

    # etracker abandoned carts
    data["etracker_carts_this_week"] = query("""
        SELECT attribute_value,
               SUM(unique_visits) AS sessions,
               SUM(conversion_value) AS value
        FROM kpi_daily_etracker
        WHERE date BETWEEN %s AND %s AND report_id = 'EACart'
        GROUP BY attribute_value ORDER BY sessions DESC LIMIT 10
    """, (this_week_start, this_week_end)) if True else []

    # GA4 web by channel
    data["ga4_channel_this_week"] = query("""
        SELECT dimension_value AS channel,
               SUM(sessions) AS sessions,
               AVG(session_conversion_rate) AS avg_cr,
               SUM(purchase_revenue) AS revenue
        FROM kpi_daily_ga4_web
        WHERE date BETWEEN %s AND %s AND dimension_name = 'sessionDefaultChannelGroup'
        GROUP BY dimension_value ORDER BY sessions DESC
    """, (this_week_start, this_week_end))

    data["ga4_channel_last_week"] = query("""
        SELECT dimension_value AS channel,
               SUM(sessions) AS sessions,
               AVG(session_conversion_rate) AS avg_cr,
               SUM(purchase_revenue) AS revenue
        FROM kpi_daily_ga4_web
        WHERE date BETWEEN %s AND %s AND dimension_name = 'sessionDefaultChannelGroup'
        GROUP BY dimension_value ORDER BY sessions DESC
    """, (last_week_start, last_week_end))

    # GA4 app
    data["ga4_app_this_week"] = query("""
        SELECT dimension_value AS device,
               SUM(sessions) AS sessions,
               AVG(session_conversion_rate) AS avg_cr,
               SUM(purchase_revenue) AS revenue
        FROM kpi_daily_ga4_app
        WHERE date BETWEEN %s AND %s
        GROUP BY dimension_value ORDER BY sessions DESC
    """, (this_week_start, this_week_end))

    data["ga4_app_last_week"] = query("""
        SELECT dimension_value AS device,
               SUM(sessions) AS sessions,
               AVG(session_conversion_rate) AS avg_cr,
               SUM(purchase_revenue) AS revenue
        FROM kpi_daily_ga4_app
        WHERE date BETWEEN %s AND %s
        GROUP BY dimension_value ORDER BY sessions DESC
    """, (last_week_start, last_week_end))

    return data


def analyze_with_claude(data: dict) -> dict:
    """Send data to Claude CLI with Kai's prompt, get analysis + audience summaries."""
    today = date.today()
    kw = today.isocalendar()[1]

    user_message = f"""Weekly KPI Review — KW {kw} ({(today - timedelta(days=7)).isoformat()} to {(today - timedelta(days=1)).isoformat()})

Here is the cached data from etracker and GA4. Analyse it according to your Weekly KPI Review mode.

DATA:
{json.dumps(data, indent=2, default=str)}

INSTRUCTIONS:
1. Produce a FULL REPORT for Jakob (all segments, red/green flags, hypotheses, recommended actions)
2. Then produce 3 AUDIENCE SUMMARIES (max 5 bullets + 1 action each):
   - MARKETING (Denis, Eva): channel performance, paid efficiency, budget signals
   - PO (Laura): page performance, funnel drop-offs, device UX
   - MERCHANDISING (Lisa): category performance, collection CTR, AOV

Format each section with a clear header. Use markdown.
"""

    result = subprocess.run(
        ['claude', '-p', user_message, '--append-system-prompt', KAI_PROMPT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr}")

    full_text = result.stdout.strip()

    # Split into sections (crude but effective)
    sections = {"full": full_text, "marketing": "", "po": "", "merchandising": ""}

    for label, key in [("MARKETING", "marketing"), ("PO", "po"), ("MERCHANDISING", "merchandising")]:
        marker = f"## {label}" if f"## {label}" in full_text else f"# {label}"
        if marker.upper() in full_text.upper():
            idx = full_text.upper().index(marker.upper())
            sections[key] = full_text[idx:]

    return sections


def write_to_obsidian(report: str):
    """Write the full report to today's Obsidian daily note."""
    today = date.today()
    daily_note_path = Path(VAULT_PATH) / "Ryzon" / "daily" / f"{today.strftime('%d.%m.%Y')}.md"

    kai_section = f"\n\n---\n## Kai Weekly Report — KW {today.isocalendar()[1]}\n\n{report}\n"

    if daily_note_path.exists():
        content = daily_note_path.read_text()
        content += kai_section
        daily_note_path.write_text(content)
    else:
        daily_note_path.write_text(f"# {today.strftime('%d.%m.%Y')}\n{kai_section}")

    print(f"  Written to {daily_note_path}")


def main():
    today = date.today()
    kw = today.isocalendar()[1]
    print(f"=== Weekly Kai Report — KW {kw} ===")

    print("\n[1] Pulling cached data...")
    data = get_weekly_data()

    # Check if we have data
    total_rows = sum(len(v) for v in data.values() if isinstance(v, list))
    if total_rows == 0:
        print("No cached data found. Run daily_cache.py first.")
        return

    print(f"  {total_rows} data rows loaded")

    print("\n[2] Analysing with Claude (Kai)...")
    sections = analyze_with_claude(data)

    print("\n[3] Posting to Slack...")
    # Full report → #cjo-data
    post(f"*Kai Weekly Report — KW {kw}*\n\n{sections['full'][:3000]}", channel="cjo")

    # Audience summaries → respective channels (using cjo for now)
    if sections["marketing"]:
        post(f"*Weekly Insights for Marketing — KW {kw}*\n\n{sections['marketing'][:2000]}", channel="cjo")
    if sections["po"]:
        post(f"*Weekly Insights for PO — KW {kw}*\n\n{sections['po'][:2000]}", channel="cjo")
    if sections["merchandising"]:
        post(f"*Weekly Insights for Merchandising — KW {kw}*\n\n{sections['merchandising'][:2000]}", channel="cjo")

    print("\n[4] Writing to Obsidian...")
    write_to_obsidian(sections["full"])

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
