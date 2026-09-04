# Concerts & Events

A self-updating events spreadsheet. Every day it pulls newly announced
concerts, art shows, cultural events, fairs, comedy shows, brewery/beer
events, and rugby matches near you, ranks them by a preference model, and
writes the top picks into `data/events.xlsx`. You leave feedback right in
the sheet, and each day's run learns from it — so the recommendations get
more tailored to your taste over time.

## How it works

1. **Fetch** — queries the free [Ticketmaster Discovery API](https://developer.ticketmaster.com/)
   for events near your configured city across Music, Arts & Theatre,
   Sports, and Miscellaneous, plus targeted keyword searches for things
   like "brewery" and "rugby" that Ticketmaster doesn't classify cleanly.
2. **Categorize** — buckets each event into one of: `Concert`, `Art`,
   `Cultural`, `Fair`, `Comedy`, `Brewery/Beer`, `Rugby`, or `Other`
   (`Other` is excluded from recommendations by default — see `config.yaml`).
3. **Score** — every event gets a score from a learned preference model
   (weights per category, genre, venue, and title keywords, starting
   neutral at 1.0). Only new, never-before-seen events above
   `min_score_threshold` are added, so you never see the same event twice.
4. **You give feedback** — in `data/events.xlsx`, the `Events` sheet has a
   `Feedback` column with a dropdown: `Interested`, `Maybe`,
   `Not Interested`, `Attended`. Fill it in whenever you like.
5. **Learn** — on the *next* run, any row whose feedback changed nudges the
   weights for that event's category/genre/venue/keywords up (Interested /
   Attended) or down (Not Interested), within safe bounds. The learned
   weights are visible in the `Preferences` sheet and stored in
   `data/preferences.json`.
6. **Housekeeping** — events whose date has passed are moved from `Events`
   to `History` automatically, keeping the active list short while
   preserving the feedback record.

This runs automatically once a day via GitHub Actions
(`.github/workflows/daily-events.yml`), which commits the updated
`data/events.xlsx` and `data/preferences.json` back to the repo.

## Setup

1. **Get a free Ticketmaster API key**: sign up at
   https://developer.ticketmaster.com/ and create an app to get a
   `Consumer Key`.
2. **Add it as a repo secret**: in GitHub, go to
   Settings → Secrets and variables → Actions → New repository secret,
   name it `TICKETMASTER_API_KEY`, and paste the key.
3. **Set your location and interests** in `config.yaml` (not secret, just
   edit and commit):
   - `location.city` / `country_code` / `radius` / `unit`
   - `categories` — toggle any category off entirely
   - `min_score_threshold` — lower it early on to see more variety while
     the model is still learning; raise it once it knows your taste
   - `learning_rate` — how fast feedback moves the weights
4. The workflow runs daily on its schedule, or trigger it manually from
   the Actions tab (`Run workflow`).
5. Open `data/events.xlsx` (via GitHub, Excel, Google Sheets, etc.), fill
   in the `Feedback` column on events you have opinions about, and commit
   your changes (or just edit it directly in GitHub) before the next
   scheduled run so it's picked up.

## Running locally

```bash
pip install -r requirements.txt

# Real data (needs the API key in your shell):
export TICKETMASTER_API_KEY=your-key-here
python manage.py run -v

# Or without an API key, using bundled sample events:
python manage.py run --mock -v
```

Run the tests with:

```bash
python -m pytest tests/ -q
```

## Project layout

```
config.yaml                        location, categories, learning/scoring knobs
data/events.xlsx                   the live spreadsheet (Events / History / Preferences sheets)
data/preferences.json              the learned weights, human-readable
manage.py                          CLI entry point
src/events_pipeline/
  config.py                        loads config.yaml
  fetch.py                         Ticketmaster Discovery API client
  categorize.py                    raw event -> category + keywords
  preferences.py                   the learning model (score/update)
  spreadsheet.py                   openpyxl read/write for the workbook
  pipeline.py                      wires it all together for one daily run
  cli.py                           argparse CLI
tests/                             unit tests (no network required)
.github/workflows/daily-events.yml the daily cron job
```

## Notes on the preference model

It's a simple, fully-transparent multiplicative weighting scheme rather
than a black-box ML model: each event's score is the product of learned
weights for its category, genre, venue, and a handful of keywords from its
title. Feedback nudges the relevant weights up or down by
`learning_rate * reward` (Interested/Attended = +1, Maybe = +0.3,
Not Interested = -1), clamped to a sane range. You can always see exactly
what it has learned in the `Preferences` sheet or `data/preferences.json`,
and reset it any time by deleting `data/preferences.json`.
