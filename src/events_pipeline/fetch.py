"""Ticketmaster Discovery API client.

Free API key: https://developer.ticketmaster.com/
Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
"""
from __future__ import annotations

import datetime as dt
import logging
import time

import requests

from .config import Config

log = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MAX_PAGES = 5  # safety cap: 1000 events per query is plenty for a daily digest
REQUEST_TIMEOUT = 15

# One query per classification keeps results relevant; a broad keyword query
# on top catches "Brewery/Beer" and similar events Ticketmaster files under
# "Miscellaneous" instead of a dedicated segment.
CLASSIFICATION_QUERIES = ["Music", "Arts & Theatre", "Sports", "Miscellaneous"]
KEYWORD_QUERIES = ["beer festival", "brewery", "rugby"]


class TicketmasterError(RuntimeError):
    pass


def _date_window(lookahead_days: int) -> tuple[str, str]:
    now = dt.datetime.utcnow()
    end = now + dt.timedelta(days=lookahead_days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return now.strftime(fmt), end.strftime(fmt)


def _base_params(config: Config, api_key: str) -> dict:
    start, end = _date_window(config.lookahead_days)
    loc = config.location
    params = {
        "apikey": api_key,
        "countryCode": loc.country_code,
        "radius": loc.radius,
        "unit": loc.unit,
        "startDateTime": start,
        "endDateTime": end,
        "size": PAGE_SIZE,
        "sort": "date,asc",
    }
    # postalCode alone is enough for Ticketmaster to geocode a search center
    # and sidesteps city-name collisions (there's a Franklin in a dozen
    # states) — prefer it whenever it's set, falling back to city otherwise.
    if loc.postal_code:
        params["postalCode"] = loc.postal_code
    else:
        params["city"] = loc.city
    if loc.state_code:
        params["stateCode"] = loc.state_code
    return params


def _paged_fetch(session: requests.Session, params: dict) -> list[dict]:
    events: list[dict] = []
    page = 0
    while page < MAX_PAGES:
        params["page"] = page
        resp = session.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 429:
            log.warning("Ticketmaster rate limit hit, backing off")
            time.sleep(2)
            continue
        if not resp.ok:
            log.warning("Ticketmaster request failed (%s): %s", resp.status_code, resp.text[:300])
            break
        payload = resp.json()
        batch = (payload.get("_embedded") or {}).get("events", [])
        events.extend(batch)
        total_pages = (payload.get("page") or {}).get("totalPages", 1)
        page += 1
        if page >= total_pages:
            break
    return events


def fetch_raw_events(config: Config, api_key: str) -> list[dict]:
    """Returns raw (deduped by event id) Ticketmaster event dicts."""
    session = requests.Session()
    by_id: dict[str, dict] = {}

    for classification in CLASSIFICATION_QUERIES:
        params = _base_params(config, api_key)
        params["classificationName"] = classification
        for event in _paged_fetch(session, params):
            by_id[event.get("id")] = event

    for keyword in KEYWORD_QUERIES:
        params = _base_params(config, api_key)
        params["keyword"] = keyword
        for event in _paged_fetch(session, params):
            by_id[event.get("id")] = event

    return list(by_id.values())
