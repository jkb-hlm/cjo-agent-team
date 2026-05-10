"""Tessa — Experimentation Expert Agent with Airtable + AB Tasty + Report Writer + Experiment Design"""

import json
import anthropic
from pathlib import Path

from tools import airtable, abtasty, github, etracker as et

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "experimentation.md"
VAULT_PATH = Path.home() / "Desktop" / "MAIN" / "main_vault"

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    # ── IdeaBase / Airtable ──
    {
        "name": "get_ideabase",
        "description": "Read ideas from the Airtable IdeaBase. Optionally filter by status (e.g. 'Running', 'Next: Prio', 'Ready for Dev', 'Move to Pipeline', 'Finished/in analysis', 'Done'). Leave status empty to get all.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status. Leave empty for all."}
            },
        },
    },
    {
        "name": "get_results",
        "description": "Get recent test results from Airtable.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of results to fetch. Default: 10."}
            },
        },
    },
    {
        "name": "create_idea",
        "description": "Create a new test idea in the Airtable IdeaBase.",
        "input_schema": {
            "type": "object",
            "required": ["short_description"],
            "properties": {
                "short_description": {"type": "string"},
                "research": {"type": "string", "description": "Background research and evidence."},
                "impact": {"type": "integer", "description": "Impact score 1-10."},
                "confidence": {"type": "integer", "description": "Confidence score 1-10."},
                "ease": {"type": "integer", "description": "Ease score 1=easy, 10=hard."},
                "page_type": {"type": "array", "items": {"type": "string"}, "description": "E.g. ['PDP', 'PLP']"},
                "device": {"type": "array", "items": {"type": "string"}, "description": "E.g. ['Mobile', 'Desktop']"},
            },
        },
    },
    {
        "name": "update_idea",
        "description": "Update an existing idea in the Airtable IdeaBase by its record ID.",
        "input_schema": {
            "type": "object",
            "required": ["record_id", "fields"],
            "properties": {
                "record_id": {"type": "string", "description": "Airtable record ID (starts with 'rec')."},
                "fields": {
                    "type": "object",
                    "description": "Fields to update. Keys must match Airtable field names exactly.",
                },
            },
        },
    },
    # ── AB Tasty tests ──
    {
        "name": "get_abtasty_tests",
        "description": "Get tests from AB Tasty. status options: 'play' (running), 'pause', 'stop', or empty for all.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: 'play', 'pause', 'stop', or empty."}
            },
        },
    },
    {
        "name": "get_abtasty_test_results",
        "description": "Get detailed results for a specific AB Tasty test by its ID.",
        "input_schema": {
            "type": "object",
            "required": ["test_id"],
            "properties": {
                "test_id": {"type": "string", "description": "The AB Tasty test ID."}
            },
        },
    },
    # ── Report Writer ──
    {
        "name": "generate_test_report",
        "description": (
            "Generate a full structured test report for an AB Tasty test. "
            "Pulls live data from AB Tasty Data Explorer, calculates CR, uplift, "
            "statistical summary, and produces a markdown report. "
            "Use this when asked to evaluate, report on, or analyze a specific test."
        ),
        "input_schema": {
            "type": "object",
            "required": ["test_id"],
            "properties": {
                "test_id": {"type": "string", "description": "The AB Tasty test ID."},
                "metric_preset": {
                    "type": "string",
                    "enum": ["traffic", "revenue", "full"],
                    "description": "Metric set: 'traffic' (users, sessions, transactions), 'revenue' (users, transactions, revenuePerUser), 'full' (all). Default: 'full'.",
                },
                "save_to_vault": {
                    "type": "boolean",
                    "description": "Save the report to the vault cjo-team-outputs folder. Default: true.",
                },
            },
        },
    },
    {
        "name": "push_report_to_airtable",
        "description": "Push test results to Airtable IdeaBase (upserts by test ID). Run after generate_test_report.",
        "input_schema": {
            "type": "object",
            "required": ["test_id"],
            "properties": {
                "test_id": {"type": "string", "description": "The AB Tasty test ID."},
            },
        },
    },
    {
        "name": "post_report_to_slack",
        "description": "Post a test result summary to Slack #experimentation. Run after generate_test_report.",
        "input_schema": {
            "type": "object",
            "required": ["test_id"],
            "properties": {
                "test_id": {"type": "string", "description": "The AB Tasty test ID."},
            },
        },
    },
    # ── etracker ──
    {
        "name": "etracker_list_reports",
        "description": (
            "List all available report IDs in etracker. "
            "Use when unsure which report to query, or to discover available dimensions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "etracker_get_report_info",
        "description": (
            "Get metadata for a specific etracker report: available attributes (dimensions) "
            "and figures (KPIs). Use before querying an unfamiliar report."
        ),
        "input_schema": {
            "type": "object",
            "required": ["report_id"],
            "properties": {
                "report_id": {"type": "string", "description": "e.g. 'EAGeo', 'EADeviceType', 'EAPage', 'EATime'"},
            },
        },
    },
    {
        "name": "etracker_get_data",
        "description": (
            "Fetch data from etracker. Use to validate test results with real traffic data — "
            "e.g. CR by device, page-level bounce rates, conversion uplift. "
            "Known reports: EAGeo (country), EADeviceType (device), EAPage (page URL), EATime (month/year). "
            "Default figures: visits, visitors, page impressions, bounce rate, session duration, "
            "pages/session, conversion count, conversion value, conversion rate."
        ),
        "input_schema": {
            "type": "object",
            "required": ["report_id", "start_date", "end_date"],
            "properties": {
                "report_id": {"type": "string"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "attributes": {"type": "array", "items": {"type": "string"}, "description": "Dimension columns, e.g. ['device_type']"},
                "figures": {"type": "array", "items": {"type": "string"}, "description": "KPI columns. Leave empty for default set."},
                "filters": {"type": "array", "items": {"type": "object"}},
                "sort_column": {"type": "string", "description": "Column to sort by (default: unique_visits)"},
                "sort_order": {"type": "integer", "enum": [1, 2], "description": "1=desc (default), 2=asc"},
                "limit": {"type": "integer", "description": "Max rows (default: 100)"},
            },
        },
    },
    # ── GitHub Snippet Library ──
    {
        "name": "list_snippets",
        "description": (
            "List available code snippets in the ryzon_files GitHub repo. "
            "Use before fetching a snippet to find the correct file path. "
            "Optionally pass a subfolder path (e.g. 'np_popup')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Subfolder to list. Leave empty for root."}
            },
        },
    },
    {
        "name": "get_snippet",
        "description": (
            "Fetch the raw content of a code snippet from the ryzon_files GitHub repo. "
            "Use list_snippets first to find the exact path. "
            "Examples: 'bundle_variant_triggers.js', 'np_popup/popup_nl_JS', 'popup_tasty_CSS'."
        ),
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "description": "File path in the repo (e.g. 'popup_tasty_JS')."}
            },
        },
    },
    # ── Experiment Design ──
    {
        "name": "save_experiment_brief",
        "description": (
            "Save a completed experiment brief to the vault. "
            "Use after designing an experiment — writes the full brief as markdown."
        ),
        "input_schema": {
            "type": "object",
            "required": ["slug", "content"],
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Kebab-case test slug, max 5 words (e.g. 'pdp-size-guide-visibility').",
                },
                "content": {
                    "type": "string",
                    "description": "Full experiment brief in markdown.",
                },
            },
        },
    },
]


# ── Report cache (for multi-step workflows within a session) ─────────────────

_report_cache: dict = {}


# ── Tool execution ────────────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "get_ideabase":
            result = airtable.get_ideabase(status=inputs.get("status", ""))
        elif name == "get_results":
            result = airtable.get_results(limit=inputs.get("limit", 10))
        elif name == "get_abtasty_tests":
            result = abtasty.get_tests(status=inputs.get("status", ""))
        elif name == "get_abtasty_test_results":
            result = abtasty.get_test_results(inputs["test_id"])
        elif name == "create_idea":
            result = airtable.create_idea(
                short_description=inputs["short_description"],
                research=inputs.get("research", ""),
                impact=inputs.get("impact"),
                confidence=inputs.get("confidence"),
                ease=inputs.get("ease"),
                page_type=inputs.get("page_type"),
                device=inputs.get("device"),
            )
        elif name == "update_idea":
            result = airtable.update_idea(inputs["record_id"], inputs["fields"])

        # ── Report Writer tools ──
        elif name == "generate_test_report":
            test_id = inputs["test_id"]
            preset = inputs.get("metric_preset", "full")
            report_data = abtasty.generate_test_report(test_id, preset)
            _report_cache[test_id] = report_data

            if inputs.get("save_to_vault", True):
                filename = f"report-{test_id}-{report_data.get('test_name', 'test').replace(' ', '-')[:40]}.md"
                path = abtasty.save_report_to_vault(report_data["report"], filename)
                report_data["saved_to"] = path

            result = {
                "report": report_data["report"],
                "verdict": report_data.get("verdict", ""),
                "period": report_data.get("period", ""),
                "saved_to": report_data.get("saved_to", ""),
            }

        elif name == "push_report_to_airtable":
            test_id = inputs["test_id"]
            cached = _report_cache.get(test_id)
            if not cached:
                result = {"error": "No report cached for this test. Run generate_test_report first."}
            else:
                test = abtasty.get_test(test_id)
                result = abtasty.push_report_to_airtable(
                    test_id, test, True, cached.get("parsed_rows", [])
                )

        elif name == "post_report_to_slack":
            test_id = inputs["test_id"]
            cached = _report_cache.get(test_id)
            if not cached:
                result = {"error": "No report cached for this test. Run generate_test_report first."}
            else:
                result = abtasty.post_report_to_slack(
                    test_name=cached.get("test_name", f"Test {test_id}"),
                    test_id=test_id,
                    period=cached.get("period", "—"),
                    status="—",
                    parsed_rows=cached.get("parsed_rows", []),
                    metric_label="Full",
                    verdict=cached.get("verdict", ""),
                )

        # ── etracker ──
        elif name == "etracker_list_reports":
            result = et.list_reports()
        elif name == "etracker_get_report_info":
            result = et.get_report_info(inputs["report_id"])
        elif name == "etracker_get_data":
            result = et.get_report_data(
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

        # ── GitHub Snippet Library ──
        elif name == "list_snippets":
            result = github.list_files(path=inputs.get("path", ""))
        elif name == "get_snippet":
            result = {"content": github.get_snippet(inputs["path"])}

        # ── Experiment Design ──
        elif name == "save_experiment_brief":
            from datetime import date
            slug = inputs["slug"]
            content = inputs["content"]
            exp_dir = VAULT_PATH / "Ryzon" / "04_Measurement" / "experiments"
            exp_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{date.today().isoformat()}-{slug}.md"
            path = exp_dir / filename
            path.write_text(content, encoding="utf-8")
            result = {"ok": True, "path": str(path)}

        else:
            result = {"error": f"Unknown tool: {name}"}

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Agent ─────────────────────────────────────────────────────────────────────

def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_agent(client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
    return {
        "name": "Tessa",
        "role": "Experimentation Expert",
        "system_prompt": load_prompt(),
        "client": client,
        "model": model,
    }


def run(agent: dict, user_message: str, context: str = "") -> str:
    """Run Tessa with tool use loop for Airtable + AB Tasty + Report Writer + Experiment Design."""
    client: anthropic.Anthropic = agent["client"]

    content = f"<context>\n{context}\n</context>\n\n{user_message}" if context else user_message
    messages = [{"role": "user", "content": content}]

    while True:
        response = client.messages.create(
            model=agent["model"],
            max_tokens=4096,
            system=agent["system_prompt"],
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "\n".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            return "\n".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_call in tool_calls:
            print(f"   🔧 {tool_call.name}({json.dumps(tool_call.input, ensure_ascii=False)[:120]})")
            result = _execute_tool(tool_call.name, tool_call.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})
