"""Shared pytest fixtures for ``ziniao_mcp.flows`` (RPA flow runner) tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest


class FakeTab:
    """Minimal tab stub for flow tests (no CDP)."""

    def __init__(self, url: str = "https://example.com/") -> None:
        self.target = MagicMock()
        self.target.url = url
        self._queries: dict[str, Any] = {}

    def query_selector(self, sel: str) -> Any:
        return self._queries.get(sel)

    def set_query(self, sel: str, node: Any) -> None:
        self._queries[sel] = node

    async def send(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def sleep(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def evaluate(self, *_args: Any, **_kwargs: Any) -> Any:
        return None


class FakeSession:
    """Minimal session manager stub."""

    def __init__(self, url: str = "https://example.com/") -> None:
        self._tab = FakeTab(url=url)
        self.iframe_context = None

    def get_active_tab(self) -> FakeTab:
        return self._tab

    def get_active_session(self) -> FakeSession:
        return self


@pytest.fixture
def fake_tab() -> FakeTab:
    return FakeTab()


@pytest.fixture
def fake_session(fake_tab: FakeTab) -> FakeSession:
    s = FakeSession(url=fake_tab.target.url)
    s._tab = fake_tab  # type: ignore[attr-defined]
    return s


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Isolated ``~/.ziniao/runs/<id>`` style directory."""
    d = tmp_path / "runs" / "test-run-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def policy_dev() -> dict[str, Any]:
    """Permissive policy for unit tests."""
    return {
        "external_call": {
            "http": {"enabled": True, "allow_private_network": True, "url_allowlist": ["*"]},
            "mcp": {"enabled": True, "tool_allowlist": ["*"]},
        },
        "code_step": {
            "enabled": True,
            "language_allowlist": ["python"],
            "max_runtime_seconds": 30,
            "max_output_kb": 256,
        },
        "local_command": {"enabled": False},
        "file_write_outside_workspace": {"enabled": True},
    }


@pytest.fixture
def policy_off() -> dict[str, Any]:
    """Restrictive policy for negative tests."""
    return {
        "external_call": {
            "http": {"enabled": False, "allow_private_network": False, "url_allowlist": []},
            "mcp": {"enabled": False, "tool_allowlist": []},
        },
        "code_step": {"enabled": False},
        "local_command": {"enabled": False},
        "file_write_outside_workspace": {"enabled": False},
    }


def sample_flow_minimal_ok() -> dict[str, Any]:
    """Tiny valid ``kind: rpa_flow`` document (no browser steps)."""
    return {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "name": "noop",
        "vars": {},
        "policy": {"code": True},
        "steps": [
            {"id": "ping", "action": "eval", "script": "1+1", "await_promise": False},
        ],
    }


def sample_state_minimal() -> dict[str, Any]:
    return {
        "run_id": "test-run-001",
        "flow_id": "noop",
        "current_step": "ping",
        "last_ok_step": "",
        "ctx": {"vars": {}, "extracted": {}, "steps": {}},
        "session": {
            "kind": "chrome",
            "store_id": "",
            "cdp_port": 9222,
            "active_tab_url": "https://example.com/",
            "active_tab_title": "Ex",
            "wait_anchors": [],
        },
        "policy_view": {},
        "capabilities_used": [],
    }


@pytest.fixture
def sample_flow() -> dict[str, Any]:
    return sample_flow_minimal_ok()


@pytest.fixture
def sample_state() -> dict[str, Any]:
    return sample_state_minimal()


@pytest.fixture
def mock_httpx(monkeypatch: pytest.MonkeyPatch) -> Callable[..., AsyncMock]:
    """Return factory to patch httpx.AsyncClient for external_call tests."""

    def _patch(response_json: dict | None = None, status: int = 200) -> AsyncMock:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.json = MagicMock(return_value=response_json or {})
        mock_resp.text = json.dumps(response_json or {})
        mock_client.request = AsyncMock(return_value=mock_resp)

        async def _client_cm(*_a: Any, **_k: Any):
            yield mock_client

        monkeypatch.setattr(
            "httpx.AsyncClient",
            lambda *a, **k: MagicMock(__aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()),
        )
        return mock_client

    return _patch


@pytest.fixture
def freeze_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub time for deterministic run_id (optional use in tests)."""
    from datetime import datetime, timezone

    fixed = datetime(2026, 4, 28, 6, 0, 0, tzinfo=timezone.utc)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr("datetime.datetime", _FakeDatetime)
