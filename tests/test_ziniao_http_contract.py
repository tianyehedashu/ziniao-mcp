"""ZiniaoClient HTTP 协议契约测试。

mock ``_send_http`` 并断言关键 action 的 JSON payload 形状（键名、值类型），
使紫鸟客户端大版本变更时能快速发现协议退化。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ziniao_webdriver.client import ZiniaoClient

_USER_INFO = {"company": "acme", "username": "bot", "password": "s3cret"}

_OK_RESPONSE = {"statusCode": "0"}


@pytest.fixture()
def client():
    return ZiniaoClient(
        client_path=r"C:\fake\ziniao.exe",
        socket_port=16851,
        user_info=_USER_INFO,
        version="v6",
    )


def _capture_payload(client: ZiniaoClient, *, response=None):
    """拦截 _send_http，返回 (captured_dict, original_return)。"""
    captured: dict = {}
    orig = response if response is not None else _OK_RESPONSE

    def side_effect(data, timeout=120):
        captured.update(data)
        return orig

    with patch.object(client, "_send_http", side_effect=side_effect):
        yield captured


# ------------------------------------------------------------------ #
#  heartbeat
# ------------------------------------------------------------------ #

class TestHeartbeatContract:

    def test_payload_keys(self, client):
        gen = _capture_payload(client)
        payload = next(gen)
        client.heartbeat()
        assert payload["action"] == "heartbeat"
        assert "requestId" in payload
        for k in _USER_INFO:
            assert k in payload, f"heartbeat 缺少 user_info 键 '{k}'"


# ------------------------------------------------------------------ #
#  updateCore
# ------------------------------------------------------------------ #

class TestUpdateCoreContract:

    def test_payload_keys(self, client):
        gen = _capture_payload(client)
        payload = next(gen)
        client.update_core(max_retries=1)
        assert payload["action"] == "updateCore"
        assert "requestId" in payload
        for k in _USER_INFO:
            assert k in payload


# ------------------------------------------------------------------ #
#  getBrowserList
# ------------------------------------------------------------------ #

class TestGetBrowserListContract:

    def test_payload_keys(self, client):
        resp = {"statusCode": "0", "browserList": []}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.get_browser_list()
        assert payload["action"] == "getBrowserList"
        assert "requestId" in payload
        for k in _USER_INFO:
            assert k in payload


# ------------------------------------------------------------------ #
#  startBrowser (open_store)
# ------------------------------------------------------------------ #

_REQUIRED_START_BROWSER_KEYS = {
    "action", "isWaitPluginUpdate", "isHeadless",
    "isWebDriverReadOnlyMode", "cookieTypeLoad", "cookieTypeSave",
    "runMode", "isLoadUserPlugin", "pluginIdType",
    "privacyMode", "notPromptForDownload",
}


class TestStartBrowserContract:

    def test_payload_with_browser_id(self, client):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.open_store("12345")
        for key in _REQUIRED_START_BROWSER_KEYS:
            assert key in payload, f"open_store 缺少 '{key}'"
        assert payload["action"] == "startBrowser"
        assert payload["browserId"] == "12345"
        assert "browserOauth" not in payload

    def test_payload_with_browser_oauth(self, client):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.open_store("abc-oauth-token")
        assert "browserOauth" in payload
        assert payload["browserOauth"] == "abc-oauth-token"
        assert "browserId" not in payload

    def test_js_info_injected_when_provided(self, client):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.open_store("12345", js_info="console.log('hi')")
        assert "injectJsInfo" in payload

    def test_js_info_absent_when_empty(self, client):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.open_store("12345", js_info="")
        assert "injectJsInfo" not in payload

    def test_default_flag_values(self, client):
        resp = {"statusCode": "0", "debuggingPort": 9222}
        gen = _capture_payload(client, response=resp)
        payload = next(gen)
        client.open_store("12345")
        assert payload["isHeadless"] == 0
        assert payload["isWebDriverReadOnlyMode"] == 0
        assert payload["privacyMode"] == 0
        assert payload["cookieTypeSave"] == 0
        assert payload["runMode"] == "1"


# ------------------------------------------------------------------ #
#  stopBrowser (close_store)
# ------------------------------------------------------------------ #

class TestStopBrowserContract:

    def test_payload_keys(self, client):
        gen = _capture_payload(client)
        payload = next(gen)
        client.close_store("my-oauth-id")
        assert payload["action"] == "stopBrowser"
        assert payload["browserOauth"] == "my-oauth-id"
        assert "duplicate" in payload


# ------------------------------------------------------------------ #
#  exit
# ------------------------------------------------------------------ #

class TestExitContract:

    def test_payload_keys(self, client):
        gen = _capture_payload(client)
        payload = next(gen)
        client.get_exit()
        assert payload["action"] == "exit"
