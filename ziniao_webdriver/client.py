"""
紫鸟 WebDriver 客户端

封装与紫鸟客户端的 HTTP 通信，支持启动客户端、打开/关闭店铺、获取 CDP 调试端口。
CDP 调试端口由 startBrowser 成功后自动开启，在返回的 debuggingPort 中。
"""

import json
import os
import platform
import subprocess
import time
import uuid
from typing import Literal, Optional

import requests


class ZiniaoClient:
    """紫鸟 WebDriver 客户端，封装与紫鸟客户端的 HTTP 通信及浏览器操作。"""

    def __init__(
        self,
        client_path: str,
        socket_port: int,
        user_info: dict[str, str],
        version: Literal["v5", "v6"] = "v6",
    ):
        """
        :param client_path: 紫鸟客户端程序路径
        :param socket_port: 与客户端通信的 HTTP 端口
        :param user_info: 企业登录信息 {"company", "username", "password"}
        :param version: 客户端版本 v5 或 v6
        """
        self.client_path = client_path
        self.socket_port = socket_port
        self.user_info = user_info
        self.version = version

        self._is_windows = platform.system() == "Windows"
        self._is_mac = platform.system() == "Darwin"
        self._is_linux = platform.system() == "Linux"

    def _send_http(self, data: dict) -> Optional[dict]:
        """向紫鸟客户端发送 HTTP 请求。"""
        try:
            url = f"http://127.0.0.1:{self.socket_port}"
            response = requests.post(
                url, json.dumps(data).encode("utf-8"), timeout=120
            )
            return json.loads(response.text)
        except Exception as err:
            print(err)
            return None

    def start_browser(self) -> None:
        """以 WebDriver 模式启动紫鸟客户端。"""
        try:
            if self._is_windows:
                cmd = [
                    self.client_path,
                    "--run_type=web_driver",
                    "--ipc_type=http",
                    f"--port={self.socket_port}",
                ]
            elif self._is_mac:
                cmd = [
                    "open",
                    "-a",
                    self.client_path,
                    "--args",
                    "--run_type=web_driver",
                    "--ipc_type=http",
                    f"--port={self.socket_port}",
                ]
            elif self._is_linux:
                cmd = [
                    self.client_path,
                    "--no-sandbox",
                    "--run_type=web_driver",
                    "--ipc_type=http",
                    f"--port={self.socket_port}",
                ]
            else:
                return
            subprocess.Popen(cmd)
            time.sleep(5)
        except Exception as e:
            print(f"启动客户端失败: {e}")
            raise

    def kill_process(self, skip_confirm: bool = False) -> bool:
        """
        终止紫鸟客户端已启动的进程。
        :param skip_confirm: 若为 True 则跳过确认
        :return: 是否已执行终止
        """
        if not skip_confirm:
            confirmation = input(
                "在启动之前，需要先关闭紫鸟浏览器的主进程，确定要终止进程吗？(y/n): "
            )
            if confirmation.lower() != "y":
                return False

        if self._is_windows:
            process_name = "SuperBrowser.exe" if self.version == "v5" else "ziniao.exe"
            os.system(f"taskkill /f /t /im {process_name}")
        elif self._is_mac:
            os.system("killall ziniao")
        elif self._is_linux:
            os.system("killall ziniaobrowser")
        else:
            return False

        time.sleep(3)
        return True

    def update_core(self) -> bool:
        """
        下载所有内核，打开店铺前调用（客户端 5.285.7 以上）。
        :return: 是否更新成功
        """
        data = {
            "action": "updateCore",
            "requestId": str(uuid.uuid4()),
        }
        data.update(self.user_info)

        while True:
            result = self._send_http(data)
            if result is None:
                print("等待客户端启动...")
                time.sleep(2)
                continue
            if result.get("statusCode") is None or result.get("statusCode") == -10003:
                print("当前版本不支持此接口，请升级客户端")
                return False
            if result.get("statusCode") == 0:
                print("更新内核完成")
                return True
            print(f"等待更新内核: {json.dumps(result)}")
            time.sleep(2)

    def get_browser_list(self) -> list[dict]:
        """获取店铺列表。"""
        data = {
            "action": "getBrowserList",
            "requestId": str(uuid.uuid4()),
        }
        data.update(self.user_info)

        r = self._send_http(data)
        if r is None:
            return []
        if str(r.get("statusCode")) == "0":
            return r.get("browserList") or []
        if str(r.get("statusCode")) == "-10003":
            print(f"登录错误: {json.dumps(r, ensure_ascii=False)}")
            return []
        print(f"获取店铺列表失败: {json.dumps(r, ensure_ascii=False)}")
        return []

    def open_store(
        self,
        store_info: str,
        is_web_driver_read_only_mode: int = 0,
        is_privacy: int = 0,
        is_headless: int = 0,
        cookie_type_save: int = 0,
        js_info: str = "",
    ) -> Optional[dict]:
        """
        打开紫鸟店铺。成功后返回包含 debuggingPort（CDP 端口）等信息的字典。

        :param store_info: 店铺 ID（browserId 或 browserOauth）
        :return: 成功时返回包含 debuggingPort、browserPath、downloadPath 等的 dict；失败返回 None
        """
        data = {
            "action": "startBrowser",
            "isWaitPluginUpdate": 0,
            "isHeadless": is_headless,
            "requestId": str(uuid.uuid4()),
            "isWebDriverReadOnlyMode": is_web_driver_read_only_mode,
            "cookieTypeLoad": 0,
            "cookieTypeSave": cookie_type_save,
            "runMode": "1",
            "isLoadUserPlugin": False,
            "pluginIdType": 1,
            "privacyMode": is_privacy,
            "notPromptForDownload": 1,
        }
        data.update(self.user_info)

        if store_info.isdigit():
            data["browserId"] = store_info
        else:
            data["browserOauth"] = store_info

        if len(str(js_info)) > 2:
            data["injectJsInfo"] = json.dumps(js_info)

        r = self._send_http(data)
        if r is None:
            return None
        if str(r.get("statusCode")) == "0":
            return r
        if str(r.get("statusCode")) == "-10003":
            print(f"登录错误: {json.dumps(r, ensure_ascii=False)}")
            return None
        print(f"打开店铺失败: {json.dumps(r, ensure_ascii=False)}")
        return None

    def close_store(self, browser_oauth: str) -> bool:
        """关闭店铺。"""
        data = {
            "action": "stopBrowser",
            "requestId": str(uuid.uuid4()),
            "duplicate": 0,
            "browserOauth": browser_oauth,
        }
        data.update(self.user_info)

        r = self._send_http(data)
        if r is None:
            return False
        if str(r.get("statusCode")) == "0":
            return True
        if str(r.get("statusCode")) == "-10003":
            print(f"登录错误: {json.dumps(r, ensure_ascii=False)}")
        else:
            print(f"关闭店铺失败: {json.dumps(r, ensure_ascii=False)}")
        return False

    def get_exit(self) -> None:
        """关闭紫鸟客户端。"""
        data = {
            "action": "exit",
            "requestId": str(uuid.uuid4()),
        }
        data.update(self.user_info)
        self._send_http(data)

