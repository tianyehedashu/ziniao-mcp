"""``SessionManager.open_store_passive`` 与对应 dispatch / CLI 路径回归。

passive 路径的核心契约——**绝不**触碰 nodriver / stealth / sessions state——
只能用纯 mock 验证：真实 `_connect_cdp` 会拉起 CDP WebSocket，
真实 `_apply_stealth_to_browser` 会 evaluate 注入。这里把它们替成 sentinel，
任何意外调用都会立刻把测试炸红。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ziniao_mcp.cli import app as cli_app
from ziniao_mcp.cli.commands import store as store_cmd
from ziniao_webdriver.client import ZiniaoClient
from ziniao_mcp.session import SessionManager, _StoreAlreadyRunning


@pytest.fixture()
def mock_client():
    c = MagicMock(spec=ZiniaoClient)
    c.user_info = {"company": "c", "username": "u", "password": "p"}
    c.socket_port = 16851
    c.heartbeat = MagicMock(return_value=True)
    c.is_process_running = MagicMock(return_value=True)
    c.get_browser_list = MagicMock(return_value=[{"browserId": "1"}])
    return c


@pytest.fixture()
def session(mock_client):
    return SessionManager(mock_client)


# ------------------------------------------------------------------ #
#  SessionManager.open_store_passive
# ------------------------------------------------------------------ #

class TestOpenStorePassive:
    """passive 必须停在 ``debuggingPort`` ready，绝不进 attach / stealth。"""

    @pytest.mark.asyncio
    async def test_does_not_attach_or_inject_stealth(self, session, mock_client):
        mock_client.open_store = MagicMock(return_value={
            "debuggingPort": 9555,
            "browserName": "Shopee MY",
            "launcherPage": "https://shopee.com.my/seller/login",
            "browserOauth": "oauth-1",
        })

        with (
            patch.object(session, "_ensure_client_running", new=AsyncMock()),
            patch.object(session, "_preflight_check", new=AsyncMock()),
            patch("ziniao_mcp.session._wait_cdp_ready", new=AsyncMock(return_value=True)),
            patch("ziniao_mcp.chrome_passive.wait_devtools_http") as mock_wait_http,
            patch("ziniao_mcp.session._connect_cdp", new=AsyncMock()) as mock_connect,
            patch.object(session, "_apply_stealth_to_browser", new=AsyncMock()) as mock_stealth,
            patch.object(session, "setup_tab_listeners", new=AsyncMock()) as mock_listeners,
            patch.object(session, "_save_store_state") as mock_save,
        ):
            out = await session.open_store_passive("1")

        # nodriver / stealth / state file: zero touches
        mock_connect.assert_not_called()
        mock_stealth.assert_not_called()
        mock_listeners.assert_not_called()
        mock_save.assert_not_called()
        # ZiniaoClient.open_store must be invoked with empty js_info to avoid
        # daemon-side stealth bundle co-injection.
        mock_client.open_store.assert_called_once_with("1", js_info="")
        mock_wait_http.assert_called_once_with(9555, 10.0)

        assert out["mode"] == "passive"
        assert out["attached"] is False
        assert out["cdp_port"] == 9555
        assert out["launcher_page"] == "https://shopee.com.my/seller/login"
        assert out["store_name"] == "Shopee MY"
        assert out["reused_existing"] is False
        # store must NOT be registered as an attached session.
        assert "1" not in session._stores

    @pytest.mark.asyncio
    async def test_reuses_already_running_store_without_attach(self, session, mock_client):
        """店铺已在跑：不重新启动浏览器，复用 cdp_port 但仍然不 attach。"""
        mock_client.open_store = MagicMock(side_effect=AssertionError(
            "passive must reuse the running browser, not call open_store again",
        ))

        with (
            patch.object(session, "_ensure_client_running", new=AsyncMock()),
            patch.object(
                session, "_preflight_check",
                new=AsyncMock(side_effect=_StoreAlreadyRunning("1", 9777)),
            ),
            patch(
                "ziniao_mcp.session._read_state_file",
                return_value={"1": {
                    "store_name": "Shopee SG",
                    "launcher_page": "https://shopee.sg/",
                    "browser_oauth": "oauth-2",
                }},
            ),
            patch("ziniao_mcp.chrome_passive.wait_devtools_http") as mock_wait_http,
            patch("ziniao_mcp.session._connect_cdp", new=AsyncMock()) as mock_connect,
            patch.object(session, "_apply_stealth_to_browser", new=AsyncMock()) as mock_stealth,
        ):
            out = await session.open_store_passive("1")

        mock_connect.assert_not_called()
        mock_stealth.assert_not_called()
        mock_wait_http.assert_called_once_with(9777, 10.0)
        assert out == {
            "ok": True,
            "mode": "passive",
            "attached": False,
            "store_id": "1",
            "store_name": "Shopee SG",
            "cdp_port": 9777,
            "launcher_page": "https://shopee.sg/",
            "browser_oauth": "oauth-2",
            "reused_existing": True,
            "message": (
                "Store already running; reusing CDP port without attaching. "
                "Use ``ziniao chrome passive-open --port 9777`` next."
            ),
        }

    @pytest.mark.asyncio
    async def test_open_failure_propagates_clearly(self, session, mock_client):
        mock_client.open_store = MagicMock(return_value=None)

        with (
            patch.object(session, "_ensure_client_running", new=AsyncMock()),
            patch.object(session, "_preflight_check", new=AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="打开店铺失败"):
                await session.open_store_passive("ghost")

    @pytest.mark.asyncio
    async def test_missing_debugging_port_raises(self, session, mock_client):
        mock_client.open_store = MagicMock(return_value={"browserName": "no port"})

        with (
            patch.object(session, "_ensure_client_running", new=AsyncMock()),
            patch.object(session, "_preflight_check", new=AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="CDP 调试端口"):
                await session.open_store_passive("1")


# ------------------------------------------------------------------ #
#  Dispatch RPC: open_store_passive
# ------------------------------------------------------------------ #

class TestDispatchOpenStorePassive:

    @pytest.mark.asyncio
    async def test_routes_to_session_manager_method(self):
        from ziniao_mcp.cli.dispatch import _COMMANDS

        sm = MagicMock()
        sm.open_store_passive = AsyncMock(return_value={
            "ok": True, "mode": "passive", "cdp_port": 9222, "store_id": "1",
        })

        out = await _COMMANDS["open_store_passive"](sm, {"store_id": "1"})

        sm.open_store_passive.assert_awaited_once_with("1")
        assert out["mode"] == "passive"

    @pytest.mark.asyncio
    async def test_missing_store_id_returns_error(self):
        from ziniao_mcp.cli.dispatch import _COMMANDS

        sm = MagicMock()
        sm.open_store_passive = AsyncMock()
        out = await _COMMANDS["open_store_passive"](sm, {})
        sm.open_store_passive.assert_not_awaited()
        assert "store_id" in out["error"]


# ------------------------------------------------------------------ #
#  CLI: ``ziniao store passive-open``
# ------------------------------------------------------------------ #

class TestCliStorePassiveOpen:

    def test_invokes_open_store_passive_rpc(self, monkeypatch):
        seen = {}

        def fake_run(command, args=None):
            seen["command"] = command
            seen["args"] = args or {}
            return {
                "ok": True,
                "mode": "passive",
                "attached": False,
                "store_id": "1",
                "cdp_port": 9222,
                "store_name": "S",
                "launcher_page": "",
                "browser_oauth": "",
                "reused_existing": False,
                "message": "ok",
            }

        monkeypatch.setattr(store_cmd, "run_command", fake_run)

        result = CliRunner().invoke(
            cli_app, ["--json", "store", "passive-open", "1"],
        )

        assert result.exit_code == 0, result.stdout
        assert seen["command"] == "open_store_passive"
        assert seen["args"] == {"store_id": "1"}
        payload = json.loads(result.stdout)
        assert payload["success"] is True
        assert payload["data"]["mode"] == "passive"
        assert payload["data"]["attached"] is False
        # No policy hint when launcher_page is empty.
        assert "policy_hint" not in payload["data"]

    def test_shopee_launcher_page_emits_policy_hint(self, monkeypatch):
        monkeypatch.setattr(
            store_cmd,
            "run_command",
            lambda _c, _a=None: {
                "ok": True,
                "mode": "passive",
                "attached": False,
                "store_id": "1",
                "cdp_port": 9222,
                "store_name": "Shopee MY",
                "launcher_page": "https://shopee.com.my/seller-login",
                "browser_oauth": "x",
                "reused_existing": False,
                "message": "ok",
            },
        )

        result = CliRunner().invoke(
            cli_app, ["--json", "store", "passive-open", "1"],
        )
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert "policy_hint" in payload["data"]
        assert "passive" in payload["data"]["policy_hint"]

    def test_does_not_emit_hint_for_non_high_risk_store(self, monkeypatch):
        monkeypatch.setattr(
            store_cmd,
            "run_command",
            lambda _c, _a=None: {
                "ok": True,
                "mode": "passive",
                "attached": False,
                "store_id": "1",
                "cdp_port": 9222,
                "store_name": "Etsy",
                "launcher_page": "https://www.etsy.com/your/shops",
                "browser_oauth": "x",
                "reused_existing": False,
                "message": "ok",
            },
        )

        result = CliRunner().invoke(
            cli_app, ["--json", "store", "passive-open", "1"],
        )
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert "policy_hint" not in payload["data"]
