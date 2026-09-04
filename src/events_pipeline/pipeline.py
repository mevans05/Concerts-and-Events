"""Orchestrates one daily run:

  1. Open the workbook — a live Google Sheet if google_sheets.enabled and
     credentials are available, otherwise the local data/events.xlsx file.
  2. Learn from any feedback (manual or calendar-inferred) since last run.
  3. If Google Calendar is enabled, check attendance on past recommendations
     against your real calendar (auto-feedback), then re-run step 2 for it.
  4. Fetch new candidate events (Ticketmaster + any public ICS feeds).
  5. Score, filter, conflict-flag against your calendar, and write the
     top picks back to the workbook.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass

from . import sheets_client, sheets_store, spreadsheet
from .attendance import match_attended_events
from .categorize import (
    CategorizedEvent,
    categorize_event,
    categorize_ticketmaster_raw,
    extract_keywords,
)
from .config import Config, get_ticketmaster_api_key, load_config
from .fetch import fetch_raw_events
from .google_auth import GoogleApiError, credentials_from_env, get_access_token
from .google_calendar import event_overlaps_busy, fetch_busy_intervals, fetch_past_events
from .ical_feeds import fetch_all_public_feeds
from .preferences import Preferences

log = logging.getLogger(__name__)

MOCK_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tests", "fixtures", "sample_events.json"
)
SHEET_ID_CACHE_PATH = "data/google_sheet_id.txt"


@dataclass
class RunSummary:
    feedback_processed: int
    events_moved_to_history: int
    new_events_fetched: int
    new_events_recommended: int
    conflicts_flagged: int
    attendance_auto_learned: int
    used_mock_data: bool
    google_calendar_active: bool
    google_sheets_active: bool
    workbook_location: str


def _load_mock_events() -> list[dict]:
    with open(MOCK_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _reconstruct_event_for_learning(row: dict) -> CategorizedEvent:
    """Feedback rows only store name/category/genre/venue in the sheet, so
    rebuild the keyword list the same way it was computed originally."""
    return CategorizedEvent(
        event_id=row["event_id"],
        name=row["name"] or "",
        category=row["category"] or "Other",
        genre=row["genre"],
        venue=row["venue"],
        city=None,
        start=None,
        url=None,
        keywords=extract_keywords(row["name"] or "", row["genre"]),
    )


def _learn_from_pending_feedback(wb, prefs: Preferences, config: Config) -> int:
    pending = spreadsheet.pending_feedback_rows(wb)
    for row in pending:
        event = _reconstruct_event_for_learning(row)
        prefs.update(event, row["feedback"], config.learning_rate)
        spreadsheet.mark_learned(wb, row["sheet"], row["row"], row["feedback"])
    return len(pending)


def _get_google_access_token(config: Config) -> str | None:
    if not (config.google_calendar.enabled or config.google_sheets.enabled):
        return None
    creds = credentials_from_env()
    if not creds:
        log.warning(
            "Google Calendar and/or Google Sheets is enabled in config.yaml but "
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN aren't all set — "
            "skipping those features this run. See scripts/google_oauth_setup.py."
        )
        return None
    try:
        return get_access_token(creds)
    except GoogleApiError as exc:
        log.warning("Google API unavailable this run: %s", exc)
        return None


def _resolve_spreadsheet_id(config: Config, access_token: str) -> str | None:
    if config.google_sheets.spreadsheet_id:
        return config.google_sheets.spreadsheet_id
    if os.path.exists(SHEET_ID_CACHE_PATH):
        with open(SHEET_ID_CACHE_PATH, "r", encoding="utf-8") as f:
            cached = f.read().strip()
        if cached:
            return cached
    try:
        created = sheets_client.create_spreadsheet(access_token, "Concerts & Events")
    except GoogleApiError as exc:
        log.warning("Couldn't create a Google Sheet this run: %s", exc)
        return None
    spreadsheet_id = created["spreadsheetId"]
    os.makedirs(os.path.dirname(SHEET_ID_CACHE_PATH) or ".", exist_ok=True)
    with open(SHEET_ID_CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(spreadsheet_id + "\n")
    url = created.get("spreadsheetUrl", sheets_store.spreadsheet_url(spreadsheet_id))
    log.warning("Created a new Google Sheet: %s (id cached in %s)", url, SHEET_ID_CACHE_PATH)
    return spreadsheet_id


def _run_attendance_matching(wb, prefs: Preferences, config: Config, access_token: str) -> int:
    gcal = config.google_calendar
    now = dt.datetime.now(dt.timezone.utc)
    time_min = now - dt.timedelta(days=gcal.attendance_lookback_days)
    try:
        past_events = fetch_past_events(access_token, gcal.calendar_id, time_min, now)
    except GoogleApiError as exc:
        log.warning("Skipping attendance learning this run: %s", exc)
        return 0

    candidates = spreadsheet.rows_needing_attendance_check(wb)
    matches = match_attended_events(past_events, candidates)
    if matches:
        spreadsheet.apply_attendance_matches(wb, matches)
        log.info("Matched %d past calendar event(s) to recommendations as Attended", len(matches))
    return _learn_from_pending_feedback(wb, prefs, config)


def _fetch_candidates(config: Config, mock: bool) -> tuple[list[CategorizedEvent], bool]:
    api_key = get_ticketmaster_api_key()
    used_mock = mock or not api_key
    if used_mock:
        log.warning(
            "No TICKETMASTER_API_KEY set (or --mock passed) — using sample fixture events "
            "instead of live data. Set the env var / GitHub secret for real results."
        )
        raw_events = _load_mock_events()
    else:
        raw_events = fetch_raw_events(config, api_key)
    categorized = [categorize_ticketmaster_raw(r) for r in raw_events]

    feed_events = fetch_all_public_feeds(config.google_calendar.public_feeds, config.lookahead_days)
    categorized.extend(categorize_event(e) for e in feed_events)
    return categorized, used_mock


def run(
    config_path: str = "config.yaml",
    workbook_path: str = "data/events.xlsx",
    preferences_path: str = "data/preferences.json",
    mock: bool = False,
) -> RunSummary:
    config: Config = load_config(config_path)
    today = dt.date.today()

    access_token = _get_google_access_token(config)
    calendar_active = bool(access_token and config.google_calendar.enabled)

    sheets_active = False
    spreadsheet_id = None
    if access_token and config.google_sheets.enabled:
        spreadsheet_id = _resolve_spreadsheet_id(config, access_token)
        sheets_active = spreadsheet_id is not None

    if sheets_active:
        wb = sheets_store.open_workbook(spreadsheet_id, access_token)
        prefs = sheets_store.load_preferences(wb)
        workbook_location = sheets_store.spreadsheet_url(spreadsheet_id)
    else:
        wb = spreadsheet.open_workbook(workbook_path)
        prefs = Preferences.load(preferences_path)
        workbook_location = workbook_path

    moved = spreadsheet.move_past_events_to_history(wb, today)
    feedback_processed = _learn_from_pending_feedback(wb, prefs, config)

    attendance_learned = 0
    if calendar_active and config.google_calendar.learn_from_past_events:
        attendance_learned = _run_attendance_matching(wb, prefs, config, access_token)
    if not sheets_active and (feedback_processed or attendance_learned):
        prefs.save(preferences_path)

    candidates, used_mock = _fetch_candidates(config, mock)

    known_ids = spreadsheet.known_event_ids(wb)
    new_candidates = [
        e for e in candidates if e.event_id not in known_ids and config.category_enabled(e.category)
    ]
    # a source can list the same event more than once (e.g. two overlapping
    # keyword searches); keep the first occurrence.
    deduped: dict[str, CategorizedEvent] = {}
    for event in new_candidates:
        deduped.setdefault(event.event_id, event)
    new_candidates = list(deduped.values())

    busy = []
    if calendar_active:
        gcal = config.google_calendar
        window_start = dt.datetime.now(dt.timezone.utc)
        window_end = window_start + dt.timedelta(days=config.lookahead_days)
        try:
            busy = fetch_busy_intervals(access_token, gcal.calendar_id, window_start, window_end)
        except GoogleApiError as exc:
            log.warning("Skipping conflict-checking this run: %s", exc)

    scored = []
    conflicts_flagged = 0
    for event in new_candidates:
        score = prefs.score(event)
        if score < config.min_score_threshold:
            continue
        has_conflict = bool(busy) and event_overlaps_busy(
            event.start, event.end, busy, config.google_calendar.conflict_buffer_minutes
        )
        if has_conflict:
            conflicts_flagged += 1
            if config.google_calendar.exclude_conflicts:
                continue
        scored.append((event, score, has_conflict))

    scored.sort(key=lambda triple: triple[1], reverse=True)
    scored = scored[: config.max_daily_recommendations]

    spreadsheet.append_events(wb, scored, today)
    spreadsheet.write_preferences_sheet(wb, prefs)

    if sheets_active:
        sheets_store.save_workbook(wb, spreadsheet_id, access_token)
    else:
        spreadsheet.save_workbook(wb, workbook_path)
        prefs.save(preferences_path)

    return RunSummary(
        feedback_processed=feedback_processed,
        events_moved_to_history=moved,
        new_events_fetched=len(new_candidates),
        new_events_recommended=len(scored),
        conflicts_flagged=conflicts_flagged,
        attendance_auto_learned=attendance_learned,
        used_mock_data=used_mock,
        google_calendar_active=calendar_active,
        google_sheets_active=sheets_active,
        workbook_location=workbook_location,
    )
