import datetime as dt

from events_pipeline.attendance import match_attended_events
from events_pipeline.google_calendar import PastCalendarEvent


def _row(sheet, row, name, event_date):
    return {"sheet": sheet, "row": row, "name": name, "event_date": event_date}


def test_matches_similar_title_same_day():
    past = [PastCalendarEvent(name="Denver Rugby Sevens Invitational Match", start=dt.datetime(2026, 9, 21, 18, 0, tzinfo=dt.timezone.utc), location=None)]
    candidates = [
        _row("Events", 2, "Denver Rugby Sevens Invitational", dt.date(2026, 9, 21)),
        _row("Events", 3, "Comedy Night Downtown", dt.date(2026, 9, 21)),
    ]
    matches = match_attended_events(past, candidates)
    assert len(matches) == 1
    assert matches[0]["row"] == 2


def test_no_match_when_titles_dissimilar():
    past = [PastCalendarEvent(name="Dentist Appointment", start=dt.datetime(2026, 9, 21, 9, 0, tzinfo=dt.timezone.utc), location=None)]
    candidates = [_row("Events", 2, "Denver Rugby Sevens Invitational", dt.date(2026, 9, 21))]
    assert match_attended_events(past, candidates) == []


def test_no_match_outside_date_tolerance():
    past = [PastCalendarEvent(name="Denver Rugby Sevens Invitational", start=dt.datetime(2026, 9, 25, 18, 0, tzinfo=dt.timezone.utc), location=None)]
    candidates = [_row("Events", 2, "Denver Rugby Sevens Invitational", dt.date(2026, 9, 21))]
    assert match_attended_events(past, candidates) == []


def test_each_row_matched_at_most_once():
    past = [
        PastCalendarEvent(name="Denver Rugby Sevens", start=dt.datetime(2026, 9, 21, 12, 0, tzinfo=dt.timezone.utc), location=None),
        PastCalendarEvent(name="Denver Rugby Sevens Finals", start=dt.datetime(2026, 9, 21, 18, 0, tzinfo=dt.timezone.utc), location=None),
    ]
    candidates = [_row("Events", 2, "Denver Rugby Sevens Invitational", dt.date(2026, 9, 21))]
    matches = match_attended_events(past, candidates)
    assert len(matches) == 1


def test_ignores_past_events_without_a_start_time():
    past = [PastCalendarEvent(name="Denver Rugby Sevens Invitational", start=None, location=None)]
    candidates = [_row("Events", 2, "Denver Rugby Sevens Invitational", dt.date(2026, 9, 21))]
    assert match_attended_events(past, candidates) == []
