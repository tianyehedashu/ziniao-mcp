"""Chrome passive-open CLI should avoid daemon/CDP Runtime attachment."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ziniao_mcp import chrome_passive as chrome_passive_mod
from ziniao_mcp.cli import app
from ziniao_mcp.cli.commands import chrome as chrome_cmd
from ziniao_mcp.cli.commands import chrome_input_cli


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

    monkeypatch.setattr(chrome_passive_mod.request, "Request", fake_request)
    monkeypatch.setattr(chrome_passive_mod.request, "urlopen", fake_urlopen)

    chrome_passive_mod.passive_open_devtools_tab(
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

    def fake_passive_open(port: int, url: str, timeout: float = 10.0, *, save_as: str | None = None) -> dict:
        calls.append((port, url, save_as))
        assert timeout == 10.0
        return {"ok": True, "id": "target-1", "url": url, "title": ""}

    def fail_run_command(*_args, **_kwargs):
        raise AssertionError("passive-open must not call the ziniao daemon")

    monkeypatch.setattr(chrome_cmd, "passive_open_devtools_tab", fake_passive_open)
    monkeypatch.setattr(chrome_cmd, "run_command", fail_run_command)

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "chrome",
            "passive-open",
            "https://example.com/",
            "--port",
            "9222",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [(9222, "https://example.com/", None)]
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
    monkeypatch.setattr(chrome_cmd, "launch_passive_chrome", fake_launch_passive_chrome)
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


def test_resolve_target_ws_url(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self) -> bytes:
            return json.dumps(
                [
                    {"id": "A", "webSocketDebuggerUrl": ""},
                    {"id": "B", "webSocketDebuggerUrl": "ws://127.0.0.1/b"},
                ],
            ).encode("utf-8")

    monkeypatch.setattr(chrome_passive_mod.request, "urlopen", lambda _req, timeout=10.0: FakeResponse())
    assert chrome_passive_mod.resolve_target_ws_url(9222, "B") == "ws://127.0.0.1/b"


def test_resolve_target_ws_url_missing(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self) -> bytes:
            return json.dumps([{"id": "A", "webSocketDebuggerUrl": ""}]).encode("utf-8")

    monkeypatch.setattr(chrome_passive_mod.request, "urlopen", lambda _req, timeout=10.0: FakeResponse())
    with pytest.raises(RuntimeError, match="No webSocketDebuggerUrl"):
        chrome_passive_mod.resolve_target_ws_url(9222, "A")


def test_chrome_passive_open_passes_save_as(monkeypatch):
    calls: list[tuple[int, str, str | None]] = []

    def fake_passive_open(port: int, url: str, timeout: float = 10.0, *, save_as: str | None = None) -> dict:
        calls.append((port, url, save_as))
        return {"ok": True, "id": "t1", "url": url}

    monkeypatch.setattr(chrome_cmd, "passive_open_devtools_tab", fake_passive_open)

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "chrome",
            "passive-open",
            "https://example.com/",
            "--port",
            "9224",
            "--save-as",
            "mytab",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert calls == [(9224, "https://example.com/", "mytab")]


def test_chrome_passive_open_shopee_adds_policy_hint(monkeypatch):
    def fake_passive_open(port: int, url: str, timeout: float = 10.0, *, save_as: str | None = None) -> dict:
        return {"ok": True, "id": "t1", "url": url}

    monkeypatch.setattr(chrome_cmd, "passive_open_devtools_tab", fake_passive_open)

    result = CliRunner().invoke(
        app,
        ["--json", "chrome", "passive-open", "https://shopee.com.my/", "--port", "9222"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "policy_hint" in payload["data"]


def test_chrome_passive_target_list_json(monkeypatch):
    monkeypatch.setattr(chrome_cmd, "list_passive_target_aliases", lambda: {"tab1": {"port": 9222}})

    result = CliRunner().invoke(app, ["--json", "chrome", "passive-target", "list"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["count"] == 1
    assert payload["data"]["aliases"]["tab1"]["port"] == 9222


def test_chrome_input_click_no_daemon(monkeypatch):
    calls: list[tuple] = []

    def fake_click(ws: str, x: float, y: float, **kwargs) -> None:
        calls.append((ws, x, y, kwargs.get("button")))

    monkeypatch.setattr(chrome_input_cli, "input_mouse_click", fake_click)

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "chrome",
            "input",
            "click",
            "--ws-url",
            "ws://127.0.0.1/fake",
            "--x",
            "12",
            "--y",
            "34",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert calls == [("ws://127.0.0.1/fake", 12.0, 34.0, "left")]


def test_chrome_input_alias_re_resolves_when_target_still_live(monkeypatch):
    """Alias snapshot may go stale; CLI must re-resolve via /json/list and
    rewrite the cache so subsequent runs hit the fresh URL."""
    saved: list[dict] = []

    monkeypatch.setattr(
        chrome_input_cli,
        "load_passive_target_alias",
        lambda _alias: {
            "port": 9222,
            "target_id": "T1",
            "webSocketDebuggerUrl": "ws://127.0.0.1/old",
            "page_url": "https://example.com/",
        },
    )
    monkeypatch.setattr(
        chrome_input_cli,
        "resolve_target_ws_url",
        lambda port, tid: "ws://127.0.0.1/new",
    )

    def fake_save(alias, **kwargs):
        saved.append({"alias": alias, **kwargs})

    monkeypatch.setattr(chrome_input_cli, "save_passive_target_alias", fake_save)

    clicks: list[str] = []
    monkeypatch.setattr(
        chrome_input_cli,
        "input_mouse_click",
        lambda ws, x, y, **kw: clicks.append(ws),
    )

    result = CliRunner().invoke(
        app,
        ["--json", "chrome", "input", "click", "--alias", "tab1", "--x", "1", "--y", "2"],
    )
    assert result.exit_code == 0, result.stdout
    assert clicks == ["ws://127.0.0.1/new"], "Stale ws should be replaced before the click."
    assert saved and saved[0]["web_socket_debugger_url"] == "ws://127.0.0.1/new"


def test_chrome_input_alias_dead_target_raises_helpful_error(monkeypatch):
    """When ``/json/list`` no longer knows the target, fail loudly with a
    pointer to ``passive-open --save-as`` instead of opening a doomed WS."""
    monkeypatch.setattr(
        chrome_input_cli,
        "load_passive_target_alias",
        lambda _alias: {
            "port": 9222,
            "target_id": "GONE",
            "webSocketDebuggerUrl": "ws://127.0.0.1/cached",
            "page_url": "",
        },
    )

    def boom(_port, _tid):
        raise RuntimeError("No webSocketDebuggerUrl for target id='GONE' on port 9222")

    monkeypatch.setattr(chrome_input_cli, "resolve_target_ws_url", boom)

    sentinel = {"called": False}

    def must_not_run(*_a, **_kw):
        sentinel["called"] = True

    monkeypatch.setattr(chrome_input_cli, "input_mouse_click", must_not_run)

    result = CliRunner().invoke(
        app,
        ["chrome", "input", "click", "--alias", "tab1", "--x", "1", "--y", "2"],
    )
    assert result.exit_code != 0
    assert sentinel["called"] is False
    assert "passive-open" in (result.stdout + (result.stderr or ""))


def test_passive_targets_atomic_write(monkeypatch, tmp_path):
    """``save_passive_target_alias`` must use a tmp+rename pattern so a crash
    mid-write can never leave half-written JSON that ``_read`` would treat as
    empty (which would silently delete every existing alias)."""
    state_path = tmp_path / "passive_targets.json"
    monkeypatch.setattr(
        chrome_passive_mod, "passive_targets_state_path", lambda: state_path,
    )

    chrome_passive_mod.save_passive_target_alias(
        "tab1",
        port=9222,
        target_id="T1",
        web_socket_debugger_url="ws://127.0.0.1/a",
        page_url="https://example.com/",
    )
    assert state_path.is_file()

    real_replace = chrome_passive_mod.os.replace

    def boom_replace(_src, _dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(chrome_passive_mod.os, "replace", boom_replace)

    with pytest.raises(OSError, match="simulated rename failure"):
        chrome_passive_mod.save_passive_target_alias(
            "tab2",
            port=9223,
            target_id="T2",
            web_socket_debugger_url="ws://127.0.0.1/b",
            page_url="",
        )

    monkeypatch.setattr(chrome_passive_mod.os, "replace", real_replace)
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert "tab1" in on_disk["aliases"], "Existing alias must survive a failed write."
    assert "tab2" not in on_disk["aliases"], "Half-written tab2 must not appear."
    leftover_tmps = list(tmp_path.glob("passive_targets.json.tmp.*"))
    assert leftover_tmps == [], "Failed atomic writes must not leave .tmp.* files behind."
