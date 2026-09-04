import os

from events_pipeline.categorize import CategorizedEvent
from events_pipeline.preferences import MAX_WEIGHT, MIN_WEIGHT, Preferences


def _event(category="Concert", genre="Rock", venue="Red Rocks", keywords=None):
    return CategorizedEvent(
        event_id="e1",
        name="Test Event",
        category=category,
        genre=genre,
        venue=venue,
        city="Denver",
        start="2026-01-01T00:00:00Z",
        url="https://example.com",
        keywords=keywords or ["test", "event"],
    )


def test_unknown_event_scores_neutral():
    prefs = Preferences()
    assert prefs.score(_event()) == 1.0


def test_positive_feedback_increases_future_score():
    prefs = Preferences()
    event = _event()
    before = prefs.score(event)
    prefs.update(event, "Interested", learning_rate=0.15)
    after = prefs.score(event)
    assert after > before


def test_negative_feedback_decreases_future_score():
    prefs = Preferences()
    event = _event()
    prefs.update(event, "Not Interested", learning_rate=0.15)
    assert prefs.score(event) < 1.0


def test_weights_are_clamped():
    prefs = Preferences()
    event = _event()
    for _ in range(200):
        prefs.update(event, "Interested", learning_rate=0.5)
    assert prefs.categories["Concert"] <= MAX_WEIGHT
    for _ in range(200):
        prefs.update(event, "Not Interested", learning_rate=0.5)
    assert prefs.categories["Concert"] >= MIN_WEIGHT


def test_repeated_feedback_compounds_category_preference():
    prefs = Preferences()
    liked = _event(category="Rugby", genre="Rugby", venue="Infinity Park", keywords=["rugby"])
    disliked = _event(category="Comedy", genre="Comedy", venue="Comedy Club", keywords=["comedy"])
    for _ in range(5):
        prefs.update(liked, "Interested", learning_rate=0.15)
        prefs.update(disliked, "Not Interested", learning_rate=0.15)
    assert prefs.score(liked) > prefs.score(disliked)


def test_save_and_load_round_trip(tmp_path):
    prefs = Preferences()
    event = _event()
    prefs.update(event, "Interested", learning_rate=0.15)
    path = os.path.join(tmp_path, "prefs.json")
    prefs.save(path)

    loaded = Preferences.load(path)
    assert loaded.categories == prefs.categories
    assert loaded.genres == prefs.genres
    assert loaded.venues == prefs.venues
    assert loaded.keywords == prefs.keywords


def test_load_missing_file_returns_defaults(tmp_path):
    prefs = Preferences.load(os.path.join(tmp_path, "does-not-exist.json"))
    assert prefs.categories == {}
