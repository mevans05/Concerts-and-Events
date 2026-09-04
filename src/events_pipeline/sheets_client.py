"""Google Sheets REST API client. Talks to the Sheets API directly with
`requests` (same approach as google_calendar.py) rather than pulling in the
google-api-python-client SDK. Shares OAuth credentials with Calendar via
google_auth.py — the refresh token just needs both scopes granted (see
scripts/google_oauth_setup.py).
"""
from __future__ import annotations

import logging

import requests

from .google_auth import GoogleApiError
from .spreadsheet import COL_EVENT_ID, COL_FEEDBACK, COL_LEARNED_AS, FEEDBACK_OPTIONS

log = logging.getLogger(__name__)

API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
REQUEST_TIMEOUT = 30

SHEET_TAB_NAMES = ("Events", "History", "Preferences")

HEADER_BACKGROUND = {"red": 0.184, "green": 0.333, "blue": 0.588}
HEADER_FOREGROUND = {"red": 1, "green": 1, "blue": 1}


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def create_spreadsheet(access_token: str, title: str) -> dict:
    """Returns the created spreadsheet resource, including spreadsheetId
    and spreadsheetUrl."""
    body = {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": name}} for name in SHEET_TAB_NAMES],
    }
    resp = requests.post(API_BASE, headers=_headers(access_token), json=body, timeout=REQUEST_TIMEOUT)
    if not resp.ok:
        raise GoogleApiError(f"Creating spreadsheet failed ({resp.status_code}): {resp.text[:300]}")
    created = resp.json()
    apply_formatting(access_token, created["spreadsheetId"], _sheet_ids_from_metadata(created))
    return created


def _sheet_ids_from_metadata(metadata: dict) -> dict:
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in metadata.get("sheets", [])}


def get_spreadsheet_metadata(access_token: str, spreadsheet_id: str) -> dict:
    resp = requests.get(f"{API_BASE}/{spreadsheet_id}", headers=_headers(access_token), timeout=REQUEST_TIMEOUT)
    if not resp.ok:
        raise GoogleApiError(f"Fetching spreadsheet failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def ensure_tabs_exist(access_token: str, spreadsheet_id: str) -> dict:
    """Returns {sheet_title: sheet_id}, creating (and formatting) any
    tabs that are missing — e.g. if the user pointed config.yaml at a
    spreadsheet they created by hand without the right tabs."""
    metadata = get_spreadsheet_metadata(access_token, spreadsheet_id)
    existing = _sheet_ids_from_metadata(metadata)
    missing = [name for name in SHEET_TAB_NAMES if name not in existing]
    if not missing:
        return existing

    resp = requests.post(
        f"{API_BASE}/{spreadsheet_id}:batchUpdate",
        headers=_headers(access_token),
        json={"requests": [{"addSheet": {"properties": {"title": name}}} for name in missing]},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleApiError(f"Creating sheet tabs failed ({resp.status_code}): {resp.text[:300]}")
    for reply in resp.json().get("replies", []):
        added = reply.get("addSheet", {}).get("properties", {})
        if added:
            existing[added["title"]] = added["sheetId"]
    apply_formatting(access_token, spreadsheet_id, {name: existing[name] for name in missing if name in existing})
    return existing


def get_values(access_token: str, spreadsheet_id: str, sheet_name: str) -> list[list]:
    resp = requests.get(
        f"{API_BASE}/{spreadsheet_id}/values/'{sheet_name}'",
        headers=_headers(access_token),
        params={"valueRenderOption": "UNFORMATTED_VALUE"},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleApiError(f"Reading {sheet_name} failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json().get("values", [])


def write_values(access_token: str, spreadsheet_id: str, sheet_name: str, rows: list[list]) -> None:
    """Overwrites the sheet's full contents with `rows`, starting at A1.
    Formatting (header style, hidden columns, dropdown) is untouched —
    values.update/clear only affect cell values."""
    clear_resp = requests.post(
        f"{API_BASE}/{spreadsheet_id}/values/'{sheet_name}':clear",
        headers=_headers(access_token),
        timeout=REQUEST_TIMEOUT,
    )
    if not clear_resp.ok:
        raise GoogleApiError(f"Clearing {sheet_name} failed ({clear_resp.status_code}): {clear_resp.text[:300]}")
    if not rows:
        return
    resp = requests.put(
        f"{API_BASE}/{spreadsheet_id}/values/'{sheet_name}'!A1",
        headers=_headers(access_token),
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": rows},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleApiError(f"Writing {sheet_name} failed ({resp.status_code}): {resp.text[:300]}")


def apply_formatting(access_token: str, spreadsheet_id: str, sheet_ids: dict) -> None:
    """One-time cosmetic setup for newly-created Events/History tabs: bold
    white-on-blue header row, frozen header, hidden Event ID / Learned As
    columns, and a dropdown on the Feedback column. Safe to call again
    (idempotent) but unnecessary once a tab already has it."""
    requests_body = []
    for name in ("Events", "History"):
        sheet_id = sheet_ids.get(name)
        if sheet_id is None:
            continue
        requests_body.extend(
            [
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": HEADER_BACKGROUND,
                                "textFormat": {"bold": True, "foregroundColor": HEADER_FOREGROUND},
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": COL_EVENT_ID - 1,
                            "endIndex": COL_EVENT_ID,
                        },
                        "properties": {"hiddenByUser": True},
                        "fields": "hiddenByUser",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": COL_LEARNED_AS - 1,
                            "endIndex": COL_LEARNED_AS,
                        },
                        "properties": {"hiddenByUser": True},
                        "fields": "hiddenByUser",
                    }
                },
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": COL_FEEDBACK - 1,
                            "endColumnIndex": COL_FEEDBACK,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": v} for v in FEEDBACK_OPTIONS],
                            },
                            "showCustomUi": True,
                            "strict": False,
                        },
                    }
                },
            ]
        )
    if not requests_body:
        return
    resp = requests.post(
        f"{API_BASE}/{spreadsheet_id}:batchUpdate",
        headers=_headers(access_token),
        json={"requests": requests_body},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleApiError(f"Applying formatting failed ({resp.status_code}): {resp.text[:300]}")
