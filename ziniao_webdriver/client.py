"""
紫鸟 WebDriver 客户端

封装与紫鸟客户端的 HTTP 通信，支持启动客户端、打开/关闭店铺、获取 CDP 调试端口。
CDP 调试端口由 startBrowser 成功后自动开启，在返回的 debuggingPort 中。
"""

import json
import logging
import os
import platform
import re
import subprocess
import time
import uuid
from typing import Literal, Optional

import requests

_logger = logging.getLogger("ziniao-webdriver")

_STATUS_OK = "0"
_STATUS_AUTH_ERROR = "-10003"
_DEFAULT_PORT = 16851


def detect_ziniao_port() -> Optional[int]:
    """从运行中的紫鸟进程命令行参数中检测 HTTP 通信端口。

    扫描所有 ziniao / SuperBrowser 进程，提取 ``--port=XXXXX`` 参数。
    找不到时返回 None。
    """
    system = platform.system()
    try:
        if system == "Windows":
            output = subprocess.check_output(
                ["wmic", "process", "where",
                 "name like '%ziniao%' or name like '%SuperBrowser%'",
                 "get", "CommandLine"],
                text=True, timeout=10,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            output = subprocess.check_output(
                ["ps", "aux"], text=True, timeout=10,
            )
    except (subprocess.SubprocessError, FileNotFoundError):
        _logger.debug("detect_ziniao_port: 无法获取进程列表")
        return None

    ports: set[int] = set()
    for line in output.splitlines():
        if system != "Windows" and "ziniao" not in line.lower() and "superbrowser" not in line.lower():
            continue
        m = re.search(r"--port=(\d+)", line)
        if m:
            ports.add(int(m.group(1)))

    if len(ports) == 1:
        port = ports.pop()
        _logger.info("自动检测到紫鸟端口: %s", port)
        return port
    if len(ports) > 1:
        _logger.warning("检测到多个紫鸟端口: %s，无法自动选择", ports)
    return None


class ZiniaoClient:
    """紫鸟 WebDriver 客户端，封装与紫鸟客户端的 HTTP 通信及浏览器操作。"""

    _PROCESS_NAMES: dict[str, dict[str, str]] = {
        "v5": {"windows": "SuperBrowser.exe", "mac": "SuperBrowser", "linux": "SuperBrowser"},
        "v6": {"windows": "ziniao.exe", "mac": "ziniao", "linux": "ziniaobrowser"},
    }

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

        _logger.info("ZiniaoClient init: version=%s, port=%s, path=%s",
                      version, socket_port, client_path)

    @property
    def _process_name(self) -> str:
        """当前版本 + 平台对应的进程名。"""
        names = self._PROCESS_NAMES.get(self.version, self._PROCESS_NAMES["v6"])
        if self._is_windows:
            return names["windows"]
        if self._is_mac:
            return names["mac"]
        return names["linux"]

    # ------------------------------------------------------------------
    # HTTP 通信 & 响应解析
    # ------------------------------------------------------------------

    def _send_http(self, data: dict, timeout: int = 120) -> Optional[dict]:
        """向紫鸟客户端发送 HTTP 请求。"""
        try:
            url = f"http://127.0.0.1:{self.socket_port}"
            response = requests.post(
                url, json.dumps(data).encode("utf-8"), timeout=timeout
            )
            return json.loads(response.text)
        except requests.exceptions.ConnectionError:
            _logger.warning(
                "无法连接紫鸟客户端 (127.0.0.1:%s)。"
                "请确认：1) 客户端已启动；"
                "2) ZINIAO_SOCKET_PORT (%s) 与客户端实际监听端口一致。"
                "可在客户端设置或任务管理器中确认实际端口。",
                self.socket_port, self.socket_port,
            )
            return None
        except Exception as err:
            _logger.warning("HTTP 请求失败 (port=%s): %s", self.socket_port, err)
            return None

    @staticmethod
    def _get_status(response: Optional[dict]) -> Optional[str]:
        """从 API 响应中提取并归一化 statusCode（统一转 str，兼容 v5 int / v6 str）。"""
        if response is None:
            return None
        code = response.get("statusCode")
        return str(code) if code is not None else None

    def _request(self, data: dict, action: str, timeout: Optional[int] = None) -> tuple[str, Optional[dict]]:
        """发送请求并解析响应。

        :return: (status, response)
            status — "ok" | "none" | "auth_error" | "unsupported" | "error"
        """
        data.setdefault("requestId", str(uuid.uuid4()))
        data.update(self.user_info)

        r = self._send_http(data, timeout=timeout if timeout is not None else 120)
        status = self._get_status(r)

        if r is None:
            return ("none", None)
        if status is None:
            _logger.warning("响应无 statusCode [%s]: %s", action,
                            json.dumps(r, ensure_ascii=False))
            return ("unsupported", r)
        if status == _STATUS_OK:
            return ("ok", r)
        if status == _STATUS_AUTH_ERROR:
            _logger.warning("登录错误 [%s]: %s", action,
                            json.dumps(r, ensure_ascii=False))
            return ("auth_error", r)
        _logger.warning("%s失败 (statusCode=%s): %s", action, status,
                        json.dumps(r, ensure_ascii=False))
        return ("error", r)

    # ------------------------------------------------------------------
    # 客户端生命周期
    # ------------------------------------------------------------------

    def heartbeat(self) -> bool:
        """检查客户端是否在运行（通过心跳请求）。使用较短超时避免端口不通时长时间阻塞。"""
        data = {"action": "heartbeat", "requestId": str(uuid.uuid4())}
        data.update(self.user_info)
        return self._send_http(data, timeout=10) is not None

    def is_process_running(self) -> bool:
        """检查紫鸟客户端进程是否存在（不论是否为 WebDriver 模式）。"""
        name = self._process_name
        try:
            if self._is_windows:
                ret = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                    capture_output=True, text=True, timeout=10, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return name.lower() in ret.stdout.lower()
            ret = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True, timeout=10, check=False,
            )
            return ret.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def start_browser(self) -> None:
        """以 WebDriver 模式启动紫鸟客户端。"""
        if not (self.client_path and self.client_path.strip()):
            raise FileNotFoundError(
                "未配置紫鸟客户端路径。请设置 ZINIAO_CLIENT_PATH 或 config.yaml 中的 client_path，"
                "或使用 --client-path 指定可执行文件路径（如 D:\\ziniao\\ziniao.exe）。"
            )
        if self._is_windows and not os.path.isfile(self.client_path):
            raise FileNotFoundError(
                f"紫鸟客户端不存在: {self.client_path}。请检查 ZINIAO_CLIENT_PATH 或 --client-path。"
            )
        try:
            args = [
                "--run_type=web_driver",
                "--ipc_type=http",
                f"--port={self.socket_port}",
            ]
            # Cursor/VS Code 宿主会设置 ELECTRON_RUN_AS_NODE=1，
            # 导致 Electron 应用以 Node.js 模式运行而非 GUI 模式。
            # 必须从子进程环境中移除这类干扰变量。
            clean_env = {
                k: v for k, v in os.environ.items()
                if k not in ("ELECTRON_RUN_AS_NODE",)
            }
            popen_kwargs: dict = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "cwd": os.path.dirname(self.client_path) or None,
                "env": clean_env,
            }
            if self._is_windows:
                cmd = [self.client_path, *args]
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            elif self._is_mac:
                cmd = ["open", "-a", self.client_path, "--args", *args]
            elif self._is_linux:
                cmd = [self.client_path, "--no-sandbox", *args]
            else:
                return
            _logger.info("启动客户端: %s (cwd=%s)", cmd, popen_kwargs.get("cwd"))
            subprocess.Popen(cmd, **popen_kwargs)
            time.sleep(8)
        except Exception as e:
            _logger.error("启动客户端失败: %s", e)
            raise

    def kill_process(self, skip_confirm: bool = True) -> bool:
        """
        终止紫鸟客户端已启动的进程。
        :param skip_confirm: 若为 True 则跳过确认（默认 True，适用于 MCP 服务器场景）
        :return: 是否已执行终止
        """
        if not skip_confirm:
            confirmation = input(
                "在启动之前，需要先关闭紫鸟浏览器的主进程，确定要终止进程吗？(y/n): "
            )
            if confirmation.lower() != "y":
                return False

        name = self._process_name
        try:
            if self._is_windows:
                # 使用 subprocess 并吞掉 stderr，避免 taskkill 的 GBK 输出混入 MCP UTF-8 导致乱码
                ret = subprocess.run(
                    ["taskkill", "/f", "/t", "/im", name],
                    capture_output=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            elif self._is_mac or self._is_linux:
                ret = subprocess.run(
                    ["killall", name],
                    capture_output=True,
                    timeout=10,
                )
            else:
                return False
            if ret.returncode != 0:
                _logger.debug("终止进程 %s: 未在运行或已退出 (returncode=%s)", name, ret.returncode)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            _logger.debug("kill_process: %s", e)
        time.sleep(3)
        return True

    def update_core(self, max_retries: int = 90) -> bool:
        """
        下载所有内核，打开店铺前调用（客户端 5.285.7 以上）。
        :param max_retries: 最大重试次数，默认 90 次（约 3 分钟）
        :return: 是否更新成功
        """
        data: dict = {"action": "updateCore"}
        data.update(self.user_info)

        for attempt in range(max_retries):
            data["requestId"] = str(uuid.uuid4())
            result = self._send_http(data, timeout=10)
            if result is None:
                _logger.info("等待客户端启动... (%d/%d)", attempt + 1, max_retries)
                time.sleep(2)
                continue
            status = self._get_status(result)
            if status is None or status == _STATUS_AUTH_ERROR:
                _logger.warning("当前版本不支持此接口，请升级客户端")
                return False
            if status == _STATUS_OK:
                _logger.info("更新内核完成")
                return True
            _logger.info("等待更新内核 (%d/%d): %s", attempt + 1, max_retries,
                         json.dumps(result))
            time.sleep(2)

        _logger.warning("更新内核超时，已重试 %d 次", max_retries)
        return False

    # ------------------------------------------------------------------
    # 店铺操作
    # ------------------------------------------------------------------

    def get_browser_list(self, timeout: int = 15) -> list[dict]:
        """获取店铺列表。timeout 过短时若客户端启动慢可能返回空，默认 15 秒避免长时间阻塞。"""
        status, r = self._request(
            {"action": "getBrowserList"}, "获取店铺列表", timeout=timeout
        )
        if status == "ok" and r is not None:
            return r.get("browserList") or []
        return []

    def get_store_info(self, store_id: str, timeout: int = 15) -> Optional[dict]:
        """从店铺列表中查找指定店铺，返回其详细信息（含 isExpired 等）。

        匹配规则：store_id 与 browserId 或 browserOauth 任一匹配即命中。
        :return: 匹配到的店铺 dict，未找到返回 None
        """
        for s in self.get_browser_list(timeout=timeout):
            if store_id in (str(s.get("browserId", "")), s.get("browserOauth", "")):
                return s
        return None

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
        data: dict = {
            "action": "startBrowser",
            "isWaitPluginUpdate": 0,
            "isHeadless": is_headless,
            "isWebDriverReadOnlyMode": is_web_driver_read_only_mode,
            "cookieTypeLoad": 0,
            "cookieTypeSave": cookie_type_save,
            "runMode": "1",
            "isLoadUserPlugin": False,
            "pluginIdType": 1,
            "privacyMode": is_privacy,
            "notPromptForDownload": 1,
        }

        if store_info.isdigit():
            data["browserId"] = store_info
        else:
            data["browserOauth"] = store_info

        if len(str(js_info)) > 2:
            data["injectJsInfo"] = json.dumps(js_info)

        status, r = self._request(data, "打开店铺", timeout=60)
        return r if status == "ok" else None

    def close_store(self, browser_oauth: str) -> bool:
        """关闭店铺。"""
        status, _ = self._request(
            {"action": "stopBrowser", "duplicate": 0, "browserOauth": browser_oauth},
            "关闭店铺",
            timeout=15,
        )
        return status == "ok"

    def get_exit(self) -> None:
        """关闭紫鸟客户端。"""
        self._request({"action": "exit"}, "退出客户端", timeout=10)

