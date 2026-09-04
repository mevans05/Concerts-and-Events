"""A small multiplicative-weights preference model.

Every event gets scored as the product of learned weights for its category,
genre, venue, and a few keywords pulled from its title. Feedback nudges
those weights up (Interested / Attended) or down (Not Interested), so the
same category/genre/venue/keyword combo scores differently over time as
more feedback comes in. This is intentionally simple (no external ML
dependency) and fully explainable — the current weights are written out to
the spreadsheet's "Preferences" sheet every run.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .categorize import CategorizedEvent

DEFAULT_WEIGHT = 1.0
MIN_WEIGHT = 0.2
MAX_WEIGHT = 4.0

# Reward applied per feedback value before scaling by the learning rate.
REWARD_MAP = {
    "Interested": 1.0,
    "Attended": 1.0,
    "Maybe": 0.3,
    "Not Interested": -1.0,
}


def _clamp(value: float) -> float:
    return max(MIN_WEIGHT, min(MAX_WEIGHT, value))


@dataclass
class Preferences:
    categories: dict = field(default_factory=dict)
    genres: dict = field(default_factory=dict)
    venues: dict = field(default_factory=dict)
    keywords: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "Preferences":
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            categories=raw.get("categories", {}),
            genres=raw.get("genres", {}),
            venues=raw.get("venues", {}),
            keywords=raw.get("keywords", {}),
        )

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "categories": self.categories,
                    "genres": self.genres,
                    "venues": self.venues,
                    "keywords": self.keywords,
                },
                f,
                indent=2,
                sort_keys=True,
            )

    @classmethod
    def from_rows(cls, rows) -> "Preferences":
        """Rebuilds weights from (Type, Key, Weight) rows — the same shape
        the Preferences sheet/tab is written in. Used by the Google Sheets
        backend, where that sheet is the persisted source of truth instead
        of a local JSON file."""
        prefs = cls()
        targets = {
            "Category": prefs.categories,
            "Genre": prefs.genres,
            "Venue": prefs.venues,
            "Keyword": prefs.keywords,
        }
        for row in rows:
            if not row or len(row) < 3:
                continue
            type_, key, weight = row[0], row[1], row[2]
            target = targets.get(type_)
            if target is None or key in (None, "") or weight in (None, ""):
                continue
            try:
                target[str(key)] = float(weight)
            except (TypeError, ValueError):
                continue
        return prefs

    def to_rows(self) -> list[tuple]:
        """(Type, Key, Weight) rows for the Preferences sheet/tab."""
        rows = []
        for key, weight in sorted(self.categories.items()):
            rows.append(("Category", key, weight))
        for key, weight in sorted(self.genres.items()):
            rows.append(("Genre", key, weight))
        for key, weight in sorted(self.venues.items()):
            rows.append(("Venue", key, weight))
        for key, weight in sorted(self.keywords.items(), key=lambda kv: -kv[1]):
            rows.append(("Keyword", key, weight))
        return rows

    def score(self, event: CategorizedEvent) -> float:
        score = self.categories.get(event.category, DEFAULT_WEIGHT)
        if event.genre:
            score *= self.genres.get(event.genre, DEFAULT_WEIGHT)
        if event.venue:
            score *= self.venues.get(event.venue, DEFAULT_WEIGHT)
        kw_weights = [self.keywords.get(k, DEFAULT_WEIGHT) for k in event.keywords if k in self.keywords]
        if kw_weights:
            score *= sum(kw_weights) / len(kw_weights)
        return round(score, 4)

    def update(self, event: CategorizedEvent, feedback: str, learning_rate: float) -> None:
        reward = REWARD_MAP.get(feedback)
        if reward is None:
            return
        delta = learning_rate * reward

        self.categories[event.category] = _clamp(self.categories.get(event.category, DEFAULT_WEIGHT) + delta)
        if event.genre:
            self.genres[event.genre] = _clamp(self.genres.get(event.genre, DEFAULT_WEIGHT) + delta)
        if event.venue:
            self.venues[event.venue] = _clamp(self.venues.get(event.venue, DEFAULT_WEIGHT) + delta)
        for kw in event.keywords:
            # Keywords move slower than category/genre/venue so one quirky
            # title doesn't overwhelm the model.
            self.keywords[kw] = _clamp(self.keywords.get(kw, DEFAULT_WEIGHT) + delta * 0.5)
