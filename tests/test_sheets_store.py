"""Exercises sheets_store.py against a fake in-memory Sheets API (no
network), verifying: business logic from spreadsheet.py works unchanged
against the Sheets-backed SimpleWorkbook, and that a full
open -> mutate -> save -> reopen cycle round-trips correctly, including
Preferences living entirely in the Preferences tab (no local JSON file)."""
from __future__ import annotations

import datetime as dt

import pytest

from events_pipeline import sheets_client, sheets_store, spreadsheet
from events_pipeline.categorize import CategorizedEvent
from events_pipeline.preferences import Preferences


@pytest.fixture
def fake_sheets(monkeypatch):
    db = {"Events": [], "History": [], "Preferences": []}

    def fake_ensure_tabs_exist(token, spreadsheet_id):
        return {"Events": 1, "History": 2, "Preferences": 3}

    def fake_get_values(token, spreadsheet_id, name):
        return [list(row) for row in db[name]]

    def fake_write_values(token, spreadsheet_id, name, rows):
        db[name] = [list(row) for row in rows]

    monkeypatch.setattr(sheets_client, "ensure_tabs_exist", fake_ensure_tabs_exist)
    monkeypatch.setattr(sheets_client, "get_values", fake_get_values)
    monkeypatch.setattr(sheets_client, "write_values", fake_write_values)
    return db


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


def test_open_workbook_on_empty_tabs_seeds_headers(fake_sheets):
    wb = sheets_store.open_workbook("sid", "token")
    assert wb["Events"].rows[0] == spreadsheet.EVENT_HEADERS
    assert wb["Preferences"].rows[0] == spreadsheet.PREF_HEADERS


def test_save_then_reopen_round_trips_values(fake_sheets):
    wb = sheets_store.open_workbook("sid", "token")
    spreadsheet.append_events(wb, [(_event("a"), 1.0, False)], dt.date(2026, 1, 1))
    prefs = Preferences()
    prefs.update(_event("a"), "Interested", 0.15)
    spreadsheet.write_preferences_sheet(wb, prefs)
    sheets_store.save_workbook(wb, "sid", "token")

    wb2 = sheets_store.open_workbook("sid", "token")
    assert spreadsheet.known_event_ids(wb2) == {"a"}
    reloaded_prefs = sheets_store.load_preferences(wb2)
    assert reloaded_prefs.categories == prefs.categories


def test_user_edited_feedback_is_picked_up_and_learned(fake_sheets):
    wb = sheets_store.open_workbook("sid", "token")
    spreadsheet.append_events(wb, [(_event("a"), 1.0, False)], dt.date(2026, 1, 1))
    sheets_store.save_workbook(wb, "sid", "token")

    # Simulate the user typing "Interested" directly into the live sheet.
    fake_sheets["Events"][1][spreadsheet.COL_FEEDBACK - 1] = "Interested"

    wb2 = sheets_store.open_workbook("sid", "token")
    pending = spreadsheet.pending_feedback_rows(wb2)
    assert len(pending) == 1
    assert pending[0]["feedback"] == "Interested"

    prefs = sheets_store.load_preferences(wb2)
    prefs.update(_event(pending[0]["event_id"]), pending[0]["feedback"], 0.15)
    spreadsheet.mark_learned(wb2, pending[0]["sheet"], pending[0]["row"], pending[0]["feedback"])
    spreadsheet.write_preferences_sheet(wb2, prefs)
    sheets_store.save_workbook(wb2, "sid", "token")

    assert fake_sheets["Events"][1][spreadsheet.COL_LEARNED_AS - 1] == "Interested"
    assert prefs.categories["Concert"] > 1.0


def test_spreadsheet_url_format():
    assert sheets_store.spreadsheet_url("abc123") == "https://docs.google.com/spreadsheets/d/abc123/edit"
