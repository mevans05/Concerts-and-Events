"""Loads config.yaml into a plain, validated dict-like structure."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

DEFAULT_CATEGORIES = {
    "Concert": True,
    "Art": True,
    "Cultural": True,
    "Fair": True,
    "Comedy": True,
    "Brewery/Beer": True,
    "Rugby": True,
    "Other": False,
}


@dataclass
class Location:
    city: str
    state_code: str | None = None
    postal_code: str | None = None
    country_code: str = "US"
    radius: int = 50
    unit: str = "miles"


@dataclass
class GoogleCalendarConfig:
    enabled: bool = False
    calendar_id: str = "primary"
    conflict_buffer_minutes: int = 30
    exclude_conflicts: bool = False
    learn_from_past_events: bool = True
    attendance_lookback_days: int = 3
    public_feeds: list = field(default_factory=list)


@dataclass
class Config:
    location: Location
    lookahead_days: int = 30
    max_daily_recommendations: int = 25
    min_score_threshold: float = 0.35
    learning_rate: float = 0.15
    categories: dict = field(default_factory=lambda: dict(DEFAULT_CATEGORIES))
    google_calendar: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)

    def category_enabled(self, category: str) -> bool:
        return self.categories.get(category, False)


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    loc_raw = raw.get("location", {})
    location = Location(
        city=loc_raw.get("city", "Denver"),
        state_code=loc_raw.get("state_code") or None,
        postal_code=str(loc_raw["postal_code"]) if loc_raw.get("postal_code") else None,
        country_code=loc_raw.get("country_code", "US"),
        radius=int(loc_raw.get("radius", 50)),
        unit=loc_raw.get("unit", "miles"),
    )

    categories = dict(DEFAULT_CATEGORIES)
    categories.update(raw.get("categories", {}))

    gcal_raw = raw.get("google_calendar", {}) or {}
    google_calendar = GoogleCalendarConfig(
        enabled=bool(gcal_raw.get("enabled", False)),
        calendar_id=gcal_raw.get("calendar_id", "primary"),
        conflict_buffer_minutes=int(gcal_raw.get("conflict_buffer_minutes", 30)),
        exclude_conflicts=bool(gcal_raw.get("exclude_conflicts", False)),
        learn_from_past_events=bool(gcal_raw.get("learn_from_past_events", True)),
        attendance_lookback_days=int(gcal_raw.get("attendance_lookback_days", 3)),
        public_feeds=list(gcal_raw.get("public_feeds", []) or []),
    )

    return Config(
        location=location,
        lookahead_days=int(raw.get("lookahead_days", 30)),
        max_daily_recommendations=int(raw.get("max_daily_recommendations", 25)),
        min_score_threshold=float(raw.get("min_score_threshold", 0.35)),
        learning_rate=float(raw.get("learning_rate", 0.15)),
        categories=categories,
        google_calendar=google_calendar,
    )


def get_ticketmaster_api_key() -> str | None:
    return os.environ.get("TICKETMASTER_API_KEY")
