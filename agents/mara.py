"""Mara — UX Research Strategist Agent

Tools available:
  - get_ideabase        Read hypothesis backlog from Airtable IdeaBase
  - create_idea         Write a new hypothesis to IdeaBase
  - fetch_page          Fetch a web page for UX analysis (competitor audits, RYZON pages)
  - fetch_multiple      Fetch several pages at once for side-by-side comparison
  - get_recordings      Hotjar recording metadata (rage clicks, device, page, duration)
  - get_rage_click_summary  Aggregate rage clicks by page
  - get_heatmaps        List Hotjar heatmaps
  - get_surveys         List Hotjar surveys
  - get_survey_responses    Get open-text survey responses
"""

import json
import sys
from pathlib import Path

import anthropic

# ── Tool imports ──────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools import airtable, web_fetch

try:
    from tools import hotjar as _hotjar
    _HOTJAR_AVAILABLE = True
except Exception:
    _HOTJAR_AVAILABLE = False

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "mara.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_ideabase",
        "description": (
            "Read hypothesis and test ideas from the IdeaBase in Airtable. "
            "Use to check what research already exists, avoid duplicates, and understand current pipeline."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": (
                        "Filter by status. Leave empty for all. "
                        "Options: 'Running', 'Next: Prio', 'Ready for Dev', "
                        "'Finished/in analysis', 'Done', 'Hypo-generation'"
                    ),
                    "default": "",
                }
            },
        },
    },
    {
        "name": "create_idea",
        "description": (
            "Create a new hypothesis card in IdeaBase. Use after generating a well-evidenced hypothesis. "
            "Always populate Research/Background with the evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "short_description": {"type": "string", "description": "One-line hypothesis title"},
                "research":          {"type": "string", "description": "Evidence and background — what we observed and why this matters"},
                "impact":            {"type": "integer", "minimum": 1, "maximum": 10, "description": "ICE impact score"},
                "confidence":        {"type": "integer", "minimum": 1, "maximum": 10, "description": "ICE confidence score"},
                "ease":              {"type": "integer", "minimum": 1, "maximum": 10, "description": "ICE ease score (1=easy, 10=hard)"},
                "page_type":         {"type": "array", "items": {"type": "string"}, "description": "e.g. ['PDP', 'PLP', 'Checkout', 'Homepage']"},
                "device":            {"type": "array", "items": {"type": "string"}, "description": "e.g. ['Mobile', 'Desktop']"},
            },
            "required": ["short_description"],
        },
    },
    {
        "name": "fetch_page",
        "description": (
            "Fetch a web page and extract readable text for UX analysis. "
            "Use for: competitor page audits (Rapha, Endura, PNS), RYZON page analysis, "
            "landing page reviews. Not suitable for JS-heavy SPAs — returns server-rendered content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL including https://"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "fetch_multiple",
        "description": "Fetch several pages at once for side-by-side UX comparison. Ideal for competitive audits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to fetch",
                },
            },
            "required": ["urls"],
        },
    },
    {
        "name": "get_recordings",
        "description": (
            "Get Hotjar recording metadata. Returns page URL, device, duration, rage clicks, dead clicks. "
            "Use to identify sessions worth watching manually in Hotjar UI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":        {"type": "integer", "default": 20, "description": "Max recordings to return"},
                "rage_click":   {"type": "boolean", "default": False, "description": "Only sessions with rage clicks"},
                "dead_click":   {"type": "boolean", "default": False, "description": "Only sessions with dead clicks"},
                "device":       {"type": "string", "description": "Filter by device: 'phone', 'tablet', 'desktop'"},
                "min_duration": {"type": "integer", "default": 0, "description": "Minimum session duration in seconds"},
            },
        },
    },
    {
        "name": "get_rage_click_summary",
        "description": "Aggregate rage click data ranked by page. Quick way to identify the most frustrating pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50, "description": "Number of recordings to analyse"},
            },
        },
    },
    {
        "name": "get_heatmaps",
        "description": "List available Hotjar heatmaps with page URL and sample count. View visuals in Hotjar UI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_surveys",
        "description": "List Hotjar surveys and their response counts.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_survey_responses",
        "description": "Get open-text responses from a Hotjar survey. Use for VoC / exit survey analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "survey_id": {"type": "integer", "description": "Survey ID from get_surveys()"},
                "limit":     {"type": "integer", "default": 50},
            },
            "required": ["survey_id"],
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _call_tool(name: str, inputs: dict):
    """Route tool calls to implementations. Returns JSON-serialisable result."""
    try:
        if name == "get_ideabase":
            return airtable.get_ideabase(inputs.get("status", ""))

        elif name == "create_idea":
            return airtable.create_idea(
                short_description=inputs["short_description"],
                research=inputs.get("research", ""),
                impact=inputs.get("impact"),
                confidence=inputs.get("confidence"),
                ease=inputs.get("ease"),
                page_type=inputs.get("page_type"),
                device=inputs.get("device"),
                contributor="Mara (AI)",
            )

        elif name == "fetch_page":
            return web_fetch.fetch_page(inputs["url"])

        elif name == "fetch_multiple":
            return web_fetch.fetch_multiple(inputs["urls"])

        elif name in ("get_recordings", "get_rage_click_summary", "get_heatmaps",
                      "get_surveys", "get_survey_responses"):
            if not _HOTJAR_AVAILABLE:
                return {"error": "Hotjar tool could not be loaded — check HOTJAR_SITE_ID and HOTJAR_API_TOKEN in .env"}
            fn = getattr(_hotjar, name)
            return fn(**{k: v for k, v in inputs.items()})

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"error": str(e)}


# ── Agent ─────────────────────────────────────────────────────────────────────

def create_agent(client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
    return {
        "name": "Mara",
        "role": "UX Research Strategist",
        "system_prompt": load_prompt(),
        "client": client,
        "model": model,
    }


def run(agent: dict, user_message: str, context: str = "") -> str:
    """
    Run Mara with full tool use support (agentic loop).
    Mara can call tools autonomously to gather data before responding.
    """
    client: anthropic.Anthropic = agent["client"]

    initial_content = (
        f"<context>\n{context}\n</context>\n\n{user_message}" if context else user_message
    )
    messages = [{"role": "user", "content": initial_content}]

    while True:
        response = client.messages.create(
            model=agent["model"],
            max_tokens=4096,
            system=agent["system_prompt"],
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return next(
                (block.text for block in response.content if hasattr(block, "text")), ""
            )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _call_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            return next(
                (block.text for block in response.content if hasattr(block, "text")), ""
            )
