"""Google Sheets-backed storage for the events workbook — the live,
human-editable equivalent of what spreadsheet.py does for a local .xlsx
file. All of spreadsheet.py's business logic (pending_feedback_rows,
append_events, move_past_events_to_history, ...) works unchanged against
the SimpleWorkbook built here, since it only needs the small subset of the
openpyxl Worksheet API that SimpleWorkbook also implements (see
simple_grid.py) — this module just handles the Sheets API read/write at
the edges.
"""
from __future__ import annotations

from . import sheets_client
from .preferences import Preferences
from .simple_grid import SimpleWorkbook
from .spreadsheet import DATA_SHEETS, EVENT_HEADERS, PREF_HEADERS


def _populate(sheet, values: list[list], headers: list[str]) -> None:
    if not values:
        sheet.append(list(headers))
        return
    for row in values:
        sheet.append(list(row))


def open_workbook(spreadsheet_id: str, access_token: str) -> SimpleWorkbook:
    sheets_client.ensure_tabs_exist(access_token, spreadsheet_id)
    wb = SimpleWorkbook()
    for name in (*DATA_SHEETS, "Preferences"):
        values = sheets_client.get_values(access_token, spreadsheet_id, name)
        headers = EVENT_HEADERS if name in DATA_SHEETS else PREF_HEADERS
        _populate(wb.create_sheet(name), values, headers)
    return wb


def save_workbook(wb: SimpleWorkbook, spreadsheet_id: str, access_token: str) -> None:
    for name in (*DATA_SHEETS, "Preferences"):
        rows = [list(row) for row in wb[name].iter_rows(min_row=1, values_only=True)]
        sheets_client.write_values(access_token, spreadsheet_id, name, rows)


def load_preferences(wb: SimpleWorkbook) -> Preferences:
    rows = list(wb["Preferences"].iter_rows(min_row=2, values_only=True))
    return Preferences.from_rows(rows)


def spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
