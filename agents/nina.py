"""Nina — CJO Communicator & Sparring Partner Agent"""

import anthropic
from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "nina.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_agent(client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
    return {
        "name": "Nina",
        "role": "Communicator & Sparring Partner",
        "system_prompt": load_prompt(),
        "client": client,
        "model": model,
    }


def run(agent: dict, user_message: str, context: str = "") -> str:
    """Run Nina on a task and return her response."""
    messages = []

    if context:
        messages.append({
            "role": "user",
            "content": f"<context>\n{context}\n</context>\n\n{user_message}",
        })
    else:
        messages.append({"role": "user", "content": user_message})

    response = agent["client"].messages.create(
        model=agent["model"],
        max_tokens=4096,
        system=agent["system_prompt"],
        messages=messages,
    )

    return response.content[0].text
