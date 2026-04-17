"""ZiniaoClient unit tests — 覆盖 v5/v6 兼容性、响应解析、各 API 方法、端口自动检测。"""

from unittest.mock import patch, MagicMock

import pytest

from ziniao_webdriver.client import ZiniaoClient, detect_ziniao_port


# ------------------------------------------------------------------ #
#  _get_status: statusCode 归一化 (v5 int vs v6 str)
# ------------------------------------------------------------------ #

class TestGetStatus:
    """_get_status 应将 int/str 统一转为 str，None 和缺失要区分处理。"""

    def test_none_response(self):
        assert ZiniaoClient._get_status(None) is None

    def test_missing_status_code(self):
        assert ZiniaoClient._get_status({"data": 1}) is None

    def test_v5_int_zero(self):
        assert ZiniaoClient._get_status({"statusCode": 0}) == "0"

    def test_v6_str_zero(self):
        assert ZiniaoClient._get_status({"statusCode": "0"}) == "0"

    def test_v5_int_auth_error(self):
        assert ZiniaoClient._get_status({"statusCode": -10003}) == "-10003"

    def test_v6_str_auth_error(self):
        assert ZiniaoClient._get_status({"statusCode": "-10003"}) == "-10003"

    def test_v5_int_other(self):
        assert ZiniaoClient._get_status({"statusCode": 1}) == "1"

    def test_v6_str_other(self):
        assert ZiniaoClient._get_status({"statusCode": "1"}) == "1"

    def test_zero_is_falsy_but_not_none(self):
        """statusCode=0 (int) 在 Python 中是 falsy，但不应被视为 None。"""
        assert ZiniaoClient._get_status({"statusCode": 0}) is not None


# ------------------------------------------------------------------ #
#  _process_name: 版本 × 平台 矩阵
# ------------------------------------------------------------------ #

class TestProcessName:
    """_process_name 应根据版本和平台返回正确的进程名。"""

    @pytest.mark.parametrize("version, expected", [
        ("v5", "SuperBrowser.exe"),
        ("v6", "ziniao.exe"),
    ])
    def test_windows(self, version, expected):
        c = ZiniaoClient("path", 1, {}, version=version)
        c._is_windows, c._is_mac, c._is_linux = True, False, False
        assert c._process_name == expected

    @pytest.mark.parametrize("version, expected", [
        ("v5", "SuperBrowser"),
        ("v6", "ziniao"),
    ])
    def test_mac(self, version, expected):
        c = ZiniaoClient("path", 1, {}, version=version)
        c._is_windows, c._is_mac, c._is_linux = False, True, False
        assert c._process_name == expected

    @pytest.mark.parametrize("version, expected", [
        ("v5", "SuperBrowser"),
        ("v6", "ziniaobrowser"),
    ])
    def test_linux(self, version, expected):
        c = ZiniaoClient("path", 1, {}, version=version)
        c._is_windows, c._is_mac, c._is_linux = False, False, True
        assert c._process_name == expected

    def test_unknown_version_falls_back_to_v6(self):
        c = ZiniaoClient("path", 1, {}, version="v6")
        c.version = "v99"
        c._is_windows, c._is_mac, c._is_linux = True, False, False
        assert c._process_name == "ziniao.exe"


# ------------------------------------------------------------------ #
#  _request: 统一响应分发
# ------------------------------------------------------------------ #

class TestRequest:
    """_request 应正确分发 ok / none / auth_error / unsupported / error。"""

    def _make_client(self, http_return):
        c = ZiniaoClient("path", 1, {"company": "c", "username": "u", "password": "p"})
        c._send_http = MagicMock(return_value=http_return)
        return c

    def test_ok_v5_int(self):
        c = self._make_client({"statusCode": 0, "data": "yes"})
        status, r = c._request({"action": "test"}, "测试")
        assert status == "ok"
        assert r["data"] == "yes"

    def test_ok_v6_str(self):
        c = self._make_client({"statusCode": "0", "data": "yes"})
        status, r = c._request({"action": "test"}, "测试")
        assert status == "ok"

    def test_none_when_http_fails(self):
        c = self._make_client(None)
        status, r = c._request({"action": "test"}, "测试")
        assert status == "none"
        assert r is None

    def test_auth_error_v5_int(self):
        c = self._make_client({"statusCode": -10003})
        status, _ = c._request({"action": "test"}, "测试")
        assert status == "auth_error"

    def test_auth_error_v6_str(self):
        c = self._make_client({"statusCode": "-10003"})
        status, _ = c._request({"action": "test"}, "测试")
        assert status == "auth_error"

    def test_unsupported_no_status_code(self):
        c = self._make_client({"message": "no code"})
        status, r = c._request({"action": "test"}, "测试")
        assert status == "unsupported"
        assert r is not None

    def test_error_unknown_code(self):
        c = self._make_client({"statusCode": 999})
        status, _ = c._request({"action": "test"}, "测试")
        assert status == "error"

    def test_request_id_auto_generated(self):
        c = self._make_client({"statusCode": 0})
        c._request({"action": "test"}, "测试")
        sent_data = c._send_http.call_args[0][0]
        assert "requestId" in sent_data

    def test_user_info_merged(self):
        c = self._make_client({"statusCode": 0})
        c._request({"action": "test"}, "测试")
        sent_data = c._send_http.call_args[0][0]
        assert sent_data["company"] == "c"
        assert sent_data["username"] == "u"


# ------------------------------------------------------------------ #
#  heartbeat
# ------------------------------------------------------------------ #

class TestHeartbeat:

    def test_returns_true_when_http_succeeds(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": 0})
        assert client_v6.heartbeat() is True

    def test_returns_false_when_http_fails(self, client_v6):
        client_v6._send_http = MagicMock(return_value=None)
        assert client_v6.heartbeat() is False


# ------------------------------------------------------------------ #
#  update_core: 重试、超时、v5/v6 statusCode 兼容
# ------------------------------------------------------------------ #

class TestUpdateCore:

    def test_immediate_success_v6_str(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "0"})
        assert client_v6.update_core(max_retries=3) is True

    def test_immediate_success_v5_int(self, client_v5):
        client_v5._send_http = MagicMock(return_value={"statusCode": 0})
        assert client_v5.update_core(max_retries=3) is True

    @patch("ziniao_webdriver.client.time.sleep")
    def test_success_after_retries(self, mock_sleep, client_v6):
        responses = [None, {"statusCode": "1"}, {"statusCode": "0"}]
        client_v6._send_http = MagicMock(side_effect=responses)
        assert client_v6.update_core(max_retries=5) is True
        assert client_v6._send_http.call_count == 3

    @patch("ziniao_webdriver.client.time.sleep")
    def test_timeout_returns_false(self, mock_sleep, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "1"})
        assert client_v6.update_core(max_retries=3) is False
        assert client_v6._send_http.call_count == 3

    def test_auth_error_returns_false_immediately(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "-10003"})
        assert client_v6.update_core(max_retries=10) is False
        assert client_v6._send_http.call_count == 1

    def test_no_status_code_returns_false(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"message": "unknown"})
        assert client_v6.update_core(max_retries=10) is False

    @patch("ziniao_webdriver.client.time.sleep")
    def test_none_responses_keep_retrying(self, mock_sleep, client_v6):
        """HTTP 连接失败时应继续重试直到超限。"""
        client_v6._send_http = MagicMock(return_value=None)
        assert client_v6.update_core(max_retries=3) is False
        assert client_v6._send_http.call_count == 3


# ------------------------------------------------------------------ #
#  get_browser_list
# ------------------------------------------------------------------ #

class TestGetBrowserList:

    def test_success_v6(self, client_v6):
        stores = [{"browserId": "1", "browserName": "Shop A"}]
        client_v6._send_http = MagicMock(
            return_value={"statusCode": "0", "browserList": stores}
        )
        assert client_v6.get_browser_list() == stores

    def test_success_v5(self, client_v5):
        stores = [{"browserId": "1"}]
        client_v5._send_http = MagicMock(
            return_value={"statusCode": 0, "browserList": stores}
        )
        assert client_v5.get_browser_list() == stores

    def test_connection_failure_raises(self, client_v6):
        client_v6._send_http = MagicMock(return_value=None)
        with pytest.raises(RuntimeError, match="无法连接紫鸟客户端"):
            client_v6.get_browser_list()

    def test_auth_error_raises(self, client_v6):
        client_v6._send_http = MagicMock(
            return_value={"statusCode": "-10003", "err": "用户名或者密码错误"}
        )
        with pytest.raises(RuntimeError, match="紫鸟登录失败"):
            client_v6.get_browser_list()

    def test_missing_browser_list_key(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "0"})
        assert client_v6.get_browser_list() == []


# ------------------------------------------------------------------ #
#  open_store
# ------------------------------------------------------------------ #

class TestOpenStore:

    def test_success_with_browser_id(self, client_v6):
        resp = {"statusCode": "0", "debuggingPort": 9222, "browserName": "Shop"}
        client_v6._send_http = MagicMock(return_value=resp)
        result = client_v6.open_store("12345")
        assert result == resp
        sent = client_v6._send_http.call_args[0][0]
        assert sent["browserId"] == "12345"
        assert "browserOauth" not in sent

    def test_success_with_browser_oauth(self, client_v6):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        client_v6._send_http = MagicMock(return_value=resp)
        result = client_v6.open_store("abc-oauth-id")
        assert result == resp
        sent = client_v6._send_http.call_args[0][0]
        assert sent["browserOauth"] == "abc-oauth-id"
        assert "browserId" not in sent

    def test_failure_returns_none(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "999"})
        assert client_v6.open_store("12345") is None

    def test_http_error_returns_none(self, client_v6):
        client_v6._send_http = MagicMock(return_value=None)
        assert client_v6.open_store("12345") is None

    def test_v5_int_status_works(self, client_v5):
        resp = {"statusCode": 0, "debuggingPort": 9222}
        client_v5._send_http = MagicMock(return_value=resp)
        assert client_v5.open_store("12345") == resp


# ------------------------------------------------------------------ #
#  close_store
# ------------------------------------------------------------------ #

class TestCloseStore:

    def test_success(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "0"})
        assert client_v6.close_store("oauth-123") is True

    def test_failure(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "500"})
        assert client_v6.close_store("oauth-123") is False

    def test_http_error(self, client_v6):
        client_v6._send_http = MagicMock(return_value=None)
        assert client_v6.close_store("oauth-123") is False

    def test_sends_correct_action(self, client_v6):
        client_v6._send_http = MagicMock(return_value={"statusCode": "0"})
        client_v6.close_store("my-oauth")
        sent = client_v6._send_http.call_args[0][0]
        assert sent["action"] == "stopBrowser"
        assert sent["browserOauth"] == "my-oauth"


# ------------------------------------------------------------------ #
#  kill_process: 版本感知的进程名，使用 subprocess.run 避免 taskkill 的 GBK 输出导致乱码
# ------------------------------------------------------------------ #

class TestKillProcess:

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_v5_windows_kills_by_pid_filtered_by_path(
        self, mock_run, mock_sleep, client_v5,
    ):
        """按 PID 精确终止：只打到 ExecutablePath 匹配 client_path 的进程，
        不会按 /im 模糊匹配到同名的 CLI 壳 (~/.local/bin/ziniao.exe)。
        """
        mock_run.return_value = MagicMock(returncode=0)
        client_v5._is_windows, client_v5._is_mac, client_v5._is_linux = True, False, False
        with patch.object(client_v5, "_find_client_pids", return_value=[1234, 5678]):
            assert client_v5.kill_process(skip_confirm=True) is True
        assert mock_run.call_count == 2
        # 都必须走 /pid，绝不能再出现 /im
        for call in mock_run.call_args_list:
            argv = call[0][0]
            assert "/im" not in argv, "Windows 下按名称模糊终止会误杀 CLI 壳"
            assert argv[:4] == ["taskkill", "/f", "/t", "/pid"]
            assert argv[4] in ("1234", "5678")

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_v6_windows_kills_by_pid_filtered_by_path(
        self, mock_run, mock_sleep, client_v6,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = True, False, False
        with patch.object(client_v6, "_find_client_pids", return_value=[9999]):
            assert client_v6.kill_process(skip_confirm=True) is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == [
            "taskkill", "/f", "/t", "/pid", "9999",
        ]
        assert mock_run.call_args.kwargs.get("check") is False

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_windows_returns_false_and_skips_taskkill_when_no_matching_pids(
        self, mock_run, mock_sleep, client_v6,
    ):
        """回归：_find_client_pids 返回空列表时必须提前返回 False，
        不得继续走 taskkill（避免误暗示"已终止"语义，同时避免未来出现任何
        隐式 /im 回退带来的误杀风险）。
        """
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = True, False, False
        with patch.object(client_v6, "_find_client_pids", return_value=[]):
            assert client_v6.kill_process(skip_confirm=True) is False
        mock_run.assert_not_called()

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_v5_mac(self, mock_run, mock_sleep, client_v5):
        mock_run.return_value = MagicMock(returncode=0)
        client_v5._is_windows, client_v5._is_mac, client_v5._is_linux = False, True, False
        assert client_v5.kill_process(skip_confirm=True) is True
        mock_run.assert_called_once_with(
            ["killall", "SuperBrowser"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        mock_sleep.assert_called_once_with(3)

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_v6_mac(self, mock_run, mock_sleep, client_v6):
        mock_run.return_value = MagicMock(returncode=0)
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = False, True, False
        assert client_v6.kill_process(skip_confirm=True) is True
        mock_run.assert_called_once_with(
            ["killall", "ziniao"],
            capture_output=True,
            timeout=10,
            check=False,
        )

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_v6_linux(self, mock_run, mock_sleep, client_v6):
        mock_run.return_value = MagicMock(returncode=0)
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = False, False, True
        assert client_v6.kill_process(skip_confirm=True) is True
        mock_run.assert_called_once_with(
            ["killall", "ziniaobrowser"],
            capture_output=True,
            timeout=10,
            check=False,
        )

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_mac_returns_false_and_does_not_sleep_when_killall_misses(
        self, mock_run, mock_sleep, client_v6,
    ):
        """跨平台语义对齐：Mac 下 killall 未找到进程（rc=1）时必须返回 False，
        与 Windows 的"未匹配 PID → False"行为一致；且不应该白等 3s。
        """
        mock_run.return_value = MagicMock(returncode=1)
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = False, True, False
        assert client_v6.kill_process(skip_confirm=True) is False
        mock_sleep.assert_not_called()

    @patch("ziniao_webdriver.client.time.sleep")
    @patch("ziniao_webdriver.client.subprocess.run")
    def test_linux_returns_false_and_does_not_sleep_when_killall_misses(
        self, mock_run, mock_sleep, client_v6,
    ):
        mock_run.return_value = MagicMock(returncode=1)
        client_v6._is_windows, client_v6._is_mac, client_v6._is_linux = False, False, True
        assert client_v6.kill_process(skip_confirm=True) is False
        mock_sleep.assert_not_called()


# ------------------------------------------------------------------ #
#  detect_ziniao_port: 自动检测紫鸟客户端端口
# ------------------------------------------------------------------ #

class TestDetectZiniaoPort:

    @patch("ziniao_webdriver.client.subprocess.check_output")
    @patch("ziniao_webdriver.client.platform.system", return_value="Windows")
    def test_single_port_windows(self, _mock_sys, mock_output):
        mock_output.return_value = (
            'CommandLine\n'
            '"D:\\ziniao\\ziniao.exe" --run_type=web_driver --ipc_type=http --port=16851\n'
            '"D:\\ziniao\\ziniao.exe" --type=renderer\n'
        )
        assert detect_ziniao_port() == 16851

    @patch("ziniao_webdriver.client.subprocess.check_output")
    @patch("ziniao_webdriver.client.platform.system", return_value="Linux")
    def test_single_port_linux(self, _mock_sys, mock_output):
        mock_output.return_value = (
            'user  1234  0.0  ziniao --run_type=web_driver --port=9480\n'
            'user  1235  0.0  ziniao --type=renderer\n'
        )
        assert detect_ziniao_port() == 9480

    @patch("ziniao_webdriver.client.subprocess.check_output")
    @patch("ziniao_webdriver.client.platform.system", return_value="Windows")
    def test_no_port_flag_returns_none(self, _mock_sys, mock_output):
        mock_output.return_value = (
            'CommandLine\n'
            '"D:\\ziniao\\ziniao.exe" --type=renderer\n'
        )
        assert detect_ziniao_port() is None

    @patch("ziniao_webdriver.client.subprocess.check_output")
    @patch("ziniao_webdriver.client.platform.system", return_value="Windows")
    def test_multiple_ports_returns_none(self, _mock_sys, mock_output):
        mock_output.return_value = (
            'CommandLine\n'
            '"D:\\ziniao\\ziniao.exe" --port=16851\n'
            '"D:\\ziniao\\ziniao.exe" --port=16852\n'
        )
        assert detect_ziniao_port() is None

    @patch("ziniao_webdriver.client.subprocess.check_output", side_effect=FileNotFoundError)
    @patch("ziniao_webdriver.client.platform.system", return_value="Windows")
    def test_process_error_returns_none(self, _mock_sys, _mock_output):
        assert detect_ziniao_port() is None

    @patch("ziniao_webdriver.client.subprocess.check_output")
    @patch("ziniao_webdriver.client.platform.system", return_value="Windows")
    def test_empty_output_returns_none(self, _mock_sys, mock_output):
        mock_output.return_value = ""
        assert detect_ziniao_port() is None
