import json
import os

from events_pipeline.categorize import categorize_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_events.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _by_id(events, event_id):
    return next(e for e in events if e["id"] == event_id)


EXPECTED = {
    "mock-concert-1": "Concert",
    "mock-art-1": "Art",
    "mock-comedy-1": "Comedy",
    "mock-cultural-1": "Cultural",
    "mock-fair-1": "Fair",
    "mock-beer-1": "Brewery/Beer",
    "mock-rugby-1": "Rugby",
    "mock-other-sport-1": "Other",
}


def test_all_fixture_events_categorized_as_expected():
    events = _load_fixture()
    for event_id, expected_category in EXPECTED.items():
        raw = _by_id(events, event_id)
        result = categorize_event(raw)
        assert result.category == expected_category, f"{event_id}: got {result.category}"


def test_beer_keyword_overrides_misc_classification():
    raw = _by_id(_load_fixture(), "mock-beer-1")
    result = categorize_event(raw)
    assert result.category == "Brewery/Beer"


def test_extracts_venue_and_city():
    raw = _by_id(_load_fixture(), "mock-rugby-1")
    result = categorize_event(raw)
    assert result.venue == "Infinity Park"
    assert result.city == "Denver"


def test_keywords_exclude_stopwords():
    raw = _by_id(_load_fixture(), "mock-comedy-1")
    result = categorize_event(raw)
    assert "feat" not in result.keywords
    assert "the" not in result.keywords
    assert "dana" in result.keywords
