# Concerts & Events

A self-updating events spreadsheet. Every day it pulls newly announced
concerts, art shows, cultural events, fairs, comedy shows, brewery/beer
events, and rugby matches near you — from Ticketmaster, optionally your
own Google Calendar, and any public calendar feeds you subscribe to —
ranks them by a preference model, and writes the top picks into a
spreadsheet. You leave feedback right in it, and each day's run learns
from it — so the recommendations get more tailored to your taste over
time.

The spreadsheet is either a **live Google Sheet** (open it in a browser,
edit from your phone — no downloading/uploading anything) or a local
`data/events.xlsx` file committed to the repo, depending on
`google_sheets.enabled` in `config.yaml`. See **Google Sheets** below.

## How it works

1. **Fetch** — queries the free [Ticketmaster Discovery API](https://developer.ticketmaster.com/)
   for events near your configured city across Music, Arts & Theatre,
   Sports, and Miscellaneous, plus targeted keyword searches for things
   like "brewery" and "rugby" that Ticketmaster doesn't classify cleanly.
   It also pulls in any public iCal feeds and, if you've connected your
   own Google Calendar, checks it for conflicts and past attendance (see
   "Google Calendar" below).
2. **Categorize** — buckets each event into one of: `Concert`, `Art`,
   `Cultural`, `Fair`, `Comedy`, `Brewery/Beer`, `Rugby`, or `Other`
   (`Other` is excluded from recommendations by default — see `config.yaml`).
3. **Score** — every event gets a score from a learned preference model
   (weights per category, genre, venue, and title keywords, starting
   neutral at 1.0). Only new, never-before-seen events above
   `min_score_threshold` are added, so you never see the same event twice.
4. **You give feedback** — the `Events` sheet/tab has a `Feedback` column
   with a dropdown: `Interested`, `Maybe`, `Not Interested`, `Attended`.
   Fill it in whenever you like. (If Google Calendar attendance-learning
   is on, some rows may already show `Attended` with
   `Feedback Source: Calendar (auto)` — you can override any of those
   manually too.)
5. **Learn** — on the *next* run, any row whose feedback changed nudges the
   weights for that event's category/genre/venue/keywords up (Interested /
   Attended) or down (Not Interested), within safe bounds. The learned
   weights are visible in the `Preferences` sheet/tab (and, on the local
   backend, also cached in `data/preferences.json`).
6. **Housekeeping** — events whose date has passed are moved from `Events`
   to `History` automatically, keeping the active list short while
   preserving the feedback record.

This runs automatically once a day via GitHub Actions
(`.github/workflows/daily-events.yml`), which writes to your Google Sheet
directly (nothing to commit) or, on the local backend, commits the
updated `data/events.xlsx` back to the repo.

## Google Sheets

With `google_sheets.enabled: true` (the default in the shipped
`config.yaml`), the workbook lives as a real Google Sheet instead of a
binary file in the repo — open the link, edit the `Feedback` column from
any browser or your phone, no downloading or committing anything.

- Leave `google_sheets.spreadsheet_id` blank and a new sheet is created
  automatically on the first run; its ID is cached in
  `data/google_sheet_id.txt` (committed by the workflow) so every later
  run reuses the same sheet. The run's log line and CLI output print the
  sheet's URL.
- Or create your own blank Google Sheet, copy its ID out of the URL
  (`https://docs.google.com/spreadsheets/d/THIS_PART/edit`), and paste it
  into `spreadsheet_id` to pin it — useful if you want it in a specific
  Drive folder or shared with someone else up front.
- It reuses the **exact same OAuth credentials** as Google Calendar below
  (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN`) —
  one setup script run covers both, as long as the refresh token has the
  Sheets scope (see **Google Calendar setup**, which now requests both).
- If those secrets aren't set, the pipeline logs a warning and falls back
  to the local `data/events.xlsx` file automatically — nothing breaks.
- Preferences live entirely in the sheet's `Preferences` tab in this mode
  (no local JSON file to keep in sync).

Turn it off (`google_sheets.enabled: false`) to go back to the plain
local-file workflow described everywhere else in this README.

## Google Calendar

Three independent things, all controlled by `google_calendar` in
`config.yaml`:

- **Conflict flagging** — recommended events that overlap something
  already on your calendar (+ `conflict_buffer_minutes` on each side) get
  `Calendar Conflict: Yes` in the sheet. They're still recommended by
  default; set `exclude_conflicts: true` to drop them instead.
- **Attendance learning** — if a past calendar event's title closely
  matches a previously-recommended event on the same day, that row is
  auto-marked `Attended` (`Feedback Source: Calendar (auto)`) and folded
  into the learning model on the next run — free positive feedback for
  everything you actually went to, without typing anything in.
- **Public calendar feeds** (`google_calendar.public_feeds`) — subscribe
  to any public `.ics` URL (a venue's schedule, a rugby club's fixture
  list, a public Google Calendar's "Secret address in iCal format") as an
  extra event-discovery source. No personal auth needed for this one.

Conflict flagging and attendance learning need read access to your own
calendar via OAuth — see **Google Calendar setup** below. Public feeds
work with none of that, just URLs in `config.yaml`.

### Google Calendar setup (for conflicts / attendance learning / Sheets)

One setup covers both Google Calendar features and Google Sheets — the
refresh token it mints carries both scopes.

1. In the [Google Cloud Console](https://console.cloud.google.com/), create
   (or reuse) a project and enable both the **Google Calendar API** and
   the **Google Sheets API**.
2. Create OAuth client credentials of type **Desktop app** and note the
   Client ID and Client Secret. If the consent screen is in "Testing"
   mode, add your own Google account as a test user.
3. Run the one-time setup script locally (it opens a browser for you to
   approve access, then prints a refresh token):
   ```bash
   pip install -r requirements.txt
   python scripts/google_oauth_setup.py --client-id YOUR_ID --client-secret YOUR_SECRET
   ```
4. Add the three printed values as GitHub repo secrets: `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`.
5. Set `google_calendar.enabled: true` and/or `google_sheets.enabled: true`
   in `config.yaml` (Sheets is already `true` by default) and commit it.

If these secrets aren't set, the pipeline just skips personal-calendar
and Sheets features and logs a warning — everything else keeps working
against the local `data/events.xlsx` file.

### Why not Facebook Events?

Meta shut down the public Events Graph API for third-party apps years
ago; the only thing still accessible is events on Pages you manage,
via that page's own access token, which isn't general event discovery.
Given that, we skipped it — Ticketmaster plus your own calendar and any
public feeds you add already cover the categories you're after. If you
later want Page-specific events pulled in, that's a narrower, addable
piece.

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
4. **(Optional)** set up Google Calendar/Sheets — see the sections above —
   and/or add public `.ics` feed URLs to `google_calendar.public_feeds`.
   `google_sheets.enabled` is `true` by default; set it `false` if you'd
   rather stick with the local `data/events.xlsx` file.
5. The workflow runs daily on its schedule, or trigger it manually from
   the Actions tab (`Run workflow`).
6. Fill in the `Feedback` column on events you have opinions about:
   - **Google Sheets backend**: just open the sheet (its URL is in the
     workflow's run log, and cached in `data/google_sheet_id.txt`) and
     edit it — the next scheduled run picks up your changes automatically.
   - **Local file backend**: open `data/events.xlsx` (via GitHub, Excel,
     etc.), edit it, and commit your changes before the next scheduled
     run so it's picked up.

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
config.yaml                        location, categories, learning/scoring, google_calendar/google_sheets knobs
data/events.xlsx                   local-backend spreadsheet (Events / History / Preferences sheets)
data/preferences.json              local-backend learned weights, human-readable
data/google_sheet_id.txt           Sheets-backend: cached ID of the auto-created sheet
manage.py                          CLI entry point
scripts/google_oauth_setup.py      one-time script to mint a Google refresh token (Calendar + Sheets scopes)
src/events_pipeline/
  config.py                        loads config.yaml
  fetch.py                         Ticketmaster Discovery API client
  ical_feeds.py                    public .ics calendar feed client
  google_auth.py                   shared OAuth token refresh (Calendar + Sheets)
  google_calendar.py               personal Google Calendar client (freeBusy + events.list)
  sheets_client.py                 Google Sheets REST client (values, formatting, tab creation)
  sheets_store.py                  glues sheets_client to the same in-memory grid spreadsheet.py uses
  simple_grid.py                   openpyxl-compatible in-memory grid (the Sheets backend's "workbook")
  attendance.py                    matches past calendar events to recommendations
  categorize.py                    normalized event -> category + keywords (source-agnostic)
  preferences.py                   the learning model (score/update); to_rows/from_rows for the Sheets backend
  spreadsheet.py                   local .xlsx read/write + the shared business logic both backends use
  pipeline.py                      wires it all together for one daily run, picks the backend
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
what it has learned in the `Preferences` sheet/tab. Reset it any time —
on the Google Sheets backend, clear out the rows in the `Preferences` tab
(keep the header); on the local backend, delete `data/preferences.json`.
