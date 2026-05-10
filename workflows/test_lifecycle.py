#!/usr/bin/env python3
"""Test Lifecycle Sync — AB Tasty ↔ Airtable ↔ Asana

What this does:
  1. Pulls currently running tests from AB Tasty
  2. Compares against Airtable IdeaBase "Running" records
  3. For tests that ended → updates Airtable + creates Asana evaluation task
  4. For AB Tasty tests with no Airtable "Running" record → syncs status
  5. Recommends the next test from the prioritized backlog (ICE-sorted)

Usage:
    python workflows/test_lifecycle.py          # full sync + recommendation
    python workflows/test_lifecycle.py --dry    # dry run, no writes
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import airtable, abtasty
try:
    from tools import asana as _asana
    _ASANA_AVAILABLE = bool(__import__("os").getenv("ASANA_TOKEN"))
except Exception:
    _ASANA_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ice(record: dict) -> float:
    """Calculate ICE score from Impact × Confidence / Ease. Falls back to stored ICE-Score."""
    stored = record.get("ICE-Score")
    if stored and isinstance(stored, (int, float)):
        return float(stored)
    i = record.get("Impact") or 5
    c = record.get("Confidence") or 5
    e = record.get("Ease (1=easy, 10=hard)") or 5
    return round((i * c) / e, 2)


def _today() -> str:
    return date.today().isoformat()


def _format_test_summary(test: dict, result: dict | None = None) -> str:
    """Build a compact summary string for Asana task notes."""
    lines = [
        f"AB Tasty Test ID: {test.get('id')}",
        f"Test name: {test.get('name')}",
        f"Status: {test.get('status')}",
        f"Start: {test.get('start_date', '—')}",
        f"Stop:  {test.get('stop_date', '—')}",
        f"Traffic: {test.get('traffic', '—')}%",
        "",
        f"AB Tasty report: https://app2.abtasty.com/reporting/test/{test.get('id')}/report",
    ]
    if result:
        verdict = result.get("verdict", "")
        if verdict:
            lines += ["", f"Directional verdict: {verdict}"]
        period = result.get("period", "")
        if period:
            lines.append(f"Period: {period}")
    return "\n".join(lines)


# ── Core sync steps ───────────────────────────────────────────────────────────

def step_sync_running(abt_play: dict, at_running: list[dict], dry: bool) -> list[str]:
    """
    For each Airtable 'Running' record with a Test-ID:
      - If AB Tasty says it's stopped → flag as ended (handled in step_handle_ended)
      - If AB Tasty says it's still running → OK, optionally sync dates

    Returns list of ended record IDs.
    """
    ended_records = []
    log = []

    abt_all = abtasty.get_tests()
    abt_by_id = {str(t["id"]): t for t in abt_all}

    for record in at_running:
        test_id = str(record.get("Test-ID", "")).strip()
        name = record.get("Short Description", "?")
        if not test_id:
            log.append(f"  ⚠️  Airtable 'Running' record has no Test-ID: {name[:60]}")
            continue

        abt_test = abt_by_id.get(test_id)
        if not abt_test:
            log.append(f"  ⚠️  Test-ID {test_id} not found in AB Tasty: {name[:60]}")
            continue

        abt_status = abt_test.get("status", "")
        if abt_status == "play":
            log.append(f"  ✅  Still running: {name[:60]} (ID {test_id})")
        else:
            log.append(f"  🔴  Ended ({abt_status}): {name[:60]} (ID {test_id})")
            ended_records.append((record, abt_test))

    return ended_records, log


def step_handle_ended(ended_records: list[tuple], dry: bool) -> list[str]:
    """
    For each ended test:
      1. Update Airtable status → 'Finished/in analysis' + End Date
      2. Generate AB Tasty report
      3. Create Asana 'Evaluate: ...' task
    """
    log = []
    for record, abt_test in ended_records:
        record_id = record["id"]
        test_id = str(abt_test.get("id"))
        test_name = abt_test.get("name", f"Test {test_id}")
        short_desc = record.get("Short Description", test_name)

        log.append(f"\n  Handling ended test: {short_desc[:60]}")

        # 1. Update Airtable
        if not dry:
            try:
                airtable.update_idea(record_id, {
                    "Status": "Finished/in analysis",
                    "End Date": _today(),
                })
                log.append(f"    → Airtable updated: 'Finished/in analysis'")
            except Exception as e:
                log.append(f"    → Airtable update failed: {e}")
        else:
            log.append(f"    → [dry] would update Airtable to 'Finished/in analysis'")

        # 2. Generate AB Tasty report
        report_result = None
        try:
            report_result = abtasty.generate_test_report(test_id, metric_preset="full")
            log.append(f"    → Report generated: {report_result.get('verdict', 'no verdict')[:80]}")
        except Exception as e:
            log.append(f"    → Report generation failed: {e}")

        # 3. Create Asana task
        if _ASANA_AVAILABLE:
            task_name = f"Evaluate: {short_desc[:80]}"
            notes = _format_test_summary(abt_test, report_result)
            if report_result and report_result.get("report"):
                # Append first 500 chars of report for quick context
                snippet = report_result["report"][:500].strip()
                notes += f"\n\n---\n{snippet}\n…"

            existing = _asana.find_task_by_name(task_name)
            if existing:
                log.append(f"    → Asana task already exists: {existing.get('gid')}")
            elif not dry:
                try:
                    task = _asana.create_task(
                        name=task_name,
                        notes=notes,
                        due_on=_today(),
                    )
                    log.append(f"    → Asana task created: {task.get('url', task)}")
                except Exception as e:
                    log.append(f"    → Asana task creation failed: {e}")
            else:
                log.append(f"    → [dry] would create Asana task: '{task_name}'")
        else:
            log.append(f"    → Asana skipped (ASANA_TOKEN not set)")

    return log


def step_sync_new_running(abt_play: dict, at_running: list[dict], dry: bool) -> list[str]:
    """
    For AB Tasty tests currently running that have NO matching Airtable 'Running' record:
    Find the Airtable record by Test-ID (any status) and update it to 'Running'.
    """
    log = []
    at_all = airtable.get_ideabase()  # all statuses
    at_by_test_id = {str(r.get("Test-ID", "")).strip(): r for r in at_all if r.get("Test-ID")}

    # Find Airtable 'Running' test IDs to avoid duplicates
    at_running_ids = {str(r.get("Test-ID", "")).strip() for r in at_running}

    for test_id, abt_test in abt_play.items():
        if test_id in at_running_ids:
            continue  # already tracked as Running

        at_record = at_by_test_id.get(test_id)
        if at_record:
            rec_id = at_record["id"]
            name = at_record.get("Short Description", f"Test {test_id}")
            current_status = at_record.get("Status", "?")
            log.append(f"  📋  AB Tasty running but Airtable status='{current_status}': {name[:60]}")
            if not dry:
                try:
                    airtable.update_idea(rec_id, {
                        "Status": "Running",
                        "Start Date": abt_test.get("start_date", _today()),
                        "Test-Name": abt_test.get("name", ""),
                    })
                    log.append(f"      → Updated to 'Running'")
                except Exception as e:
                    log.append(f"      → Update failed: {e}")
            else:
                log.append(f"      → [dry] would update to 'Running'")
        else:
            log.append(f"  ❓  Running in AB Tasty, no Airtable record: '{abt_test.get('name')}' (ID {test_id})")

    return log


def step_recommend_next(at_running: list[dict]) -> list[str]:
    """
    Recommend the next test(s) to launch from 'Next: Prio' and 'Ready for Dev' backlog.
    Sorted by ICE score. Excludes page types / devices already heavily tested.
    """
    log = []

    backlog = airtable.get_ideabase("Next: Prio") + airtable.get_ideabase("Ready for Dev")
    if not backlog:
        log.append("  No items in 'Next: Prio' or 'Ready for Dev'.")
        return log

    # Get page types currently being tested to flag conflicts
    running_pages = set()
    for r in at_running:
        for p in (r.get("PageType") or []):
            running_pages.add(p)

    scored = sorted(backlog, key=_ice, reverse=True)

    log.append(f"\n  {'#':<3} {'ICE':<6} {'Status':<18} {'Conflict':<10} Description")
    log.append(f"  {'-'*3} {'-'*6} {'-'*18} {'-'*10} {'-'*45}")

    for i, rec in enumerate(scored[:8], 1):
        ice = _ice(rec)
        status = rec.get("Status", "?")
        pages = rec.get("PageType") or []
        desc = rec.get("Short Description", "?")[:50]
        conflict = "⚠️ overlap" if any(p in running_pages for p in pages) else ""
        log.append(f"  {i:<3} {ice:<6} {status:<18} {conflict:<10} {desc}")

    log.append(f"\n  Top pick: {scored[0].get('Short Description', '?')[:70]}")
    log.append(f"  ICE: {_ice(scored[0])} | Status: {scored[0].get('Status')} | Pages: {scored[0].get('PageType')}")

    return log


# ── Main sync ─────────────────────────────────────────────────────────────────

def sync(dry: bool = False) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  Test Lifecycle Sync — {now}{' [DRY RUN]' if dry else ''}")
    print(f"{'='*60}")

    # ── AB Tasty: get all tests ──
    print("\n📡 Fetching AB Tasty tests...")
    abt_tests = abtasty.get_tests()
    if not abt_tests or (len(abt_tests) == 1 and "error" in abt_tests[0]):
        print(f"  Error fetching AB Tasty tests: {abt_tests}")
        return

    abt_play = {str(t["id"]): t for t in abt_tests if t.get("status") == "play"}
    print(f"  → {len(abt_play)} running, {len(abt_tests)} total")

    # ── Airtable: get Running records ──
    print("\n📋 Fetching Airtable 'Running' records...")
    at_running = airtable.get_ideabase("Running")
    print(f"  → {len(at_running)} records with status 'Running'")

    # ── Step 1: Detect ended tests ──
    print("\n🔍 Checking for ended tests...")
    ended_records, sync_log = step_sync_running(abt_play, at_running, dry)
    for line in sync_log:
        print(line)

    # ── Step 2: Handle ended tests ──
    if ended_records:
        print(f"\n🏁 Handling {len(ended_records)} ended test(s)...")
        end_log = step_handle_ended(ended_records, dry)
        for line in end_log:
            print(line)
    else:
        print("\n  No ended tests detected.")

    # ── Step 3: Sync newly running tests ──
    print("\n🔄 Checking for newly running tests...")
    new_log = step_sync_new_running(abt_play, at_running, dry)
    if new_log:
        for line in new_log:
            print(line)
    else:
        print("  All running AB Tasty tests are already tracked.")

    # ── Step 4: Recommend next test ──
    print("\n🎯 Next test recommendation (ICE-ranked backlog):")
    rec_log = step_recommend_next(at_running)
    for line in rec_log:
        print(line)

    print(f"\n{'='*60}")
    print(f"  Sync complete.{' No writes were made (dry run).' if dry else ''}")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Lifecycle Sync")
    parser.add_argument("--dry", action="store_true", help="Dry run — read only, no writes")
    args = parser.parse_args()
    sync(dry=args.dry)
