from __future__ import annotations

from typing import Any

import pytest
import requests


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200, headers: dict | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


@pytest.fixture
def fake_response() -> type[FakeResponse]:
    return FakeResponse
