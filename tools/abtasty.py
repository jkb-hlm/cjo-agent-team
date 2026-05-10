"""AB Tasty API tools for Tessa — tests, results, reports, Airtable + Slack push."""

import datetime
import json
import os
import time
import requests
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

CLIENT_ID     = os.getenv("ABTASTY_CLIENT_ID")
CLIENT_SECRET = os.getenv("ABTASTY_CLIENT_SECRET")
ACCOUNT_ID    = os.getenv("ABTASTY_ACCOUNT_ID")

AUTH_URL            = "https://api.abtasty.com/oauth/v2/token"
API_BASE            = f"https://api.abtasty.com/api/v1/accounts/{ACCOUNT_ID}"
DATA_EXPLORER_BASE  = f"https://api-data-explorer.abtasty.com/v2/clients/{ACCOUNT_ID}"

AIRTABLE_API  = "https://api.airtable.com/v0"
AT_TOKEN      = os.getenv("AIRTABLE_TOKEN", "")
AT_BASE_ID    = os.getenv("AIRTABLE_BASE_ID", "")
AT_TABLE_ID   = os.getenv("AIRTABLE_TABLE_ID", "")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")

VAULT_PATH = Path(os.getenv("VAULT_PATH", str(Path.home() / "vault")))

METRIC_PRESETS = {
    "traffic": [
        {"key": "users", "type": "COMMON"},
        {"key": "sessions", "type": "COMMON"},
        {"key": "transactions"},
    ],
    "revenue": [
        {"key": "users", "type": "COMMON"},
        {"key": "transactions"},
        {"key": "revenuePerUser"},
    ],
    "full": [
        {"key": "users", "type": "COMMON"},
        {"key": "sessions", "type": "COMMON"},
        {"key": "transactions"},
        {"key": "revenuePerUser"},
    ],
}

MONTH_MAP_DE = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Jun",
                7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez"}

_token_cache: dict = {}


def _get_token() -> str:
    """Fetch OAuth token (cached for session)."""
    if _token_cache.get("token"):
        return _token_cache["token"]
    resp = requests.post(AUTH_URL, json={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    token = resp.json()["access_token"]
    _token_cache["token"] = token
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Test metadata ────────────────────────────────────────────────────────────

def get_tests(status: str = "") -> list[dict]:
    """
    Get AB Tasty tests. status options: 'play' (running), 'pause', 'stop'.
    Returns a simplified list with id, name, status, type, start/stop dates.
    Paginates automatically (API returns 12/page, account can have 100+).
    """
    params = {"_max_per_page": 50}
    if status:
        params["status"] = status
    all_tests = []
    page = 1
    try:
        while True:
            params["_page"] = page
            resp = requests.get(f"{API_BASE}/tests", headers=_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            tests = data.get("_data", []) if isinstance(data, dict) else data
            if not tests:
                break
            all_tests.extend(tests)
            total_pages = (data.get("_pagination") or {}).get("_pages", 1)
            if page >= total_pages:
                break
            page += 1
        return [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "status": t.get("status"),
                "type": t.get("type"),
                "url": t.get("url", ""),
                "start_date": t.get("startDate", t.get("start_date", "")),
                "stop_date": t.get("stopDate", t.get("stop_date", "")),
                "traffic": t.get("percentageOfVisitors", t.get("traffic", "")),
            }
            for t in all_tests
        ]
    except Exception as e:
        return [{"error": str(e)}]


def get_test(test_id: str) -> dict:
    """Get full test metadata for a single test."""
    resp = requests.get(f"{API_BASE}/tests/{test_id}", headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_test_results(test_id: str) -> dict:
    """Get results for a specific AB Tasty test by ID."""
    try:
        resp = requests.get(f"{API_BASE}/tests/{test_id}/results", headers=_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── Data Explorer (detailed metrics) ────────────────────────────────────────

def _get_data_explorer_results(test_id: str, test: dict, metrics: list[dict]) -> dict:
    """Query Data Explorer for detailed metrics on a test."""
    from_ts = (test.get("last_play") or {}).get("timestamp") or \
              (test.get("created_at") or {}).get("timestamp") or \
              (int(time.time()) - 90 * 86400)
    last_pause = (test.get("last_pause") or {}).get("timestamp")
    now_ts = last_pause if last_pause else int(time.time())

    fmt = lambda ts: datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    period = f"{fmt(from_ts)} – {fmt(now_ts)}"

    payload = {
        "timeIntervals": [{"start": str(from_ts), "end": str(now_ts)}],
        "dimensions": ["campaignId", "variationId"],
        "metrics": metrics,
        "filters": {
            "single": {"field": "campaignId", "operator": "EQUAL", "value": test_id},
            "filteringStrategy": "PER_SESSION",
        },
        "limit": 100,
    }
    resp = requests.post(
        f"{DATA_EXPLORER_BASE}/query",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    if resp.status_code == 200:
        return {"ok": True, "data": resp.json(), "period": period, "from_ts": from_ts, "now_ts": now_ts}
    return {"ok": False, "status": resp.status_code, "detail": resp.text[:500], "period": period}


# ── Report parsing helpers ───────────────────────────────────────────────────

def _resolve_variation_name(variation_id: str, test: dict) -> str:
    if variation_id == "0":
        return "Original (control)"
    for v in test.get("variations", []):
        if str(v.get("id")) == variation_id:
            return v.get("name", variation_id)
    return variation_id


def _parse_results(raw: dict, test: dict) -> list[dict]:
    headers = raw.get("headers", [])
    parsed = []
    for row in raw.get("rows", []):
        values = row.get("values", [])
        record = {}
        for i, h in enumerate(headers):
            val = values[i] if i < len(values) else "—"
            if h == "variationId":
                record["Variation"] = _resolve_variation_name(val, test)
            elif h == "campaignId":
                continue
            elif h == "users":
                record["Unique visitors"] = int(val) if str(val).isdigit() else val
            elif h == "sessions":
                record["Sessions"] = int(val) if str(val).isdigit() else val
            elif h == "transactions":
                record["Transactions"] = int(val) if str(val).isdigit() else val
            elif h == "revenuePerUser":
                try:
                    rpu = float(val)
                    record["Revenue / user"] = f"€{rpu:.2f}"
                    record["_rpu_raw"] = rpu
                except (ValueError, TypeError):
                    record["Revenue / user"] = "—"
            else:
                record[h] = val
        parsed.append(record)
    return parsed


def _add_cr_and_uplift(rows: list[dict]) -> list[dict]:
    if not rows or "Unique visitors" not in rows[0] or "Transactions" not in rows[0]:
        return rows
    for row in rows:
        uv, tx = row.get("Unique visitors", 0), row.get("Transactions", 0)
        row["CR"] = f"{(tx / uv * 100):.2f}%" if uv else "—"
    control_cr = None
    for row in rows:
        uv, tx = row.get("Unique visitors", 0), row.get("Transactions", 0)
        if uv:
            cr = tx / uv
            if control_cr is None:
                control_cr = cr
                row["Uplift"] = "— (control)"
            else:
                if control_cr:
                    uplift = (cr - control_cr) / control_cr * 100
                    row["Uplift"] = f"{uplift:+.2f}%"
                    row["_uplift_raw"] = uplift
                else:
                    row["Uplift"] = "— (no control txn)"
        else:
            row["Uplift"] = "—"
    return rows


def _md_table(rows: list[dict]) -> list[str]:
    display_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if not display_rows:
        return ["> _(no rows)_"]
    headers = list(display_rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in display_rows:
        lines.append("| " + " | ".join(str(row.get(h, "—")) for h in headers) + " |")
    return lines


def _stat_summary(rows: list[dict]) -> tuple[list[str], str]:
    verdict = ""
    lines = []
    if len(rows) < 2 or "Unique visitors" not in rows[0]:
        return lines, verdict
    ctrl, var = rows[0], rows[1]
    n_c, n_v = ctrl.get("Unique visitors", 0), var.get("Unique visitors", 0)
    t_c, t_v = ctrl.get("Transactions", 0), var.get("Transactions", 0)
    if not (n_c and n_v and isinstance(n_c, int)):
        return lines, verdict
    cr_c = t_c / n_c
    cr_v = t_v / n_v
    uplift = (cr_v - cr_c) / cr_c * 100 if cr_c else 0
    lines += ["## Statistical Summary", ""]
    lines += ["| | Control | Variation 1 |", "| --- | --- | --- |"]
    lines += [
        f"| Unique visitors | {n_c:,} | {n_v:,} |",
        f"| Transactions    | {t_c:,} | {t_v:,} |",
        f"| CR              | {cr_c * 100:.2f}% | {cr_v * 100:.2f}% |",
        f"| Uplift          | — | {uplift:+.2f}% |",
        "",
    ]
    if abs(uplift) < 1.0:
        verdict = "No meaningful effect — uplift below 1%. Do not ship."
    elif abs(uplift) < 3.0:
        verdict = f"Small effect — uplift {uplift:+.2f}%. Verify statistical significance before deciding."
    else:
        direction = "Positive" if uplift > 0 else "Negative"
        verdict = f"{direction} effect — uplift {uplift:+.2f}%. Confirm significance in AB Tasty dashboard."
    lines.append(f"> **{verdict}**")
    lines.append("")
    return lines, verdict


# ── Report generation ────────────────────────────────────────────────────────

def generate_test_report(test_id: str, metric_preset: str = "full") -> dict:
    """
    Generate a full structured test report for a given AB Tasty test ID.
    metric_preset: 'traffic', 'revenue', or 'full' (default).
    Returns {report: str, parsed_rows: list, verdict: str, test: dict, period: str}.
    """
    metrics = METRIC_PRESETS.get(metric_preset, METRIC_PRESETS["full"])
    metric_label = metric_preset.capitalize()

    test = get_test(test_id)
    results = _get_data_explorer_results(test_id, test, metrics)

    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    name = test.get("name") or f"Test {test_id}"
    last_play = (test.get("last_play") or {}).get("readable_date", "—")
    last_pause = (test.get("last_pause") or {}).get("readable_date", "—")

    lines = [
        f"# AB Tasty Report — {name}",
        "",
        f"**Test ID:** `{test_id}`  ",
        f"**Status:** {test.get('status', '—')} / {test.get('state', '—')}  ",
        f"**Run period:** {last_play[:10] if last_play != '—' else '—'} → {last_pause[:10] if last_pause != '—' else '—'}  ",
        f"**Generated:** {generated_at}",
        "",
        "---",
        "",
    ]

    # Overview table
    lines += ["## Overview", ""]
    lines += ["| Field | Value |", "| --- | --- |"]
    for k, v in [
        ("Description", (test.get("description") or "—").strip()),
        ("Type", test.get("type", "—")),
        ("Traffic %", (test.get("traffic") or {}).get("value", "—")),
        ("Days active", test.get("days_active", "—")),
        ("Goals", test.get("total_goals", "—")),
        ("Statistics", test.get("statistic_engine", "—")),
    ]:
        lines.append(f"| **{k}** | {v} |")
    lines.append("")

    # Variations
    flat_variations = test.get("variations", [])
    if flat_variations:
        lines += ["## Variations", ""]
        lines += _md_table([{"ID": v.get("id"), "Name": v.get("name"), "Traffic %": v.get("traffic", "—")} for v in flat_variations])
        lines.append("")

    # Results
    period = results.get("period", "test period")
    lines += [f"## Results — {metric_label} ({period})", ""]

    parsed = []
    verdict = ""
    if not results.get("ok"):
        lines += [
            f"> **Warning:** Data Explorer query failed (HTTP {results.get('status', '?')}).",
            f"> Raw error: `{results.get('detail', '')}`",
            "",
        ]
    else:
        parsed = _parse_results(results["data"], test)
        parsed = _add_cr_and_uplift(parsed)
        lines += _md_table(parsed) if parsed else ["> No result rows returned."]
        lines.append("")
        summary_lines, verdict = _stat_summary(parsed)
        lines += summary_lines

    report = "\n".join(lines) + "\n"
    return {
        "report": report,
        "parsed_rows": parsed,
        "verdict": verdict,
        "test_name": name,
        "period": period,
    }


def save_report_to_vault(report: str, filename: str) -> str:
    """Save report markdown to the cjo-team-outputs folder. Returns file path."""
    output_dir = VAULT_PATH / "Ryzon" / "01_Projects" / "cjo-team-outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(report, encoding="utf-8")
    return str(path)


# ── Airtable push ────────────────────────────────────────────────────────────

def push_report_to_airtable(test_id: str, test: dict, results_ok: bool,
                            parsed_rows: list[dict]) -> dict:
    """Push test results to Airtable IdeaBase. Returns {ok, action}."""
    if not all([AT_TOKEN, AT_BASE_ID, AT_TABLE_ID]):
        return {"ok": False, "error": "Airtable credentials missing in .env"}

    at_headers = {"Authorization": f"Bearer {AT_TOKEN}", "Content-Type": "application/json"}

    from_ts = 0
    last_pause_ts = 0
    fmt = lambda ts: datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else None

    fields: dict = {
        "ABTasty Campaign ID": test_id,
        "ABTasty Report Link": f"https://app2.abtasty.com/reporting/test/{test_id}/report",
        "Test-ID": test_id,
        "Test-Name": test.get("name", ""),
        "Status": "Finished/in analysis",
    }

    if results_ok and len(parsed_rows) >= 1:
        ctrl = parsed_rows[0]
        var = parsed_rows[1] if len(parsed_rows) >= 2 else {}
        uv_c = ctrl.get("Unique visitors", 0)
        tx_c = ctrl.get("Transactions", 0)
        uv_v = var.get("Unique visitors", 0)
        tx_v = var.get("Transactions", 0)

        fields["UniqueVisitor_Baseline"] = uv_c
        fields["TotalTransaction_Baseline"] = tx_c
        fields["UniqueVisitor_Variant1"] = uv_v
        fields["TotalTransaction_Variant1"] = tx_v

        if uv_c: fields["Transaction_Rate_Baseline"] = tx_c / uv_c
        if uv_v: fields["Transaction_Rate_Variant1"] = tx_v / uv_v
        if ctrl.get("_rpu_raw"): fields["ARPU_Baseline"] = ctrl["_rpu_raw"]
        if var.get("_rpu_raw"): fields["ARPU_Variant1"] = var["_rpu_raw"]
        if var.get("_uplift_raw") is not None:
            fields["TR Growth (%)"] = var["_uplift_raw"] / 100

    # Upsert: find existing record or create new
    find_resp = requests.get(
        f"{AIRTABLE_API}/{AT_BASE_ID}/{AT_TABLE_ID}",
        headers=at_headers,
        params={"filterByFormula": f'{{"ABTasty Campaign ID"}}="{test_id}"', "maxRecords": 1},
        timeout=15,
    )
    record_id = None
    if find_resp.status_code == 200:
        records = find_resp.json().get("records", [])
        record_id = records[0]["id"] if records else None

    if record_id:
        resp = requests.patch(f"{AIRTABLE_API}/{AT_BASE_ID}/{AT_TABLE_ID}/{record_id}",
                              headers=at_headers, json={"fields": fields}, timeout=15)
        action = "updated"
    else:
        resp = requests.post(f"{AIRTABLE_API}/{AT_BASE_ID}/{AT_TABLE_ID}",
                             headers=at_headers, json={"fields": fields}, timeout=15)
        action = "created"

    if resp.status_code not in (200, 201):
        return {"ok": False, "error": resp.text[:300]}
    return {"ok": True, "action": action}


# ── Slack push ───────────────────────────────────────────────────────────────

def post_report_to_slack(test_name: str, test_id: str, period: str,
                         status: str, parsed_rows: list[dict],
                         metric_label: str, verdict: str) -> dict:
    """Post a test summary to Slack #experimentation."""
    if not SLACK_WEBHOOK:
        return {"ok": False, "error": "SLACK_WEBHOOK_URL missing in .env"}

    link = f"https://app2.abtasty.com/reporting/test/{test_id}/report"
    lines = [
        f":bar_chart: *AB Tasty Report — {test_name}*",
        f"Test ID: `{test_id}` | Period: {period} | Status: _{status}_",
        "",
    ]

    if len(parsed_rows) >= 2:
        lines.append(f"*{metric_label}*")
        for row in parsed_rows:
            name_str = row.get("Variation", "—")
            uv = f"{row['Unique visitors']:,}" if isinstance(row.get("Unique visitors"), int) else "—"
            sessions = f"{row['Sessions']:,}" if isinstance(row.get("Sessions"), int) else None
            tx = f"{row['Transactions']:,}" if isinstance(row.get("Transactions"), int) else "—"
            rpu = row.get("Revenue / user", "")
            cr = row.get("CR", "")
            uplift = row.get("Uplift", "")
            parts = [f"*{name_str}*", f"{uv} visitors"]
            if sessions: parts.append(f"{sessions} sessions")
            parts.append(f"{tx} txn")
            if rpu: parts.append(rpu)
            if cr: parts.append(f"CR {cr}")
            if uplift and uplift != "— (control)": parts.append(f"Uplift *{uplift}*")
            lines.append(" | ".join(parts))
        lines.append("")

    if verdict:
        lines.append(f"{verdict}")
    lines.append(f"\n<{link}|View in AB Tasty>")

    resp = requests.post(SLACK_WEBHOOK, json={"text": "\n".join(lines)}, timeout=15)
    return {"ok": resp.status_code == 200}
