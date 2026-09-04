"""Confirms spreadsheet.py's business logic behaves identically against
SimpleWorkbook (the Google Sheets backend's in-memory grid) as it does
against a real openpyxl Workbook — this is the parity that lets sheets_store
reuse spreadsheet.py unchanged."""
from __future__ import annotations

import datetime as dt

from events_pipeline import spreadsheet
from events_pipeline.categorize import CategorizedEvent
from events_pipeline.simple_grid import SimpleWorkbook


def _new_simple_workbook() -> SimpleWorkbook:
    wb = SimpleWorkbook()
    for name, headers in (
        ("Events", spreadsheet.EVENT_HEADERS),
        ("History", spreadsheet.EVENT_HEADERS),
        ("Preferences", spreadsheet.PREF_HEADERS),
    ):
        wb.create_sheet(name).append(headers)
    return wb


def _event(event_id, start="2099-01-01T00:00:00Z"):
    return CategorizedEvent(
        event_id=event_id,
        name=f"Event {event_id}",
        category="Concert",
        genre="Rock",
        venue="V",
        city="C",
        start=start,
        url="http://x",
        keywords=["rock"],
    )


def test_value_assignment_survives_property_setattr_override():
    wb = _new_simple_workbook()
    ws = wb["Events"]
    ws.append(["a"] * len(spreadsheet.EVENT_HEADERS))
    ws.cell(row=2, column=spreadsheet.COL_FEEDBACK).value = "Interested"
    assert ws.cell(row=2, column=spreadsheet.COL_FEEDBACK).value == "Interested"


def test_cosmetic_attribute_assignment_is_silently_accepted():
    wb = _new_simple_workbook()
    cell = wb["Events"].cell(row=1, column=1)
    cell.fill = "some-openpyxl-style-object"
    cell.font = "bold"
    # doesn't raise, and doesn't corrupt .value
    assert cell.value == "Event ID"


def test_full_pipeline_data_flow_matches_xlsx_backend():
    wb = _new_simple_workbook()
    spreadsheet.append_events(
        wb,
        [(_event("a"), 1.0, False), (_event("b", start="2020-01-01T00:00:00Z"), 1.0, True)],
        dt.date(2026, 1, 1),
    )
    assert spreadsheet.known_event_ids(wb) == {"a", "b"}

    moved = spreadsheet.move_past_events_to_history(wb, dt.date(2026, 6, 1))
    assert moved == 1
    assert {row[0] for row in wb["Events"].iter_rows(min_row=2, values_only=True)} == {"a"}
    assert {row[0] for row in wb["History"].iter_rows(min_row=2, values_only=True)} == {"b"}

    wb["Events"].cell(row=2, column=spreadsheet.COL_FEEDBACK).value = "Interested"
    pending = spreadsheet.pending_feedback_rows(wb)
    assert len(pending) == 1 and pending[0]["sheet"] == "Events"
    spreadsheet.mark_learned(wb, pending[0]["sheet"], pending[0]["row"], "Interested")
    assert spreadsheet.pending_feedback_rows(wb) == []

    candidates = spreadsheet.rows_needing_attendance_check(wb)
    assert len(candidates) == 1 and candidates[0]["sheet"] == "History"
    spreadsheet.apply_attendance_matches(wb, candidates)
    assert wb["History"].cell(row=2, column=spreadsheet.COL_FEEDBACK).value == "Attended"
    assert wb["History"].cell(row=2, column=spreadsheet.COL_FEEDBACK_SOURCE).value == spreadsheet.AUTO_FEEDBACK_SOURCE
