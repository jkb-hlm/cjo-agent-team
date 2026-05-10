"""Asana API tools — CJO team agent account.

Auth:     Personal Access Token from the agent Asana account
Env vars: ASANA_TOKEN, ASANA_CJO_PROJECT_GID

To find your project GID:
    python -c "from tools.asana import get_projects; [print(p) for p in get_projects()]"
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN       = os.getenv("ASANA_TOKEN", "")
PROJECT_GID = os.getenv("ASANA_CJO_PROJECT_GID", "")
BASE        = "https://app.asana.com/api/1.0"


def _headers() -> dict:
    if not TOKEN:
        raise EnvironmentError("ASANA_TOKEN not set in .env")
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Discovery helpers ────────────────────────────────────────────────────────

def get_projects() -> list[dict]:
    """List all projects the agent account can see. Use to find ASANA_CJO_PROJECT_GID."""
    resp = requests.get(
        f"{BASE}/projects",
        headers=_headers(),
        params={"opt_fields": "gid,name,archived", "limit": 100},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        {"gid": p["gid"], "name": p["name"], "archived": p.get("archived", False)}
        for p in resp.json().get("data", [])
    ]


def get_sections() -> list[dict]:
    """List sections in the CJO project. Useful for routing tasks to the right section."""
    if not PROJECT_GID:
        return []
    resp = requests.get(
        f"{BASE}/projects/{PROJECT_GID}/sections",
        headers=_headers(),
        params={"opt_fields": "gid,name"},
        timeout=15,
    )
    if not resp.ok:
        return []
    return [{"gid": s["gid"], "name": s["name"]} for s in resp.json().get("data", [])]


# ── Task operations ──────────────────────────────────────────────────────────

def create_task(
    name: str,
    notes: str = "",
    due_on: str = None,           # "YYYY-MM-DD"
    section_gid: str = None,      # move task to this section after creation
    assignee_gid: str = None,     # leave None to leave unassigned
) -> dict:
    """
    Create a task in the CJO project.

    Returns {"gid", "name", "url"} on success, {"error": ...} on failure.
    """
    if not PROJECT_GID:
        return {"error": "ASANA_CJO_PROJECT_GID not set in .env"}

    fields: dict = {
        "name": name,
        "projects": [PROJECT_GID],
        "notes": notes,
    }
    if due_on:
        fields["due_on"] = due_on
    if assignee_gid:
        fields["assignee"] = assignee_gid

    resp = requests.post(
        f"{BASE}/tasks",
        headers=_headers(),
        json={"data": fields},
        timeout=15,
    )
    if not resp.ok:
        return {"error": resp.text[:300]}

    task = resp.json().get("data", {})
    gid = task.get("gid")

    # Optionally move to a specific section
    if section_gid and gid:
        requests.post(
            f"{BASE}/sections/{section_gid}/addTask",
            headers=_headers(),
            json={"data": {"task": gid}},
            timeout=15,
        )

    return {
        "gid": gid,
        "name": task.get("name"),
        "url": f"https://app.asana.com/0/{PROJECT_GID}/{gid}",
    }


def add_comment(task_gid: str, text: str) -> dict:
    """Add a comment to a task."""
    resp = requests.post(
        f"{BASE}/tasks/{task_gid}/stories",
        headers=_headers(),
        json={"data": {"text": text}},
        timeout=15,
    )
    return {"ok": resp.ok}


def get_tasks(section_name: str = "", completed: bool = False) -> list[dict]:
    """
    List tasks in the CJO project. Optionally filter by section name.
    Returns compact list: gid, name, completed, due_on, assignee.
    """
    if not PROJECT_GID:
        return []

    # If section filter, find the section GID first
    if section_name:
        sections = get_sections()
        section = next((s for s in sections if section_name.lower() in s["name"].lower()), None)
        if section:
            endpoint = f"{BASE}/sections/{section['gid']}/tasks"
        else:
            endpoint = f"{BASE}/projects/{PROJECT_GID}/tasks"
    else:
        endpoint = f"{BASE}/projects/{PROJECT_GID}/tasks"

    resp = requests.get(
        endpoint,
        headers=_headers(),
        params={
            "opt_fields": "gid,name,completed,due_on,assignee.name",
            "completed_since": "now" if not completed else "",
            "limit": 100,
        },
        timeout=15,
    )
    if not resp.ok:
        return []

    tasks = resp.json().get("data", [])
    return [
        {
            "gid": t.get("gid"),
            "name": t.get("name"),
            "completed": t.get("completed", False),
            "due_on": t.get("due_on"),
            "assignee": (t.get("assignee") or {}).get("name", ""),
        }
        for t in tasks
        if completed or not t.get("completed", False)
    ]


def find_task_by_name(name: str) -> dict | None:
    """Return the first task matching the given name (exact), or None."""
    for task in get_tasks(completed=True):  # search all including completed
        if task["name"].strip() == name.strip():
            return task
    return None
