"""Entry point: `python manage.py run [--mock]`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from events_pipeline.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
