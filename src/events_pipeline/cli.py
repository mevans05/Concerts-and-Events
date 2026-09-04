from __future__ import annotations

import argparse
import logging

from .pipeline import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Daily events recommender")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Fetch new events, learn from feedback, update the workbook")
    run_parser.add_argument("--config", default="config.yaml")
    run_parser.add_argument("--workbook", default="data/events.xlsx")
    run_parser.add_argument("--preferences", default="data/preferences.json")
    run_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use bundled sample events instead of calling the Ticketmaster API (for local testing)",
    )
    run_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.command == "run":
        summary = run(
            config_path=args.config,
            workbook_path=args.workbook,
            preferences_path=args.preferences,
            mock=args.mock,
        )
        print(f"Workbook: {summary.workbook_location}" + (" (Google Sheet)" if summary.google_sheets_active else " (local file)"))
        print(f"Feedback learned from: {summary.feedback_processed} event(s)")
        print(f"Events moved to History: {summary.events_moved_to_history}")
        print(f"New candidate events considered: {summary.new_events_fetched}")
        print(f"New events recommended today: {summary.new_events_recommended}")
        if summary.google_calendar_active:
            print(f"Calendar conflicts flagged: {summary.conflicts_flagged}")
            print(f"Attendance auto-learned from calendar: {summary.attendance_auto_learned}")
        if summary.used_mock_data:
            print("NOTE: ran on sample/mock data (no TICKETMASTER_API_KEY set).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
