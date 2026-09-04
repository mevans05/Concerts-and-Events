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
    country_code: str = "US"
    radius: int = 50
    unit: str = "miles"


@dataclass
class Config:
    location: Location
    lookahead_days: int = 30
    max_daily_recommendations: int = 25
    min_score_threshold: float = 0.35
    learning_rate: float = 0.15
    categories: dict = field(default_factory=lambda: dict(DEFAULT_CATEGORIES))

    def category_enabled(self, category: str) -> bool:
        return self.categories.get(category, False)


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    loc_raw = raw.get("location", {})
    location = Location(
        city=loc_raw.get("city", "Denver"),
        country_code=loc_raw.get("country_code", "US"),
        radius=int(loc_raw.get("radius", 50)),
        unit=loc_raw.get("unit", "miles"),
    )

    categories = dict(DEFAULT_CATEGORIES)
    categories.update(raw.get("categories", {}))

    return Config(
        location=location,
        lookahead_days=int(raw.get("lookahead_days", 30)),
        max_daily_recommendations=int(raw.get("max_daily_recommendations", 25)),
        min_score_threshold=float(raw.get("min_score_threshold", 0.35)),
        learning_rate=float(raw.get("learning_rate", 0.15)),
        categories=categories,
    )


def get_api_key() -> str | None:
    return os.environ.get("TICKETMASTER_API_KEY")
