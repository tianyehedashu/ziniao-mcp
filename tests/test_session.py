"""SessionManager unit tests — 覆盖客户端生命周期管理和 heartbeat 委托。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ziniao_webdriver.client import ZiniaoClient
from ziniao_mcp.session import (
    SessionManager,
    _format_cdp_connection_error,
    _wait_cdp_ready,
)


@pytest.fixture()
def mock_client():
    c = MagicMock(spec=ZiniaoClient)
    c.user_info = {"company": "c", "username": "u", "password": "p"}
    c.socket_port = 16851
    c.heartbeat = MagicMock(return_value=True)
    c.is_process_running = MagicMock(return_value=False)
    c.kill_process = MagicMock(return_value=True)
    c.start_browser = MagicMock()
    c.update_core = MagicMock(return_value=True)
    c.get_browser_list = MagicMock(return_value=[{"browserId": "1"}])
    c.get_exit = MagicMock()
    c.close_store = MagicMock(return_value=True)
    return c


@pytest.fixture()
def session(mock_client):
    return SessionManager(mock_client)


# ------------------------------------------------------------------ #
#  CDP 辅助: _format_cdp_connection_error, _wait_cdp_ready
# ------------------------------------------------------------------ #

class TestCdpHelpers:

    def test_format_cdp_connection_error_includes_port_and_checklist(self):
        msg = _format_cdp_connection_error(9222, OSError("dummy"))
        assert "9222" in msg
        assert "手动打开" in msg or "远程调试" in msg

    def test_format_cdp_connection_error_adds_refused_hint_for_1225(self):
        msg = _format_cdp_connection_error(9222, OSError("[WinError 1225] 远程计算机拒绝网络连接"))
        assert "1225" in msg or "拒绝" in msg
        assert "端口未监听" in msg or "被拒绝" in msg

    def test_format_cdp_connection_error_adds_refused_hint_for_refused(self):
        msg = _format_cdp_connection_error(9222, ConnectionRefusedError("refused"))
        assert "端口未监听" in msg or "被拒绝" in msg

    @pytest.mark.asyncio
    @patch("ziniao_mcp.session._is_cdp_alive")
    async def test_wait_cdp_ready_returns_true_when_alive_immediately(self, mock_alive):
        mock_alive.return_value = True
        got = await _wait_cdp_ready(9222, timeout_sec=5.0, interval=1.0)
        assert got is True
        mock_alive.assert_called()

    @pytest.mark.asyncio
    @patch("ziniao_mcp.session._is_cdp_alive")
    async def test_wait_cdp_ready_returns_false_on_timeout(self, mock_alive):
        mock_alive.return_value = False
        got = await _wait_cdp_ready(9222, timeout_sec=0.5, interval=0.2)
        assert got is False


# ------------------------------------------------------------------ #
#  _is_client_running: 委托给 client.heartbeat
# ------------------------------------------------------------------ #

class TestIsClientRunning:

    @pytest.mark.asyncio
    async def test_delegates_to_heartbeat(self, session, mock_client):
        mock_client.heartbeat.return_value = True
        result = await session._is_client_running()
        assert result is True
        mock_client.heartbeat.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_heartbeat_fails(self, session, mock_client):
        mock_client.heartbeat.return_value = False
        result = await session._is_client_running()
        assert result is False


# ------------------------------------------------------------------ #
#  _ensure_client_running
# ------------------------------------------------------------------ #

class TestEnsureClientRunning:

    @pytest.mark.asyncio
    async def test_skips_if_already_started_and_running(self, session, mock_client):
        session._client_started = True
        mock_client.heartbeat.return_value = True
        await session._ensure_client_running()
        mock_client.kill_process.assert_not_called()
        mock_client.start_browser.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_started_if_running_but_not_flagged(self, session, mock_client):
        session._client_started = False
        mock_client.heartbeat.return_value = True
        await session._ensure_client_running()
        assert session._client_started is True
        mock_client.kill_process.assert_not_called()

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=None)
    async def test_full_startup_when_not_running(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.return_value = False
        await session._ensure_client_running()
        mock_client.kill_process.assert_not_called()
        mock_client.start_browser.assert_called_once()
        mock_client.update_core.assert_called_once()
        assert session._client_started is True


# ------------------------------------------------------------------ #
#  start_client
# ------------------------------------------------------------------ #

class TestStartClient:

    @pytest.mark.asyncio
    async def test_skips_if_already_running(self, session, mock_client):
        mock_client.heartbeat.return_value = True
        result = await session.start_client()
        assert "已在运行" in result
        mock_client.start_browser.assert_not_called()

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=None)
    async def test_starts_when_not_running(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.side_effect = [False, True]
        result = await session.start_client()
        assert "已启动" in result
        mock_client.kill_process.assert_not_called()
        mock_client.start_browser.assert_called_once()
        mock_client.update_core.assert_called_once()
        assert session._client_started is True

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=None)
    async def test_warns_when_still_unreachable_after_start(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.return_value = False
        result = await session.start_client()
        assert "无法连接" in result

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=9480)
    async def test_auto_switches_port_when_mismatch(self, _mock_detect, session, mock_client):
        """配置端口无响应，但客户端在其他端口运行时自动切换。"""
        mock_client.heartbeat.side_effect = [False, True]
        result = await session.start_client()
        assert "9480" in result
        assert "自动切换" in result
        assert mock_client.socket_port == 9480


# ------------------------------------------------------------------ #
#  _ensure_client_running: 端口自动检测
# ------------------------------------------------------------------ #

class TestEnsureClientRunningPortDetection:

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=9480)
    async def test_switches_to_detected_port(self, _mock_detect, session, mock_client):
        """heartbeat 失败后应检测实际端口并切换。"""
        mock_client.heartbeat.side_effect = [False, True]
        await session._ensure_client_running()
        assert mock_client.socket_port == 9480
        assert session._client_started is True
        mock_client.start_browser.assert_not_called()

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=None)
    async def test_starts_browser_when_no_detection(self, _mock_detect, session, mock_client):
        """检测不到端口时应正常启动客户端。"""
        mock_client.heartbeat.return_value = False
        await session._ensure_client_running()
        mock_client.start_browser.assert_called_once()
        mock_client.update_core.assert_called_once()


# ------------------------------------------------------------------ #
#  list_stores
# ------------------------------------------------------------------ #

class TestListStores:

    @pytest.mark.asyncio
    async def test_returns_browser_list(self, session, mock_client):
        mock_client.heartbeat.return_value = True
        session._client_started = True
        stores = [{"browserId": "1", "browserName": "Shop A"}]
        mock_client.get_browser_list.return_value = stores
        result = await session.list_stores()
        assert result == stores

    @pytest.mark.asyncio
    @patch("ziniao_webdriver.detect_ziniao_port", return_value=None)
    async def test_ensures_client_running_first(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.return_value = False
        mock_client.get_browser_list.return_value = []
        await session.list_stores()
        mock_client.start_browser.assert_called_once()


# ------------------------------------------------------------------ #
#  stop_client
# ------------------------------------------------------------------ #

class TestStopClient:

    @pytest.mark.asyncio
    async def test_calls_exit(self, session, mock_client):
        await session.stop_client()
        mock_client.get_exit.assert_called_once()
        assert session._client_started is False


# ------------------------------------------------------------------ #
#  connect_chrome: stealth 须在「已有 tab」之后（含 about:blank 新建）
# ------------------------------------------------------------------ #


class TestConnectChromeStealthOrder:

    @pytest.mark.asyncio
    @patch.object(SessionManager, "_save_store_state")
    @patch.object(SessionManager, "_sync_viewport_to_window", new_callable=AsyncMock)
    @patch.object(SessionManager, "setup_tab_listeners", new_callable=AsyncMock)
    @patch.object(SessionManager, "_evaluate_stealth_on_tab", new_callable=AsyncMock)
    @patch.object(SessionManager, "_apply_stealth_to_browser", new_callable=AsyncMock)
    @patch("ziniao_mcp.session._filter_tabs")
    @patch("ziniao_mcp.session._is_cdp_alive", new_callable=AsyncMock)
    @patch("ziniao_mcp.session._connect_cdp", new_callable=AsyncMock)
    async def test_apply_stealth_after_blank_tab_when_initially_empty(
        self,
        mock_connect_cdp,
        mock_alive,
        mock_filter_tabs,
        mock_apply_stealth,
        _mock_eval_tab,
        _mock_setup,
        _mock_sync,
        _mock_save,
        mock_client,
    ):
        """避免先 apply_stealth（0 个 tab）再 get：新建页无 OnNewDocument 注册。"""
        mock_alive.return_value = True
        tab_obj = MagicMock()
        browser = MagicMock()
        browser.tabs = []

        async def _fill_tabs(*_a, **_k):
            browser.tabs = [tab_obj]

        browser.get = AsyncMock(side_effect=_fill_tabs)
        mock_connect_cdp.return_value = browser
        mock_filter_tabs.side_effect = [[], [tab_obj]]

        sm = SessionManager(mock_client)
        await sm.connect_chrome(9222)

        browser.get.assert_awaited()
        mock_apply_stealth.assert_awaited_once()
        # connect_chrome 现在并行 evaluate 所有 tab（`apply_stealth` 内部 gather 保证速度）。
        assert mock_apply_stealth.await_args.kwargs.get("evaluate_existing_documents") is True
        # Chrome 场景默认抹平 WebGL vendor，避免真实 GPU 在 WebGL Report 泄露。
        assert mock_apply_stealth.await_args.kwargs.get("webgl_vendor") is True
        assert mock_apply_stealth.await_args.args[0] is browser
        assert browser.tabs, "stealth 应在 browser.get 填充 tabs 之后执行"
