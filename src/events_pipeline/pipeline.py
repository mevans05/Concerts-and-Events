"""Orchestrates one daily run: learn from feedback, then fetch and score
new events, then write everything back to the workbook."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass

from . import spreadsheet
from .categorize import CategorizedEvent, categorize_event, extract_keywords
from .config import Config, get_api_key, load_config
from .fetch import fetch_raw_events
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
    used_mock_data: bool


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
    pending = spreadsheet.pending_feedback_rows(wb)
    for row in pending:
        event = _reconstruct_event_for_learning(row)
        prefs.update(event, row["feedback"], config.learning_rate)
        spreadsheet.mark_learned(wb, row["row"], row["feedback"])
    if pending:
        prefs.save(preferences_path)
        log.info("Learned from %d feedback update(s)", len(pending))

    api_key = get_api_key()
    used_mock = mock or not api_key
    if used_mock:
        log.warning(
            "No TICKETMASTER_API_KEY set (or --mock passed) — using sample fixture events "
            "instead of live data. Set the env var / GitHub secret for real results."
        )
        raw_events = _load_mock_events()
    else:
        raw_events = fetch_raw_events(config, api_key)

    known_ids = spreadsheet.known_event_ids(wb)
    categorized = [categorize_event(r) for r in raw_events]
    candidates = [
        e for e in categorized if e.event_id not in known_ids and config.category_enabled(e.category)
    ]

    scored = [(e, prefs.score(e)) for e in candidates]
    scored = [pair for pair in scored if pair[1] >= config.min_score_threshold]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    scored = scored[: config.max_daily_recommendations]

    spreadsheet.append_events(wb, scored, today)
    spreadsheet.write_preferences_sheet(wb, prefs)
    spreadsheet.save_workbook(wb, workbook_path)
    if not pending:
        prefs.save(preferences_path)

    return RunSummary(
        feedback_processed=len(pending),
        events_moved_to_history=moved,
        new_events_fetched=len(candidates),
        new_events_recommended=len(scored),
        used_mock_data=used_mock,
    )
