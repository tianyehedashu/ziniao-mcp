"""Chrome passive-open CLI should avoid daemon/CDP Runtime attachment."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from ziniao_mcp.cli import app
from ziniao_mcp.cli.commands import chrome as chrome_cmd


def test_passive_open_preserves_url_query_syntax_in_devtools_endpoint(monkeypatch):
    captured: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self) -> bytes:
            return b'{"id":"target-1","url":"ok","title":"","type":"page"}'

    def fake_request(endpoint: str, method: str):
        captured["endpoint"] = endpoint
        captured["method"] = method
        return object()

    def fake_urlopen(_req, timeout: float):
        assert timeout == 10.0
        return FakeResponse()

    monkeypatch.setattr(chrome_cmd.request, "Request", fake_request)
    monkeypatch.setattr(chrome_cmd.request, "urlopen", fake_urlopen)

    chrome_cmd._passive_open_devtools_tab(
        9222,
        "https://shopee.com.my/item?mmp_pid=a&x=1#/path",
    )

    assert captured["method"] == "PUT"
    assert captured["endpoint"] == (
        "http://127.0.0.1:9222/json/new?"
        "https://shopee.com.my/item?mmp_pid=a&x=1%23/path"
    )


def test_chrome_passive_open_uses_devtools_http_without_daemon(monkeypatch):
    calls: list[tuple[int, str]] = []

    def fake_passive_open(port: int, url: str, timeout: float = 10.0) -> dict:
        calls.append((port, url))
        assert timeout == 10.0
        return {"ok": True, "id": "target-1", "url": url, "title": ""}

    def fail_run_command(*_args, **_kwargs):
        raise AssertionError("passive-open must not call the ziniao daemon")

    monkeypatch.setattr(chrome_cmd, "_passive_open_devtools_tab", fake_passive_open)
    monkeypatch.setattr(chrome_cmd, "run_command", fail_run_command)

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "chrome",
            "passive-open",
            "shopee.com.my",
            "--port",
            "9222",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [(9222, "shopee.com.my")]
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["id"] == "target-1"


def test_chrome_launch_passive_starts_chrome_without_daemon(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_launch_passive_chrome(**kwargs) -> dict:
        calls.append(kwargs)
        return {
            "ok": True,
            "mode": "passive",
            "pid": 12345,
            "cdp_port": kwargs["cdp_port"],
            "user_data_dir": kwargs["user_data_dir"],
            "executable_path": kwargs["executable_path"],
        }

    def fail_run_command(*_args, **_kwargs):
        raise AssertionError("launch-passive must not call the ziniao daemon")

    profile = tmp_path / "profile"
    monkeypatch.setattr(chrome_cmd, "_launch_passive_chrome", fake_launch_passive_chrome)
    monkeypatch.setattr(chrome_cmd, "run_command", fail_run_command)

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "chrome",
            "launch-passive",
            "--port",
            "9223",
            "--user-data-dir",
            str(profile),
            "--executable-path",
            "C:/Chrome/chrome.exe",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [
        {
            "executable_path": "C:/Chrome/chrome.exe",
            "cdp_port": 9223,
            "user_data_dir": str(profile),
            "headless": False,
            "url": "",
        }
    ]
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["mode"] == "passive"
