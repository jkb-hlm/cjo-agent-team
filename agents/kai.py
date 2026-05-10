"""Kai — CJO Data Analyst Agent

Tool use: Kai can query etracker and GA4 directly via the Claude tool_use API.
He decides which source and reports to fetch based on the task — no manual CSV export needed.

Data sources:
  etracker — complete web traffic (no consent gap), good for absolutes
  GA4      — consent-based, good for funnel events, segments, behavioral analysis
"""

import json
import time
from typing import Optional
import anthropic
from pathlib import Path

from tools import etracker as et
from tools import ga4

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "kai.md"

# ── Claude tool definitions ───────────────────────────────────────────────────

GA4_TOOLS = [
    {
        "name": "ga4_run_report",
        "description": (
            "Run a GA4 Data API report. Use for funnel analysis, event-based metrics, "
            "behavioral segmentation, and cross-referencing etracker data. "
            "GA4 is consent-based (undercounts vs etracker) but has richer event/funnel data. "
            "Properties: 'web' (ryzon.com webshop, default) or 'app' (Ryzon app). "
            "Common dimensions: country, deviceCategory, sessionDefaultChannelGroup, "
            "pagePath, landingPage, newVsReturning, sessionSource, sessionMedium, date. "
            "Common metrics: sessions, totalUsers, newUsers, bounceRate, "
            "averageSessionDuration, sessionConversionRate, ecommercePurchases, "
            "purchaseRevenue, addToCarts, checkouts, cartToViewRate. "
            "Use dimension_filters to filter by country, page path, channel, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date: YYYY-MM-DD or relative ('7daysAgo', '30daysAgo', 'yesterday')",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date: YYYY-MM-DD or 'today'",
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Dimension names, e.g. ['country', 'deviceCategory']",
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metric names. Leave null for default web KPI set.",
                },
                "dimension_filters": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Filters. Exact: {\"dimension\": \"country\", \"value\": \"United States\"}. "
                        "Contains: {\"dimension\": \"pagePath\", \"contains\": \"/collections/\"}. "
                        "Begins with: {\"dimension\": \"pagePath\", \"begins_with\": \"/collections\"}. "
                        "Negate: add \"not\": true to any filter."
                    ),
                },
                "order_by": {
                    "type": "string",
                    "description": "Metric or dimension name to sort by.",
                },
                "order_desc": {
                    "type": "boolean",
                    "description": "Sort descending (default: true).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default: 100).",
                },
                "property": {
                    "type": "string",
                    "enum": ["web", "app"],
                    "description": "'web' for ryzon.com webshop (default), 'app' for Ryzon app.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]

ETRACKER_TOOLS = [
    {
        "name": "etracker_list_reports",
        "description": (
            "List all available report IDs in the etracker account. "
            "Use this when you're unsure which report to query, or to discover available dimensions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "etracker_get_report_info",
        "description": (
            "Get metadata for a specific etracker report: available attributes (dimensions) "
            "and figures (KPIs) with their IDs. Use before querying an unfamiliar report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "description": "Report identifier, e.g. 'EAGeo', 'EADeviceType', 'EAPage', 'EATime'",
                },
            },
            "required": ["report_id"],
        },
    },
    {
        "name": "etracker_get_data",
        "description": (
            "Fetch report data from etracker. This is your primary data tool. "
            "Always include conversion figures (CR, revenue) unless explicitly told not to. "
            "Known report IDs: EAGeo (by country), EADeviceType (by device), "
            "EAPage (by page URL), EATime (by month/year). "
            "Default figures include: unique_visits, unique_visitors, page_impressions, "
            "bounces_per_visit, session duration, pages/session, conversion_count, "
            "conversion_value, conversion_rate (all with position attribution)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "description": "Report ID, e.g. 'EAGeo', 'EADeviceType', 'EAPage', 'EATime'",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "attributes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Dimension columns. Examples: ['geo_country'], ['device_type'], "
                        "['page_url'], ['time_month']. Leave empty for totals."
                    ),
                },
                "figures": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "KPI columns. Leave null/empty to use the full default KPI set "
                        "(visits, visitors, page impressions, bounce rate, session duration, "
                        "pages/session, conversion count, conversion value, conversion rate)."
                    ),
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Optional filters. Attribute filter example: "
                        '{"attributeId": "geo_country", "input": ["Germany"], "filter": "include", "type": "exact"}. '
                        "Keyfigure filter example: "
                        '{"keyfigure": "unique_visits", "input": 100, "type": "gt", "filter": "include"}'
                    ),
                },
                "sort_column": {
                    "type": "string",
                    "description": "Column to sort by (default: unique_visits)",
                },
                "sort_order": {
                    "type": "integer",
                    "enum": [1, 2],
                    "description": "1=descending (default), 2=ascending",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default: 100, max: 100000)",
                },
            },
            "required": ["report_id", "start_date", "end_date"],
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: dict):
    if name == "ga4_run_report":
        return ga4.run_report(
            start_date=inputs["start_date"],
            end_date=inputs["end_date"],
            dimensions=inputs.get("dimensions"),
            metrics=inputs.get("metrics") or None,
            dimension_filters=inputs.get("dimension_filters"),
            order_by=inputs.get("order_by"),
            order_desc=inputs.get("order_desc", True),
            limit=inputs.get("limit", 100),
            property=inputs.get("property", "web"),
        )
    elif name == "etracker_list_reports":
        return et.list_reports()
    elif name == "etracker_get_report_info":
        return et.get_report_info(inputs["report_id"])
    elif name == "etracker_get_data":
        return et.get_report_data(
            report_id=inputs["report_id"],
            start_date=inputs["start_date"],
            end_date=inputs["end_date"],
            attributes=inputs.get("attributes"),
            figures=inputs.get("figures") or None,
            filters=inputs.get("filters"),
            sort_column=inputs.get("sort_column", "unique_visits"),
            sort_order=inputs.get("sort_order", 1),
            limit=inputs.get("limit", 100),
        )
    else:
        return {"error": f"Unknown tool: {name}"}


# ── Agent ─────────────────────────────────────────────────────────────────────

def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_agent(client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
    """Create a Kai agent instance with system prompt loaded."""
    return {
        "name": "Kai",
        "role": "Data Analyst",
        "system_prompt": load_prompt(),
        "client": client,
        "model": model,
    }


_MAX_TOOL_RESULT_CHARS = 6000


def _last_week_range() -> tuple:
    from datetime import date, timedelta
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.strftime("%Y-%m-%d"), last_sunday.strftime("%Y-%m-%d")  # truncate large etracker responses to keep tokens in check


def _truncate_result(result, max_chars: int = _MAX_TOOL_RESULT_CHARS) -> str:
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    # Keep first N chars and note truncation
    return text[:max_chars] + f"\n... [truncated — {len(text) - max_chars} chars omitted]"


def run(agent: dict, user_message: str, context: str = "", use_tools: bool = True) -> str:
    """
    Run Kai on a task. With use_tools=True (default), Kai can query etracker
    directly via tool use. With use_tools=False, he works from context only
    (pass pre-fetched data as context string).
    """
    from datetime import date
    client: anthropic.Anthropic = agent["client"]

    today = date.today().strftime("%Y-%m-%d")
    date_note = f"Today's date is {today}. Last week = Mon {_last_week_range()[0]} to Sun {_last_week_range()[1]}."

    messages = []
    if context:
        messages.append({
            "role": "user",
            "content": f"<context>\n{date_note}\n{context}\n</context>\n\n{user_message}",
        })
    else:
        messages.append({
            "role": "user",
            "content": f"<context>{date_note}</context>\n\n{user_message}",
        })

    tools = (GA4_TOOLS + ETRACKER_TOOLS) if use_tools else []

    # Tool-use loop
    while True:
        kwargs = dict(
            model=agent["model"],
            max_tokens=8192,
            system=agent["system_prompt"],
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        for attempt in range(5):
            try:
                response = client.messages.create(**kwargs)
                break
            except anthropic.RateLimitError:
                if attempt == 4:
                    raise
                wait = 60 * (attempt + 1)
                print(f"  ⏳ Rate limit hit — waiting {wait}s (attempt {attempt + 1}/5)...")
                time.sleep(wait)

        # Done — extract final text
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        # Tool use — execute and loop
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  🔧 Kai → etracker: {block.name}({json.dumps(block.input, ensure_ascii=False)[:100]})")
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _truncate_result(result),
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        return f"[Unexpected stop_reason: {response.stop_reason}]"
