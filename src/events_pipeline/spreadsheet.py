"""Reads and writes the events workbook.

Sheets:
  Events       - upcoming recommendations; you fill in the Feedback column.
  History      - events whose date has passed, moved out of Events to keep
                  the active list short. Feedback already learned from these
                  stays intact for the record.
  Preferences  - a read-only dump of the current learned weights, rewritten
                  every run so you can see what the model has picked up.

Column A (Event ID) and column L (Learned As) are internal bookkeeping:
Event ID is Ticketmaster's id, used to avoid ever recommending the same
event twice. Learned As records the Feedback value already folded into the
preference model, so we only learn from a feedback change once.
"""
from __future__ import annotations

import datetime as dt
import os

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .categorize import CategorizedEvent
from .preferences import Preferences

FEEDBACK_OPTIONS = ["Interested", "Maybe", "Not Interested", "Attended"]

EVENT_HEADERS = [
    "Event ID",
    "Date Added",
    "Event Name",
    "Category",
    "Event Date",
    "Venue",
    "City",
    "Genre",
    "Score",
    "Ticket URL",
    "Feedback",
    "Learned As",
]

PREF_HEADERS = ["Type", "Key", "Weight"]

HEADER_FILL = PatternFill(start_color="FF2F5496", end_color="FF2F5496", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFFFF")


def _style_header(ws, ncols: int) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}1"


def _new_workbook() -> Workbook:
    wb = Workbook()
    events_ws = wb.active
    events_ws.title = "Events"
    events_ws.append(EVENT_HEADERS)
    _style_header(events_ws, len(EVENT_HEADERS))
    events_ws.column_dimensions["A"].hidden = True
    events_ws.column_dimensions["L"].hidden = True
    for letter, width in zip("BCDEFGHIJK", [12, 42, 12, 18, 26, 20, 16, 8, 40, 15]):
        events_ws.column_dimensions[letter].width = width

    history_ws = wb.create_sheet("History")
    history_ws.append(EVENT_HEADERS)
    _style_header(history_ws, len(EVENT_HEADERS))
    history_ws.column_dimensions["A"].hidden = True
    history_ws.column_dimensions["L"].hidden = True

    prefs_ws = wb.create_sheet("Preferences")
    prefs_ws.append(PREF_HEADERS)
    _style_header(prefs_ws, len(PREF_HEADERS))

    _apply_feedback_validation(events_ws)
    return wb


def _apply_feedback_validation(ws) -> None:
    dv = DataValidation(
        type="list",
        formula1=f'"{",".join(FEEDBACK_OPTIONS)}"',
        allow_blank=True,
        showDropDown=False,
    )
    ws.add_data_validation(dv)
    # Generous range so the dropdown still applies to rows added later.
    dv.add(f"K2:K{max(ws.max_row, 2) + 2000}")


def open_workbook(path: str) -> Workbook:
    if os.path.exists(path):
        wb = load_workbook(path)
        if "Events" not in wb.sheetnames or "History" not in wb.sheetnames or "Preferences" not in wb.sheetnames:
            raise ValueError(f"{path} exists but is missing expected sheets (Events/History/Preferences)")
        return wb
    return _new_workbook()


def save_workbook(wb: Workbook, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb.save(path)


def known_event_ids(wb: Workbook) -> set[str]:
    ids: set[str] = set()
    for sheet_name in ("Events", "History"):
        ws = wb[sheet_name]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                ids.add(str(row[0]))
    return ids


def pending_feedback_rows(wb: Workbook) -> list[dict]:
    """Rows in Events where Feedback differs from the last-learned value."""
    ws = wb["Events"]
    pending = []
    for row_idx in range(2, ws.max_row + 1):
        event_id = ws.cell(row=row_idx, column=1).value
        feedback = ws.cell(row=row_idx, column=11).value
        learned_as = ws.cell(row=row_idx, column=12).value
        if not event_id or not feedback:
            continue
        if feedback == learned_as:
            continue
        pending.append(
            {
                "row": row_idx,
                "event_id": str(event_id),
                "name": ws.cell(row=row_idx, column=3).value,
                "category": ws.cell(row=row_idx, column=4).value,
                "genre": ws.cell(row=row_idx, column=8).value,
                "venue": ws.cell(row=row_idx, column=6).value,
                "feedback": feedback,
            }
        )
    return pending


def mark_learned(wb: Workbook, row: int, feedback_value: str) -> None:
    wb["Events"].cell(row=row, column=12).value = feedback_value


def append_events(wb: Workbook, scored_events: list[tuple[CategorizedEvent, float]], today: dt.date) -> None:
    ws = wb["Events"]
    for event, score in scored_events:
        ws.append(
            [
                event.event_id,
                today.isoformat(),
                event.name,
                event.category,
                event.start,
                event.venue,
                event.city,
                event.genre,
                score,
                event.url,
                None,
                None,
            ]
        )
    _apply_feedback_validation(ws)


def move_past_events_to_history(wb: Workbook, today: dt.date) -> int:
    events_ws = wb["Events"]
    history_ws = wb["History"]
    keep_rows = [EVENT_HEADERS]
    moved = 0
    for row in events_ws.iter_rows(min_row=2, values_only=True):
        event_date_raw = row[4]
        is_past = False
        if event_date_raw:
            try:
                event_date = dt.datetime.fromisoformat(str(event_date_raw).replace("Z", "+00:00")).date()
                is_past = event_date < today
            except ValueError:
                is_past = False
        if is_past:
            history_ws.append(list(row))
            moved += 1
        else:
            keep_rows.append(list(row))

    events_ws.delete_rows(1, events_ws.max_row)
    for row in keep_rows:
        events_ws.append(row)
    _style_header(events_ws, len(EVENT_HEADERS))
    events_ws.column_dimensions["A"].hidden = True
    events_ws.column_dimensions["L"].hidden = True
    _apply_feedback_validation(events_ws)
    return moved


def write_preferences_sheet(wb: Workbook, prefs: Preferences) -> None:
    ws = wb["Preferences"]
    ws.delete_rows(1, ws.max_row)
    ws.append(PREF_HEADERS)
    _style_header(ws, len(PREF_HEADERS))
    rows = []
    for key, weight in sorted(prefs.categories.items()):
        rows.append(("Category", key, weight))
    for key, weight in sorted(prefs.genres.items()):
        rows.append(("Genre", key, weight))
    for key, weight in sorted(prefs.venues.items()):
        rows.append(("Venue", key, weight))
    for key, weight in sorted(prefs.keywords.items(), key=lambda kv: -kv[1]):
        rows.append(("Keyword", key, weight))
    for row in rows:
        ws.append(row)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 10
