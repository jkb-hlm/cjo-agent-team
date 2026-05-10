"""Google Sheets tool for Kai.

Auth:     Same service account as GA4 (google-api-python-client)
Scope:    spreadsheets (read + write)

The sheet must be shared with the service account email:
  GCP_SA_REDACTED@GCP_PROJECT_REDACTED.iam.gserviceaccount.com
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv(Path(__file__).parent.parent / ".env")

_KEY_FILE = os.getenv("GA4_KEY_FILE")
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/analytics.readonly",
]
_DEFAULT_SHEET_ID = os.getenv("KPI_WEEKLY_SHEET_ID")


def _client():
    creds = service_account.Credentials.from_service_account_file(
        _KEY_FILE, scopes=_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_range(sheet_id: str, range_: str) -> list[list]:
    """Read a range from a Google Sheet. Returns list of rows (each row is a list of values)."""
    svc = _client()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_
    ).execute()
    return result.get("values", [])


def write_range(sheet_id: str, range_: str, values: list[list]) -> dict:
    """Write values to a range in a Google Sheet. Values is a list of rows."""
    svc = _client()
    body = {"values": values}
    result = svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()
    return {"updated_cells": result.get("updatedCells"), "range": result.get("updatedRange")}


def get_sheet_names(sheet_id: str) -> list[str]:
    """List all sheet/tab names in a spreadsheet."""
    svc = _client()
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def write_kpi_weekly(data: dict, sheet_id: Optional[str] = None) -> dict:
    """
    Write KPI Weekly data to the input sheet.

    data format:
    {
        "KW-1": {
            "et_visitors": 166173,
            "et_bounce": 59.65,
            "et_cr": 1.21,
            "et_cvr_mobile": 0.86,
            "et_cvr_desktop": 2.54,
            "et_revenue": 751994,
            "et_arpu": 4.53,
            "app_users": 20179,
            "app_bounce": 12.19,
            "app_atc_rate": 18.57,
            "app_cvr": 4.22,
            "app_c2p": 22.74,
            "app_revenue": 344344,
            "app_arpu": 17.06,
        },
        "KW-2": { ... },
        ...
    }

    Sheet layout (from CSV):
    - Row 2: Unique Visitors (web)     → et_visitors
    - Row 3: Unique Visitors (app)     → app_users
    - Row 4: Bounce Rate (web)         → et_bounce
    - Row 5: Bounce Rate (app)         → app_bounce
    - Row 6: Add-to-Cart Rate (web)    → (not available)
    - Row 7: Add-to-Cart Rate (app)    → app_atc_rate
    - Row 8: CVR (web)                 → et_cr
    - Row 9: CVR (app)                 → app_cvr
    - Row 10: CVR mobile (web)         → et_cvr_mobile
    - Row 11: CVR Desktop (web)        → et_cvr_desktop
    - Row 12: Cart-to-Purchase (web)   → (not available)
    - Row 13: Cart-to-Purchase (app)   → app_c2p
    - Row 14: Sales (web)              → et_revenue
    - Row 15: Sales (app)              → app_revenue
    - Row 16: ARPU (web)               → et_arpu
    - Row 17: ARPU (app)               → app_arpu

    KW columns: KW-1=G, KW-2=H, KW-3=I, KW-4=J, KW-5=K, KW-6=L, KW-7=M, KW-8=N
    """
    sid = sheet_id or _DEFAULT_SHEET_ID

    # Row index → (metric_key, is_percentage)
    ROW_MAP = {
        2:  ("et_visitors",    False),
        3:  ("app_users",      False),
        4:  ("et_bounce",      True),
        5:  ("app_bounce",     True),
        6:  ("et_atc_rate",     True),
        7:  ("app_atc_rate",   True),
        8:  ("et_cr",          True),
        9:  ("app_cvr",        True),
        10: ("et_cvr_mobile",  True),
        11: ("et_cvr_desktop", True),
        12: ("et_c2p",          True),
        13: ("app_c2p",        True),
        14: ("et_revenue",     False),
        15: ("app_revenue",    False),
        16: ("et_arpu",        False),
        17: ("app_arpu",       False),
    }

    KW_COLS = ["G", "H", "I", "J", "K", "L", "M", "N"]
    KW_LABELS = ["KW-1", "KW-2", "KW-3", "KW-4", "KW-5", "KW-6", "KW-7", "KW-8"]

    value_ranges = []
    for row_num, (key, is_pct) in ROW_MAP.items():
        if key is None:
            continue
        for col_letter, kw_label in zip(KW_COLS, KW_LABELS):
            kw_data = data.get(kw_label, {})
            val = kw_data.get(key, "")
            if val == "-" or val == "":
                cell_val = ""
            elif is_pct:
                cell_val = round(float(val) / 100, 6)
            else:
                cell_val = float(val) if isinstance(val, str) else val
            value_ranges.append({
                "range": f"Sheet1!{col_letter}{row_num}",
                "values": [[cell_val]],
            })

    svc = _client()
    body = {"valueInputOption": "USER_ENTERED", "data": value_ranges}
    result = svc.spreadsheets().values().batchUpdate(
        spreadsheetId=sid, body=body
    ).execute()
    return {"cells_written": result.get("totalUpdatedCells", len(value_ranges)), "sheet_id": sid}
