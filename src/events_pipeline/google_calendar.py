"""Personal Google Calendar integration, used for two things:

  1. Conflict flagging — is a recommended event's time already booked?
  2. Attendance learning — did you actually go to something we
     recommended? (matched by title similarity + date against your past
     calendar events, see attendance.py)

Talks to the Calendar REST API directly with `requests` rather than
pulling in the full google-api-python-client SDK, to keep the dependency
footprint small. Needs a one-time OAuth setup — see
scripts/google_oauth_setup.py and the README — after which it runs
unattended using a stored refresh token.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
EVENTS_URL_TMPL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
REQUEST_TIMEOUT = 15
DEFAULT_EVENT_DURATION = dt.timedelta(hours=2)


@dataclass
class BusyInterval:
    start: dt.datetime
    end: dt.datetime


@dataclass
class PastCalendarEvent:
    name: str
    start: dt.datetime | None
    location: str | None


class GoogleCalendarUnavailable(RuntimeError):
    pass


def credentials_from_env() -> dict | None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}


def get_access_token(creds: dict) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleCalendarUnavailable(f"Token refresh failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["access_token"]


def _parse_rfc3339(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_busy_intervals(access_token: str, calendar_id: str, time_min: dt.datetime, time_max: dt.datetime) -> list[BusyInterval]:
    resp = requests.post(
        FREEBUSY_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": calendar_id}],
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleCalendarUnavailable(f"freeBusy query failed ({resp.status_code}): {resp.text[:300]}")
    payload = resp.json()
    busy_raw = (payload.get("calendars", {}).get(calendar_id, {}) or {}).get("busy", [])
    return [BusyInterval(start=_parse_rfc3339(b["start"]), end=_parse_rfc3339(b["end"])) for b in busy_raw]


def fetch_past_events(access_token: str, calendar_id: str, time_min: dt.datetime, time_max: dt.datetime) -> list[PastCalendarEvent]:
    events: list[PastCalendarEvent] = []
    params = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 250,
    }
    url = EVENTS_URL_TMPL.format(calendar_id=calendar_id)
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=REQUEST_TIMEOUT)
    if not resp.ok:
        raise GoogleCalendarUnavailable(f"events.list failed ({resp.status_code}): {resp.text[:300]}")
    for item in resp.json().get("items", []):
        start_raw = (item.get("start") or {}).get("dateTime") or (item.get("start") or {}).get("date")
        start = _parse_rfc3339(start_raw) if start_raw and "T" in start_raw else None
        events.append(
            PastCalendarEvent(
                name=item.get("summary", ""),
                start=start,
                location=item.get("location"),
            )
        )
    return events


def event_overlaps_busy(
    start_iso: str | None,
    end_iso: str | None,
    busy: list[BusyInterval],
    buffer_minutes: int = 0,
) -> bool:
    """Date-only starts (no time component) can't be reliably compared
    against timed calendar entries, so they're treated as non-conflicting."""
    if not start_iso or "T" not in str(start_iso):
        return False
    start = _parse_rfc3339(start_iso)
    end = _parse_rfc3339(end_iso) if end_iso and "T" in str(end_iso) else start + DEFAULT_EVENT_DURATION
    buffer = dt.timedelta(minutes=buffer_minutes)
    start -= buffer
    end += buffer
    for interval in busy:
        if start < interval.end and end > interval.start:
            return True
    return False
