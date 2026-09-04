import datetime as dt

from events_pipeline.ical_feeds import _parse_events

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:brew-1@example.com
SUMMARY:Riverside Brewery Oktoberfest Tap Takeover
DTSTART:20260915T180000Z
DTEND:20260915T220000Z
LOCATION:Riverside Brewery, Denver
DESCRIPTION:Come try our fall seasonal brews
END:VEVENT
BEGIN:VEVENT
UID:brew-2@example.com
SUMMARY:Out of window event
DTSTART:20200101T180000Z
END:VEVENT
END:VCALENDAR
"""


def test_parses_vevent_within_window():
    feed_config = {"url": "https://example.com/feed.ics", "name": "riverside-brewery", "category_hint": "Brewery/Beer"}
    events = _parse_events(SAMPLE_ICS, feed_config, dt.date(2026, 9, 1), dt.date(2026, 10, 1))
    assert len(events) == 1
    event = events[0]
    assert event.source_id == "ics:riverside-brewery:brew-1@example.com"
    assert event.name == "Riverside Brewery Oktoberfest Tap Takeover"
    assert event.venue == "Riverside Brewery, Denver"
    assert event.category_hint == "Brewery/Beer"
    assert event.start.startswith("2026-09-15T18:00:00")
    assert event.end.startswith("2026-09-15T22:00:00")


def test_events_outside_window_are_excluded():
    feed_config = {"url": "https://example.com/feed.ics"}
    events = _parse_events(SAMPLE_ICS, feed_config, dt.date(2026, 9, 1), dt.date(2026, 10, 1))
    assert all("out-of-window" not in e.source_id for e in events)
    assert len(events) == 1


def test_feed_name_falls_back_to_slugified_url():
    feed_config = {"url": "https://example.com/venues/Riverside Brewery!.ics"}
    events = _parse_events(SAMPLE_ICS, feed_config, dt.date(2026, 9, 1), dt.date(2026, 10, 1))
    assert events[0].source_id.startswith("ics:https-example-com-venues-riverside-brewe")
