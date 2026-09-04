"""Shared OAuth token handling for Google APIs (Calendar, Sheets), using a
long-lived refresh token minted once via scripts/google_oauth_setup.py.
Both google_calendar.py and sheets_client.py use this — it's one set of
credentials covering whichever scopes were granted at setup time.
"""
from __future__ import annotations

import os

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUEST_TIMEOUT = 15


class GoogleApiError(RuntimeError):
    pass


def credentials_from_env() -> dict | None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}


def get_access_token(creds: dict) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise GoogleApiError(f"Token refresh failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["access_token"]
