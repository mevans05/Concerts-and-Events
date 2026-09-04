#!/usr/bin/env python3
"""One-time setup: mints a Google OAuth refresh token covering both
personal Google Calendar access (conflict-checking, attendance learning)
and Google Sheets access (read/write the live events spreadsheet). One
token, both scopes — you don't need to run this twice.

Before running this:
  1. In the Google Cloud Console, create (or reuse) a project and enable
     both the "Google Calendar API" and the "Google Sheets API"
     (APIs & Services -> Library).
  2. Create OAuth client credentials of type "Desktop app"
     (APIs & Services -> Credentials -> Create Credentials -> OAuth client
     ID) and note the Client ID and Client Secret.
  3. Add yourself as a test user if the OAuth consent screen is in
     "Testing" mode (APIs & Services -> OAuth consent screen).

Run:
  python scripts/google_oauth_setup.py --client-id ... --client-secret ...

This starts a tiny local server on http://localhost:8765, opens (or
prints, if a browser can't launch here) the Google consent screen, and
once you approve access exchanges the resulting code for a refresh
token. Save the printed values as GitHub repo secrets (Settings ->
Secrets and variables -> Actions):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
Then set google_calendar.enabled: true and/or google_sheets.enabled: true
in config.yaml, as you like.

If you already ran this script before Sheets support existed, your old
refresh token only has the Calendar scope — run it again to mint a new
one covering both (Google will ask you to re-consent).
"""
from __future__ import annotations

import argparse
import http.server
import threading
import urllib.parse
import webbrowser

import requests

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/spreadsheets"


class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.code = params.get("code", [None])[0]
        _CodeCatcher.error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = "Done. You can close this tab and return to the terminal." if _CodeCatcher.code else "Authorization failed. Check the terminal."
        self.wfile.write(f"<html><body>{message}</body></html>".encode())

    def log_message(self, *args) -> None:  # quiet the default request logging
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a Google Calendar OAuth refresh token")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": args.client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
    )

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CodeCatcher)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Open this URL and approve access (it should also open automatically):\n")
    print(auth_url, "\n")
    webbrowser.open(auth_url)

    thread.join(timeout=300)
    server.server_close()

    if _CodeCatcher.error:
        raise SystemExit(f"Google returned an error: {_CodeCatcher.error}")
    if not _CodeCatcher.code:
        raise SystemExit("Timed out waiting for Google to redirect back with an authorization code.")

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "code": _CodeCatcher.code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "Google didn't return a refresh_token. This usually happens if you've already "
            "authorized this app before without revoking it. Revoke access at "
            "https://myaccount.google.com/permissions and run this script again."
        )

    print("\nSuccess! Add these as GitHub repo secrets (Settings -> Secrets and variables -> Actions):\n")
    print(f"  GOOGLE_CLIENT_ID={args.client_id}")
    print(f"  GOOGLE_CLIENT_SECRET={args.client_secret}")
    print(f"  GOOGLE_REFRESH_TOKEN={refresh_token}")
    print("\nThen set google_calendar.enabled: true in config.yaml.")


if __name__ == "__main__":
    main()
