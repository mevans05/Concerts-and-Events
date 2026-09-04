"""Maps a normalized event (from any source: Ticketmaster, an ICS public
calendar feed, ...) into one of our interest categories and extracts the
keyword/genre/venue signals the preference model learns on.
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
# classification tends to bury inside "Miscellaneous" or "Sports", and
# they're the *only* signal available for ICS feed events, which carry no
# segment/genre at all.
_BEER_KEYWORDS = ("beer", "brewery", "brewing", "brew fest", "brewfest", "ale fest", "craft beer")
_FAIR_KEYWORDS = ("fair", "festival", "carnival", "expo", "market")
_RUGBY_KEYWORDS = ("rugby", "sevens", "six nations", "world rugby")
_CULTURAL_KEYWORDS = ("cultural", "heritage", "parade", "festival of", "folk", "powwow", "diwali", "lunar new year")
_COMEDY_KEYWORDS = ("comedy", "stand-up", "stand up", "improv")

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    lowered = (haystack or "").lower()
    return any(n in lowered for n in needles)


@dataclass
class NormalizedRawEvent:
    """Common shape every event source is adapted into before categorizing."""

    source_id: str
    name: str
    start: str | None
    end: str | None = None
    url: str | None = None
    venue: str | None = None
    city: str | None = None
    description: str = ""
    segment: str | None = None
    genre: str | None = None
    sub_genre: str | None = None
    # Used when a source has no classification of its own (e.g. a public
    # ICS feed for a specific brewery or venue) — applied only if keyword
    # matching doesn't find a stronger signal.
    category_hint: str | None = None


@dataclass
class CategorizedEvent:
    event_id: str
    name: str
    category: str
    genre: str | None
    venue: str | None
    city: str | None
    start: str | None
    end: str | None = None
    url: str | None = None
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


def normalize_ticketmaster(raw: dict) -> NormalizedRawEvent:
    """`raw` is one element of Ticketmaster's `_embedded.events` array."""
    name = raw.get("name", "")
    classifications = raw.get("classifications") or [{}]
    top = classifications[0] if classifications else {}
    segment = (top.get("segment") or {}).get("name") or None
    genre = (top.get("genre") or {}).get("name") or None
    sub_genre = (top.get("subGenre") or {}).get("name") or None

    venues = (raw.get("_embedded") or {}).get("venues") or [{}]
    venue = venues[0].get("name") if venues else None
    city = (venues[0].get("city") or {}).get("name") if venues else None

    description = " ".join(filter(None, [name, raw.get("info", ""), raw.get("pleaseNote", "")]))

    dates = raw.get("dates", {})
    start = (dates.get("start") or {}).get("dateTime") or (dates.get("start") or {}).get("localDate")
    end = (dates.get("end") or {}).get("dateTime") or (dates.get("end") or {}).get("localDate")

    return NormalizedRawEvent(
        source_id=f"tm:{raw.get('id', '')}",
        name=name,
        start=start,
        end=end,
        url=raw.get("url"),
        venue=venue,
        city=city,
        description=description,
        segment=segment,
        genre=genre,
        sub_genre=sub_genre,
    )


def _detect_category(event: NormalizedRawEvent) -> str:
    segment = event.segment or ""
    genre = event.genre or ""
    sub_genre = event.sub_genre or ""
    description = " ".join(filter(None, [event.description, event.name]))

    if _contains_any(description, _BEER_KEYWORDS):
        return "Brewery/Beer"
    if _contains_any(description, _RUGBY_KEYWORDS) or _contains_any(genre, _RUGBY_KEYWORDS):
        return "Rugby"
    if segment == "Sports":
        return event.category_hint or "Other"
    if _contains_any(genre, _COMEDY_KEYWORDS) or _contains_any(sub_genre, _COMEDY_KEYWORDS) or _contains_any(description, _COMEDY_KEYWORDS):
        return "Comedy"
    if segment == "Music":
        return "Concert"
    if segment == "Arts & Theatre":
        if _contains_any(genre, ("dance", "theatre", "opera", "cultural")) or _contains_any(description, _CULTURAL_KEYWORDS):
            return "Cultural"
        return "Art"
    if _contains_any(description, _FAIR_KEYWORDS):
        return "Fair"
    if _contains_any(description, _CULTURAL_KEYWORDS):
        return "Cultural"
    if event.category_hint:
        return event.category_hint
    return "Other"


def categorize_event(event: NormalizedRawEvent) -> CategorizedEvent:
    category = _detect_category(event)
    return CategorizedEvent(
        event_id=event.source_id,
        name=event.name,
        category=category,
        genre=event.genre,
        venue=event.venue,
        city=event.city,
        start=event.start,
        end=event.end,
        url=event.url,
        keywords=extract_keywords(event.name, event.genre, event.sub_genre),
    )


def categorize_ticketmaster_raw(raw: dict) -> CategorizedEvent:
    """Convenience one-step helper: normalize + categorize a Ticketmaster event."""
    return categorize_event(normalize_ticketmaster(raw))
