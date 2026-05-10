#!/usr/bin/env python3
"""
CJO Tools CLI — Direct tool runner, no Anthropic API required.

Claude Code calls these tools via Bash and handles all reasoning itself.

Usage:
  python3 tools/cli.py <tool> [args as JSON string]

Examples:
  python3 tools/cli.py etracker.list_reports
  python3 tools/cli.py etracker.get_data '{"report_id":"EAPage","start_date":"2026-01-01","end_date":"2026-03-30"}'
  python3 tools/cli.py airtable.get_ideabase '{"status":"Running"}'
  python3 tools/cli.py airtable.create_idea '{"short_description":"Test idea","impact":7,"confidence":6,"ease":3}'
  python3 tools/cli.py abtasty.get_tests '{"status":"play"}'
  python3 tools/cli.py abtasty.get_test_results '{"test_id":"123456"}'
  python3 tools/cli.py github.list_files
  python3 tools/cli.py github.get_snippet '{"path":"popup_tasty_JS"}'
  python3 tools/cli.py ga4.run_report '{"start_date":"7daysAgo","end_date":"today","dimensions":["deviceCategory"]}'
"""

import json
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import etracker as et
from tools import airtable
from tools import abtasty
from tools import github
from tools import ga4


def run(tool: str, args: dict) -> any:
    # ── etracker ──────────────────────────────────────────────────────────────
    if tool == "etracker.list_reports":
        return et.list_reports()

    elif tool == "etracker.get_report_info":
        return et.get_report_info(args["report_id"])

    elif tool == "etracker.get_data":
        return et.get_report_data(
            report_id=args["report_id"],
            start_date=args["start_date"],
            end_date=args["end_date"],
            attributes=args.get("attributes"),
            figures=args.get("figures") or None,
            filters=args.get("filters"),
            sort_column=args.get("sort_column", "unique_visits"),
            sort_order=args.get("sort_order", 1),
            limit=args.get("limit", 100),
        )

    # ── Airtable ──────────────────────────────────────────────────────────────
    elif tool == "airtable.get_ideabase":
        return airtable.get_ideabase(status=args.get("status", ""))

    elif tool == "airtable.get_results":
        return airtable.get_results(limit=args.get("limit", 10))

    elif tool == "airtable.create_idea":
        return airtable.create_idea(
            short_description=args["short_description"],
            research=args.get("research", ""),
            impact=args.get("impact"),
            confidence=args.get("confidence"),
            ease=args.get("ease"),
            page_type=args.get("page_type"),
            device=args.get("device"),
        )

    elif tool == "airtable.update_idea":
        return airtable.update_idea(args["record_id"], args["fields"])

    # ── AB Tasty ──────────────────────────────────────────────────────────────
    elif tool == "abtasty.get_tests":
        return abtasty.get_tests(status=args.get("status", ""))

    elif tool == "abtasty.get_test_results":
        return abtasty.get_test_results(args["test_id"])

    elif tool == "abtasty.generate_report":
        return abtasty.generate_test_report(
            args["test_id"],
            args.get("metric_preset", "full"),
        )

    elif tool == "abtasty.push_report_to_airtable":
        test = abtasty.get_test(args["test_id"])
        return abtasty.push_report_to_airtable(
            args["test_id"], test, True, args.get("parsed_rows", [])
        )

    # ── GitHub ────────────────────────────────────────────────────────────────
    elif tool == "github.list_files":
        return github.list_files(path=args.get("path", ""))

    elif tool == "github.get_snippet":
        return {"content": github.get_snippet(args["path"])}

    # ── GA4 ───────────────────────────────────────────────────────────────────
    elif tool == "ga4.run_report":
        return ga4.run_report(
            start_date=args["start_date"],
            end_date=args["end_date"],
            dimensions=args.get("dimensions"),
            metrics=args.get("metrics") or None,
            dimension_filters=args.get("dimension_filters"),
            order_by=args.get("order_by"),
            order_desc=args.get("order_desc", True),
            limit=args.get("limit", 100),
            property=args.get("property", "web"),
        )

    else:
        return {"error": f"Unknown tool: '{tool}'. Run with --list to see available tools."}


def list_tools():
    tools = [
        ("etracker.list_reports", "List all etracker report IDs", "{}"),
        ("etracker.get_report_info", "Get etracker report metadata", '{"report_id":"EAPage"}'),
        ("etracker.get_data", "Fetch etracker report data", '{"report_id":"EAPage","start_date":"2026-01-01","end_date":"2026-03-30","attributes":["page_url"],"limit":50}'),
        ("airtable.get_ideabase", "Read IdeaBase ideas", '{"status":"Running"}'),
        ("airtable.get_results", "Read recent test results", '{"limit":10}'),
        ("airtable.create_idea", "Create a new idea record", '{"short_description":"...","impact":7,"confidence":6,"ease":3,"page_type":["PLP"],"device":["All"]}'),
        ("airtable.update_idea", "Update an idea by record ID", '{"record_id":"recXXX","fields":{"Status":"Running"}}'),
        ("abtasty.get_tests", "List AB Tasty tests", '{"status":"play"}'),
        ("abtasty.get_test_results", "Get results for a test", '{"test_id":"123456"}'),
        ("abtasty.generate_report", "Generate full test report", '{"test_id":"123456","metric_preset":"full"}'),
        ("github.list_files", "List files in the configured snippets repo", '{"path":""}'),
        ("github.get_snippet", "Fetch a code snippet", '{"path":"popup_tasty_JS"}'),
        ("ga4.run_report", "Run a GA4 report", '{"start_date":"7daysAgo","end_date":"today","dimensions":["deviceCategory"]}'),
    ]
    print("\nAvailable tools:\n")
    for name, desc, example in tools:
        print(f"  {name}")
        print(f"    {desc}")
        print(f"    Example: python3 tools/cli.py {name} '{example}'\n")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        list_tools()
        sys.exit(0)

    tool_name = sys.argv[1]
    raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"

    try:
        parsed_args = json.loads(raw_args)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON args: {e}"}))
        sys.exit(1)

    try:
        result = run(tool_name, parsed_args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
