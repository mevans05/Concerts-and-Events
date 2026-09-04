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
    spreadsheet.append_events(wb, [(_event("a"), 1.5, False)], dt.date(2026, 1, 1))
    spreadsheet.save_workbook(wb, path)

    wb2 = spreadsheet.open_workbook(path)
    assert spreadsheet.known_event_ids(wb2) == {"a"}


def test_append_records_calendar_conflict(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(
        wb,
        [(_event("a"), 1.0, True), (_event("b"), 1.0, False)],
        dt.date(2026, 1, 1),
    )
    ws = wb["Events"]
    rows = {row[spreadsheet.COL_EVENT_ID - 1]: row for row in ws.iter_rows(min_row=2, values_only=True)}
    assert rows["a"][spreadsheet.COL_CONFLICT - 1] == "Yes"
    assert rows["b"][spreadsheet.COL_CONFLICT - 1] is None


def test_move_past_events_to_history(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    today = dt.date(2026, 6, 1)
    spreadsheet.append_events(
        wb,
        [
            (_event("past", start="2026-01-01T00:00:00Z"), 1.0, False),
            (_event("future", start="2026-12-01T00:00:00Z"), 1.0, False),
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
    spreadsheet.append_events(wb, [(_event("a"), 1.0, False)], dt.date(2026, 1, 1))
    ws = wb["Events"]
    ws.cell(row=2, column=spreadsheet.COL_FEEDBACK).value = "Interested"

    pending = spreadsheet.pending_feedback_rows(wb)
    assert len(pending) == 1
    assert pending[0]["event_id"] == "a"
    assert pending[0]["sheet"] == "Events"

    spreadsheet.mark_learned(wb, pending[0]["sheet"], pending[0]["row"], "Interested")
    assert spreadsheet.pending_feedback_rows(wb) == []


def test_pending_feedback_rows_covers_history_sheet(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(wb, [(_event("a", start="2020-01-01T00:00:00Z"), 1.0, False)], dt.date(2026, 1, 1))
    spreadsheet.move_past_events_to_history(wb, dt.date(2026, 1, 1))
    ws = wb["History"]
    ws.cell(row=2, column=spreadsheet.COL_FEEDBACK).value = "Attended"

    pending = spreadsheet.pending_feedback_rows(wb)
    assert len(pending) == 1
    assert pending[0]["sheet"] == "History"


def test_rows_needing_attendance_check_excludes_rows_with_feedback(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(
        wb,
        [(_event("a", start="2026-03-01T00:00:00Z"), 1.0, False), (_event("b", start="2026-03-02T00:00:00Z"), 1.0, False)],
        dt.date(2026, 1, 1),
    )
    wb["Events"].cell(row=2, column=spreadsheet.COL_FEEDBACK).value = "Interested"

    candidates = spreadsheet.rows_needing_attendance_check(wb)
    assert len(candidates) == 1
    assert candidates[0]["name"] == "Event b"
    assert candidates[0]["event_date"] == dt.date(2026, 3, 2)


def test_apply_attendance_matches_sets_feedback_and_source(tmp_path):
    path = os.path.join(tmp_path, "events.xlsx")
    wb = spreadsheet.open_workbook(path)
    spreadsheet.append_events(wb, [(_event("a"), 1.0, False)], dt.date(2026, 1, 1))

    spreadsheet.apply_attendance_matches(wb, [{"sheet": "Events", "row": 2}])

    ws = wb["Events"]
    assert ws.cell(row=2, column=spreadsheet.COL_FEEDBACK).value == "Attended"
    assert ws.cell(row=2, column=spreadsheet.COL_FEEDBACK_SOURCE).value == spreadsheet.AUTO_FEEDBACK_SOURCE
