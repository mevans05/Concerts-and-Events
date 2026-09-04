import datetime as dt

from events_pipeline.google_auth import credentials_from_env
from events_pipeline.google_calendar import BusyInterval, event_overlaps_busy


def _busy(start_hour, end_hour, day=15):
    return BusyInterval(
        start=dt.datetime(2026, 9, day, start_hour, 0, tzinfo=dt.timezone.utc),
        end=dt.datetime(2026, 9, day, end_hour, 0, tzinfo=dt.timezone.utc),
    )


def test_overlapping_event_flagged_as_conflict():
    busy = [_busy(17, 19)]
    assert event_overlaps_busy("2026-09-15T18:00:00Z", "2026-09-15T22:00:00Z", busy) is True


def test_non_overlapping_event_not_flagged():
    busy = [_busy(17, 19)]
    assert event_overlaps_busy("2026-09-16T18:00:00Z", "2026-09-16T22:00:00Z", busy) is False


def test_missing_end_time_assumes_default_duration_and_can_still_conflict():
    busy = [_busy(19, 20)]
    assert event_overlaps_busy("2026-09-15T18:00:00Z", None, busy) is True


def test_buffer_widens_conflict_window():
    busy = [_busy(20, 21)]
    assert event_overlaps_busy("2026-09-15T18:00:00Z", "2026-09-15T19:45:00Z", busy, buffer_minutes=0) is False
    assert event_overlaps_busy("2026-09-15T18:00:00Z", "2026-09-15T19:45:00Z", busy, buffer_minutes=30) is True


def test_date_only_start_cannot_be_compared():
    busy = [_busy(0, 23, day=15)]
    assert event_overlaps_busy("2026-09-15", None, busy) is False


def test_credentials_from_env_requires_all_three(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    assert credentials_from_env() is None

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    assert credentials_from_env() is None

    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "token")
    creds = credentials_from_env()
    assert creds == {"client_id": "id", "client_secret": "secret", "refresh_token": "token"}
