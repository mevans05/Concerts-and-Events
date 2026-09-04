"""Pulls events from public iCal (.ics) feeds you subscribe to in
config.yaml — e.g. a venue's published schedule, a team's fixture
calendar, a public Google Calendar's "Secret address in iCal format".
No authentication needed; these are the same feeds you'd add to any
calendar app via "Subscribe by URL".

Recurring events (RRULE) are only read at their first occurrence — good
enough for one-off announcements, not a full recurrence expander.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

import requests
from icalendar import Calendar

from .categorize import NormalizedRawEvent

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def _feed_name(feed_config: dict) -> str:
    name = feed_config.get("name")
    if name:
        return _slugify(name)
    return _slugify(feed_config["url"])[:40]


def _to_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def _within_window(start_value, window_start: dt.date, window_end: dt.date) -> bool:
    if start_value is None:
        return False
    start_date = start_value.date() if isinstance(start_value, dt.datetime) else start_value
    return window_start <= start_date <= window_end


def _parse_events(ics_text: str, feed_config: dict, window_start: dt.date, window_end: dt.date) -> list[NormalizedRawEvent]:
    feed_name = _feed_name(feed_config)
    category_hint = feed_config.get("category_hint")
    events: list[NormalizedRawEvent] = []

    calendar = Calendar.from_ical(ics_text)
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        dtstart_prop = component.get("dtstart")
        if dtstart_prop is None:
            continue
        start_value = dtstart_prop.dt
        if not _within_window(start_value, window_start, window_end):
            continue

        uid = str(component.get("uid") or component.get("summary") or "")
        name = str(component.get("summary") or "Untitled event")
        location = component.get("location")
        description = str(component.get("description") or "")
        dtend_prop = component.get("dtend")

        events.append(
            NormalizedRawEvent(
                source_id=f"ics:{feed_name}:{uid}",
                name=name,
                start=_to_iso(start_value),
                end=_to_iso(dtend_prop.dt) if dtend_prop else None,
                url=str(component.get("url")) if component.get("url") else feed_config.get("url"),
                venue=str(location) if location else None,
                city=None,
                description=description,
                category_hint=category_hint,
            )
        )
    return events


def fetch_feed_events(feed_config: dict, lookahead_days: int) -> list[NormalizedRawEvent]:
    url = feed_config["url"]
    window_start = dt.date.today()
    window_end = window_start + dt.timedelta(days=lookahead_days)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _parse_events(resp.text, feed_config, window_start, window_end)
    except Exception as exc:  # a bad/unreachable feed shouldn't take down the whole run
        log.warning("Skipping public feed %s (%s)", url, exc)
        return []


def fetch_all_public_feeds(feed_configs: list[dict], lookahead_days: int) -> list[NormalizedRawEvent]:
    events: list[NormalizedRawEvent] = []
    for feed_config in feed_configs:
        events.extend(fetch_feed_events(feed_config, lookahead_days))
    return events
