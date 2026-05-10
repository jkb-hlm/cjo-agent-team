#!/usr/bin/env python3
"""
CJO Team Orchestrator v2 — No Anthropic API required.

All reasoning is handled by Claude Code. This script only:
  1. Prints the agent's system prompt so Claude Code knows how to think
  2. Optionally runs a tool directly via tools/cli.py

Usage:
  python3 orchestrator.py --agent tessa            # Print Tessa's system prompt
  python3 orchestrator.py --tool etracker.get_data '{"report_id":"EAPage",...}'
  python3 orchestrator.py --list-tools             # List all available tools

Claude Code then calls tools directly:
  python3 tools/cli.py <tool> '<json args>'

Agent prompts (for Claude Code context):
  Kai    → prompts/kai.md
  Mara   → prompts/mara.md
  Arno   → prompts/data_architect.md
  Tessa  → prompts/experimentation.md
  Dev    → prompts/frontend_dev.md
  Nina   → prompts/nina.md
"""

import argparse
import subprocess
import sys
import json
from pathlib import Path

AGENT_PROMPTS = {
    "kai":   "prompts/kai.md",
    "mara":  "prompts/mara.md",
    "arno":  "prompts/data_architect.md",
    "tessa": "prompts/experimentation.md",
    "dev":   "prompts/frontend_dev.md",
    "nina":  "prompts/nina.md",
}

BASE = Path(__file__).parent


def print_prompt(agent: str):
    path = BASE / AGENT_PROMPTS.get(agent, "")
    if not path.exists():
        print(f"No prompt found for agent '{agent}'")
        sys.exit(1)
    print(path.read_text(encoding="utf-8"))


def run_tool(tool: str, args_json: str):
    result = subprocess.run(
        [sys.executable, str(BASE / "tools" / "cli.py"), tool, args_json],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def list_tools():
    subprocess.run([sys.executable, str(BASE / "tools" / "cli.py"), "--list"])


def main():
    parser = argparse.ArgumentParser(description="CJO Team Orchestrator — Claude Code edition")
    parser.add_argument("--agent", "-a", help="Print agent system prompt (kai/mara/arno/tessa/dev/nina)")
    parser.add_argument("--tool", "-t", nargs="+", help="Run a tool: --tool <name> '<json args>'")
    parser.add_argument("--list-tools", action="store_true", help="List all available tools")
    args = parser.parse_args()

    if args.list_tools:
        list_tools()
    elif args.agent:
        print_prompt(args.agent)
    elif args.tool:
        tool_name = args.tool[0]
        tool_args = args.tool[1] if len(args.tool) > 1 else "{}"
        run_tool(tool_name, tool_args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
