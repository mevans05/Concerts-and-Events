"""Matches your past Google Calendar events against events we already
recommended, so attending something counts as implicit "Attended"
feedback without you having to fill in the sheet by hand.

Matching is deliberately conservative: same calendar day (+/- 1 day, to
absorb timezone slop) and a token-overlap title similarity above a
threshold. It only ever proposes a match for rows that don't already have
feedback, and never overrides feedback you entered yourself.
"""
from __future__ import annotations

import re

from .google_calendar import PastCalendarEvent

SIMILARITY_THRESHOLD = 0.5
DATE_TOLERANCE_DAYS = 1

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _title_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_attended_events(past_events: list[PastCalendarEvent], candidate_rows: list[dict]) -> list[dict]:
    """`candidate_rows` items need: sheet, row, name, event_date (a date or
    None). Returns the subset of candidate_rows judged attended, each used
    at most once."""
    matched_keys: set[tuple[str, int]] = set()
    matches: list[dict] = []

    for past in past_events:
        if past.start is None:
            continue
        past_date = past.start.date()

        best_row = None
        best_score = 0.0
        for row in candidate_rows:
            key = (row["sheet"], row["row"])
            if key in matched_keys:
                continue
            row_date = row["event_date"]
            if row_date is None or abs((row_date - past_date).days) > DATE_TOLERANCE_DAYS:
                continue
            score = _title_similarity(past.name, row["name"])
            if score > best_score:
                best_score = score
                best_row = row

        if best_row is not None and best_score >= SIMILARITY_THRESHOLD:
            matched_keys.add((best_row["sheet"], best_row["row"]))
            matches.append(best_row)

    return matches
