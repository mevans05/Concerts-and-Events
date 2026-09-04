"""Maps a raw Ticketmaster event into one of our interest categories and
extracts the keyword/genre/venue signals the preference model learns on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CATEGORIES = (
    "Concert",
    "Art",
    "Cultural",
    "Fair",
    "Comedy",
    "Brewery/Beer",
    "Rugby",
    "Other",
)

# Keyword hits are checked first for the categories that Ticketmaster's own
# classification tends to bury inside "Miscellaneous" or "Sports".
_BEER_KEYWORDS = ("beer", "brewery", "brewing", "brew fest", "brewfest", "ale fest", "craft beer")
_FAIR_KEYWORDS = ("fair", "festival", "carnival", "expo", "market")
_RUGBY_KEYWORDS = ("rugby", "sevens", "six nations", "world rugby")
_CULTURAL_KEYWORDS = ("cultural", "heritage", "parade", "festival of", "folk", "powwow", "diwali", "lunar new year")

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    lowered = (haystack or "").lower()
    return any(n in lowered for n in needles)


@dataclass
class CategorizedEvent:
    event_id: str
    name: str
    category: str
    genre: str | None
    venue: str | None
    city: str | None
    start: str | None
    url: str | None
    keywords: list[str] = field(default_factory=list)


def extract_keywords(name: str, genre: str | None, sub_genre: str | None = None) -> list[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "at", "in", "to", "with", "presents",
        "tour", "live", "show", "event", "night", "featuring", "feat", "vs",
    }
    tokens = _tokenize(name)
    keywords = [t for t in tokens if t not in stop and len(t) > 2]
    for g in (genre, sub_genre):
        if g and g.lower() not in ("undefined", "other"):
            keywords.append(g.lower())
    # de-dupe, keep order, cap so one long title doesn't dominate learning
    seen = []
    for k in keywords:
        if k not in seen:
            seen.append(k)
    return seen[:8]


def categorize_event(raw: dict) -> CategorizedEvent:
    """`raw` is one element of Ticketmaster's `_embedded.events` array."""
    name = raw.get("name", "")
    classifications = raw.get("classifications") or [{}]
    top = classifications[0] if classifications else {}
    segment = (top.get("segment") or {}).get("name", "")
    genre = (top.get("genre") or {}).get("name", "")
    sub_genre = (top.get("subGenre") or {}).get("name", "")

    venues = ((raw.get("_embedded") or {}).get("venues") or [{}])
    venue = venues[0].get("name") if venues else None
    city = (venues[0].get("city") or {}).get("name") if venues else None

    description = " ".join(
        filter(None, [name, raw.get("info", ""), raw.get("pleaseNote", "")])
    )

    if _contains_any(description, _BEER_KEYWORDS):
        category = "Brewery/Beer"
    elif segment == "Sports" and (_contains_any(genre, _RUGBY_KEYWORDS) or _contains_any(description, _RUGBY_KEYWORDS)):
        category = "Rugby"
    elif segment == "Sports":
        category = "Other"
    elif segment == "Music":
        category = "Concert"
    elif segment == "Arts & Theatre":
        if _contains_any(genre, ("comedy",)) or _contains_any(sub_genre, ("comedy",)):
            category = "Comedy"
        elif _contains_any(genre, ("dance", "theatre", "opera", "cultural")) or _contains_any(description, _CULTURAL_KEYWORDS):
            category = "Cultural"
        else:
            category = "Art"
    elif segment == "Comedy" or _contains_any(genre, ("comedy",)):
        category = "Comedy"
    elif _contains_any(description, _FAIR_KEYWORDS):
        category = "Fair"
    elif _contains_any(description, _CULTURAL_KEYWORDS):
        category = "Cultural"
    else:
        category = "Other"

    dates = raw.get("dates", {})
    start = (dates.get("start") or {}).get("dateTime") or (dates.get("start") or {}).get("localDate")

    return CategorizedEvent(
        event_id=raw.get("id", ""),
        name=name,
        category=category,
        genre=genre or None,
        venue=venue,
        city=city,
        start=start,
        url=raw.get("url"),
        keywords=extract_keywords(name, genre, sub_genre),
    )
