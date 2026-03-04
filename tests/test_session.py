"""SessionManager unit tests — 覆盖客户端生命周期管理和 heartbeat 委托。"""

from unittest.mock import MagicMock, patch

import pytest

from ziniao_webdriver.client import ZiniaoClient
from ziniao_mcp.session import SessionManager


@pytest.fixture()
def mock_client():
    c = MagicMock(spec=ZiniaoClient)
    c.user_info = {"company": "c", "username": "u", "password": "p"}
    c.socket_port = 16851
    c.heartbeat = MagicMock(return_value=True)
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
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=None)
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
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=None)
    async def test_starts_when_not_running(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.side_effect = [False, True]
        result = await session.start_client()
        assert "已启动" in result
        mock_client.kill_process.assert_not_called()
        mock_client.start_browser.assert_called_once()
        mock_client.update_core.assert_called_once()
        assert session._client_started is True

    @pytest.mark.asyncio
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=None)
    async def test_warns_when_still_unreachable_after_start(self, _mock_detect, session, mock_client):
        mock_client.heartbeat.return_value = False
        result = await session.start_client()
        assert "无法连接" in result

    @pytest.mark.asyncio
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=9480)
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
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=9480)
    async def test_switches_to_detected_port(self, _mock_detect, session, mock_client):
        """heartbeat 失败后应检测实际端口并切换。"""
        mock_client.heartbeat.side_effect = [False, True]
        await session._ensure_client_running()
        assert mock_client.socket_port == 9480
        assert session._client_started is True
        mock_client.start_browser.assert_not_called()

    @pytest.mark.asyncio
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=None)
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
    @patch("ziniao_mcp.session.detect_ziniao_port", return_value=None)
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
