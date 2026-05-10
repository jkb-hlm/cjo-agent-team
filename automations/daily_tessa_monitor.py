#!/usr/bin/env python3
"""Daily Tessa test monitor: check running AB Tasty tests.

Scheduled via n8n at 08:00 daily.
Checks all running tests for: SRM, guardrail breaches, significance.
Alerts Jakob on Slack if issues found. Silent if all clear.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from math import sqrt

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ABTASTY_CLIENT_ID, ABTASTY_CLIENT_SECRET, ABTASTY_ACCOUNT_ID,
)
from db import get_conn, init_schema
from slack import post
from psycopg2.extras import Json

# Load Tessa's system prompt
TESSA_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "experimentation.md"
TESSA_PROMPT = TESSA_PROMPT_PATH.read_text() if TESSA_PROMPT_PATH.exists() else ""

# AB Tasty OAuth
_token_cache = {}


def _get_abtasty_token() -> str:
    """Get AB Tasty OAuth token."""
    if "token" in _token_cache:
        return _token_cache["token"]

    resp = requests.post(
        "https://api.abtasty.com/oauth/v2/token",
        json={
            "grant_type": "client_credentials",
            "client_id": ABTASTY_CLIENT_ID,
            "client_secret": ABTASTY_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    _token_cache["token"] = token
    return token


def _abtasty_headers() -> dict:
    return {"Authorization": f"Bearer {_get_abtasty_token()}", "Content-Type": "application/json"}


def get_running_tests() -> list[dict]:
    """Get all running tests from AB Tasty."""
    tests = []
    page = 1
    while True:
        resp = requests.get(
            f"https://api.abtasty.com/api/v1/accounts/{ABTASTY_ACCOUNT_ID}/tests",
            headers=_abtasty_headers(),
            params={"_page": page, "_max_per_page": 50, "state": "play"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("_data", data.get("items", data.get("results", [])))
        if not items:
            break
        tests.extend(items)
        page += 1
        if len(items) < 50:
            break
    return tests


def check_srm(visitors_control: int, visitors_variant: int, expected_ratio: float = 0.5) -> bool:
    """Check for Sample Ratio Mismatch. Returns True if SRM detected."""
    total = visitors_control + visitors_variant
    if total < 100:
        return False  # Too few visitors to check

    expected_control = total * expected_ratio
    expected_variant = total * (1 - expected_ratio)

    chi2 = ((visitors_control - expected_control) ** 2 / expected_control +
            (visitors_variant - expected_variant) ** 2 / expected_variant)

    # chi2 > 3.84 = p < 0.05 → SRM detected
    return chi2 > 3.84


def check_guardrails(test_data: dict) -> list[str]:
    """Check guardrail metrics. Returns list of breach descriptions."""
    breaches = []

    # AOV guardrail: variant AOV should not drop >5% vs control
    aov_control = test_data.get("aov_control", 0)
    aov_variant = test_data.get("aov_variant", 0)
    if aov_control and aov_control > 0:
        aov_change = (aov_variant - aov_control) / aov_control
        if aov_change < -0.05:
            breaches.append(f"AOV dropped {abs(aov_change):.1%} (control: {aov_control:.0f}, variant: {aov_variant:.0f})")

    return breaches


def analyze_tests(tests: list[dict]) -> str:
    """Send test data to Claude with Tessa's prompt for analysis."""
    if not tests:
        return ""

    user_message = f"""Daily Test Monitor — {date.today().isoformat()}

Here are all currently running AB Tasty tests with their latest metrics.
For each test, check:
1. Is there an SRM issue?
2. Are guardrail metrics breached?
3. Has any test reached significance?
4. What's the sample size progress?

DATA:
{json.dumps(tests, indent=2, default=str)}

Be concise. Only flag issues that need Jakob's attention. If all tests are healthy, say so in one line.
"""

    result = subprocess.run(
        ['claude', '-p', user_message, '--append-system-prompt', TESSA_PROMPT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr}")

    return result.stdout.strip()


def save_test_snapshot(test_data: dict):
    """Save test snapshot to PostgreSQL."""
    today = date.today()
    with get_conn() as conn:
        conn.cursor().execute("""
            INSERT INTO test_monitor
                (date, test_id, test_name, status, visitors_control, visitors_variant,
                 cr_control, cr_variant, chance_to_win, aov_control, aov_variant,
                 guardrail_ok, srm_ok, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, test_id) DO UPDATE SET
                visitors_control = EXCLUDED.visitors_control,
                visitors_variant = EXCLUDED.visitors_variant,
                cr_control = EXCLUDED.cr_control,
                cr_variant = EXCLUDED.cr_variant,
                chance_to_win = EXCLUDED.chance_to_win,
                guardrail_ok = EXCLUDED.guardrail_ok,
                srm_ok = EXCLUDED.srm_ok,
                raw_json = EXCLUDED.raw_json
        """, (
            today, test_data["test_id"], test_data.get("test_name"),
            "running", test_data.get("visitors_control"),
            test_data.get("visitors_variant"),
            test_data.get("cr_control"), test_data.get("cr_variant"),
            test_data.get("chance_to_win"),
            test_data.get("aov_control"), test_data.get("aov_variant"),
            len(test_data.get("guardrail_breaches", [])) == 0,
            not test_data.get("srm_detected", False),
            Json(test_data),
        ))


def main():
    today = date.today()
    print(f"=== Tessa Daily Monitor — {today} ===")

    init_schema()

    print("\n[1] Fetching running tests from AB Tasty...")
    raw_tests = get_running_tests()
    print(f"  {len(raw_tests)} tests running")

    if not raw_tests:
        print("No running tests. Done.")
        return

    # Extract key metrics from each test
    test_summaries = []
    alerts = []

    for test in raw_tests:
        test_id = str(test.get("id", ""))
        test_name = test.get("name", "Unnamed")

        # Extract variation data (structure varies by AB Tasty API version)
        variations = test.get("variations", [])
        control = next((v for v in variations if v.get("is_reference")), variations[0] if variations else {})
        variant = variations[1] if len(variations) > 1 else {}

        visitors_c = control.get("visitors", 0)
        visitors_v = variant.get("visitors", 0)

        summary = {
            "test_id": test_id,
            "test_name": test_name,
            "visitors_control": visitors_c,
            "visitors_variant": visitors_v,
            "cr_control": control.get("conversion_rate"),
            "cr_variant": variant.get("conversion_rate"),
            "chance_to_win": variant.get("chance_to_win"),
            "aov_control": control.get("aov"),
            "aov_variant": variant.get("aov"),
        }

        # Check SRM
        srm = check_srm(visitors_c, visitors_v)
        summary["srm_detected"] = srm
        if srm:
            alerts.append(f"*SRM detected* on test `{test_name}` ({test_id}) — traffic split is off")

        # Check guardrails
        breaches = check_guardrails(summary)
        summary["guardrail_breaches"] = breaches
        for b in breaches:
            alerts.append(f"*Guardrail breach* on `{test_name}`: {b}")

        test_summaries.append(summary)

        # Save snapshot
        try:
            save_test_snapshot(summary)
        except Exception as e:
            print(f"  Warning: failed to save snapshot for {test_id}: {e}")

    print(f"\n[2] {len(test_summaries)} tests checked, {len(alerts)} alerts")

    # If there are alerts, also get Tessa's analysis
    if alerts:
        print("\n[3] Getting Tessa's analysis...")
        analysis = analyze_tests(test_summaries)

        message = (
            f"*Tessa Test Monitor — {today}*\n\n"
            f"*Alerts:*\n" + "\n".join(f"- {a}" for a in alerts) +
            f"\n\n*Tessa's Analysis:*\n{analysis}"
        )
        post(message, channel="experimentation")
        print("  Posted to Slack")
    else:
        print("  All tests healthy — no alerts")


if __name__ == "__main__":
    main()
