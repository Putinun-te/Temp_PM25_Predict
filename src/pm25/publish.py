"""Publish a forecast document to Firebase Realtime Database."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import requests

TOKEN_SCOPES = (
    "https://www.googleapis.com/auth/firebase.database",
    "https://www.googleapis.com/auth/userinfo.email",
)
REQUIRED_FIELDS = ("schema_version", "generated_at", "as_of", "status", "daily", "monthly")


def service_account_token(service_account_json: str) -> str:
    """Exchange a service account key for a short-lived OAuth token."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=list(TOKEN_SCOPES)
    )
    credentials.refresh(Request())
    return credentials.token


def publish_forecast(
    db_url: str,
    token: str,
    forecast: dict[str, Any],
    http_patch: Callable[..., Any] = requests.patch,
) -> None:
    """Write the latest forecast and its dated copy in one atomic request.

    Using one multi-path update means readers can never see the two locations
    disagree. The token travels in a header so it cannot appear in a URL.
    """
    missing = [field for field in REQUIRED_FIELDS if field not in forecast]
    if missing:
        raise ValueError(f"forecast is missing fields: {', '.join(missing)}")
    response = http_patch(
        f"{db_url.rstrip('/')}/predictions.json",
        json={"latest": forecast, f"history/{forecast['as_of']}": forecast},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
