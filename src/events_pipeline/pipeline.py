"""Orchestrates one daily run:

  1. Learn from any feedback (manual or calendar-inferred) since last run.
  2. If Google Calendar is enabled, check attendance on past recommendations
     against your real calendar (auto-feedback), then re-run step 1 for it.
  3. Fetch new candidate events (Ticketmaster + any public ICS feeds).
  4. Score, filter, conflict-flag against your calendar, and write the
     top picks into the sheet.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass

from . import spreadsheet
from .attendance import match_attended_events
from .categorize import (
    CategorizedEvent,
    categorize_event,
    categorize_ticketmaster_raw,
    extract_keywords,
)
from .config import Config, get_ticketmaster_api_key, load_config
from .fetch import fetch_raw_events
from .google_calendar import (
    GoogleCalendarUnavailable,
    credentials_from_env,
    event_overlaps_busy,
    fetch_busy_intervals,
    fetch_past_events,
    get_access_token,
)
from .ical_feeds import fetch_all_public_feeds
from .preferences import Preferences

log = logging.getLogger(__name__)

MOCK_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tests", "fixtures", "sample_events.json"
)


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
    if not config.google_calendar.enabled:
        return None
    creds = credentials_from_env()
    if not creds:
        log.warning(
            "google_calendar.enabled is true but GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
            "GOOGLE_REFRESH_TOKEN aren't all set — skipping personal calendar features. "
            "See scripts/google_oauth_setup.py."
        )
        return None
    try:
        return get_access_token(creds)
    except GoogleCalendarUnavailable as exc:
        log.warning("Google Calendar unavailable this run: %s", exc)
        return None


def _run_attendance_matching(wb, prefs: Preferences, config: Config, access_token: str) -> int:
    gcal = config.google_calendar
    now = dt.datetime.now(dt.timezone.utc)
    time_min = now - dt.timedelta(days=gcal.attendance_lookback_days)
    try:
        past_events = fetch_past_events(access_token, gcal.calendar_id, time_min, now)
    except GoogleCalendarUnavailable as exc:
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
        categorized = [categorize_ticketmaster_raw(r) for r in raw_events]
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
    wb = spreadsheet.open_workbook(workbook_path)
    today = dt.date.today()

    moved = spreadsheet.move_past_events_to_history(wb, today)

    prefs = Preferences.load(preferences_path)
    feedback_processed = _learn_from_pending_feedback(wb, prefs, config)

    access_token = _get_google_access_token(config)
    attendance_learned = 0
    if access_token and config.google_calendar.learn_from_past_events:
        attendance_learned = _run_attendance_matching(wb, prefs, config, access_token)
    if feedback_processed or attendance_learned:
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
    if access_token:
        gcal = config.google_calendar
        window_start = dt.datetime.now(dt.timezone.utc)
        window_end = window_start + dt.timedelta(days=config.lookahead_days)
        try:
            busy = fetch_busy_intervals(access_token, gcal.calendar_id, window_start, window_end)
        except GoogleCalendarUnavailable as exc:
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
    spreadsheet.save_workbook(wb, workbook_path)

    return RunSummary(
        feedback_processed=feedback_processed,
        events_moved_to_history=moved,
        new_events_fetched=len(new_candidates),
        new_events_recommended=len(scored),
        conflicts_flagged=conflicts_flagged,
        attendance_auto_learned=attendance_learned,
        used_mock_data=used_mock,
        google_calendar_active=bool(access_token),
    )
