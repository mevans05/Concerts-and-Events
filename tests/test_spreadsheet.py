import datetime as dt
import os

from events_pipeline import spreadsheet
from events_pipeline.categorize import CategorizedEvent


def _event(event_id, category="Concert", start="2099-01-01T00:00:00Z"):
    return CategorizedEvent(
        event_id=event_id,
        name=f"Event {event_id}",
        category=category,
        genre="Rock",
        venue="Venue",
        city="Denver",
        start=start,
        url="https://example.com",
        keywords=["rock"],
    )


def test_new_workbook_has_expected_sheets(tmp_path):
    wb = spreadsheet.open_workbook(os.path.join(tmp_path, "new.xlsx"))
    assert set(wb.sheetnames) == {"Events", "History", "Preferences"}
    assert [c.value for c in wb["Events"][1]] == spreadsheet.EVENT_HEADERS


def test_append_and_dedupe(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(wb, [(_event("a"), 1.5)], dt.date(2026, 1, 1))
    spreadsheet.save_workbook(wb, path)

    wb2 = spreadsheet.open_workbook(path)
    assert spreadsheet.known_event_ids(wb2) == {"a"}


def test_move_past_events_to_history(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    today = dt.date(2026, 6, 1)
    spreadsheet.append_events(
        wb,
        [
            (_event("past", start="2026-01-01T00:00:00Z"), 1.0),
            (_event("future", start="2026-12-01T00:00:00Z"), 1.0),
        ],
        today,
    )
    moved = spreadsheet.move_past_events_to_history(wb, today)
    assert moved == 1
    assert spreadsheet.known_event_ids(wb) == {"past", "future"}
    history_ids = {row[0] for row in wb["History"].iter_rows(min_row=2, values_only=True)}
    events_ids = {row[0] for row in wb["Events"].iter_rows(min_row=2, values_only=True)}
    assert history_ids == {"past"}
    assert events_ids == {"future"}


def test_pending_feedback_rows_only_returns_unlearned(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(wb, [(_event("a"), 1.0)], dt.date(2026, 1, 1))
    ws = wb["Events"]
    ws.cell(row=2, column=11).value = "Interested"  # Feedback

    pending = spreadsheet.pending_feedback_rows(wb)
    assert len(pending) == 1
    assert pending[0]["event_id"] == "a"

    spreadsheet.mark_learned(wb, pending[0]["row"], "Interested")
    assert spreadsheet.pending_feedback_rows(wb) == []
