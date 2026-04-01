"""
BioMCP Test Configuration
 =========================
Shared fixtures and pytest configuration for all tests.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="function")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        skip_windows = pytest.mark.skip(reason="Event loop issue on Windows for live API tests")
        for item in items:
            if "live" in item.name.lower() and "integration" in item.keywords:
                item.add_marker(skip_windows)


@pytest.fixture
def mock_http_response():
    def _make(status_code: int = 200, json_data: dict | None = None, text: str = ""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        resp.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx

            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"{status_code}", request=MagicMock(), response=resp
            )
        return resp

    return _make


@pytest.fixture
def mock_http_client(mock_http_response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_http_response())
    client.post = AsyncMock(return_value=mock_http_response())
    return client


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that call real external APIs (network required)"
    )
