from __future__ import annotations

from typing import Any

import pytest


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


@pytest.fixture
def fake_response() -> type[FakeResponse]:
    return FakeResponse
