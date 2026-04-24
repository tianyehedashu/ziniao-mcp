"""会话管理：紫鸟客户端 / Chrome 浏览器生命周期 + CDP 连接 + 页面事件追踪 + 跨会话状态持久化"""

from __future__ import annotations

import asyncio
import base64
import collections
import json
import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx
from ziniao_webdriver.cdp_tabs import filter_tabs as _filter_tabs
from ziniao_webdriver.cdp_tabs import is_regular_tab as _is_regular_tab

from .recording_context import RecordingBrowserContext

if os.name == "nt":
    import msvcrt
else:
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from ziniao_webdriver import ZiniaoClient

    from .iframe import IFrameContext

_logger = logging.getLogger("ziniao-debug")


def _chrome_connect_name(session_id: str, cdp_port: int) -> str:
    """connect_chrome `name` so session key matches StoreSession.store_id."""
    if session_id == f"chrome-{cdp_port}":
        return ""
    return session_id

_ZINIAO_NOT_CONFIGURED = (
    "紫鸟客户端未配置。如需使用紫鸟店铺功能，请设置环境变量 "
    "ZINIAO_COMPANY / ZINIAO_USERNAME / ZINIAO_CLIENT_PATH，"
    "或在 config.yaml 中配置 ziniao 部分。"
    "当前仅可使用 Chrome 浏览器功能（launch_chrome / connect_chrome）。"
)

_STATE_DIR = Path.home() / ".ziniao"
_STATE_FILE = _STATE_DIR / "sessions.json"
_DEFAULT_CHROME_USER_DATA_DIR = _STATE_DIR / "chrome-profile"

_MAX_CONSOLE_MESSAGES = 1000
_MAX_NETWORK_REQUESTS = 1000
# 单条请求在内存 / HAR 中保留的正文上限（UTF-8 字节近似按字符截断）
_MAX_NETWORK_POST_STORE = 1_048_576
_MAX_NETWORK_RESPONSE_STORE = 5_242_880

if TYPE_CHECKING:
    from nodriver import Browser, Tab

    from .stealth import StealthConfig


@dataclass
class ConsoleMessage:
    """控制台单条消息记录。"""

    id: int
    level: str
    text: str
    timestamp: float


@dataclass
class NetworkRequest:
    """网络请求/响应记录。"""

    id: int
    url: str
    method: str
    resource_type: str = ""
    status: Optional[int] = None
    status_text: Optional[str] = None
    request_headers: dict = field(default_factory=dict)
    response_headers: dict = field(default_factory=dict)
    timestamp: float = 0.0
    finished_timestamp: float = 0.0
    encoded_data_length: int = 0
    cdp_request_id: str = ""
    post_data: str = ""
    response_body: str = ""


@dataclass
class RouteEntry:
    """请求拦截路由规则。"""

    url_pattern: str
    abort: bool = False
    response_status: int = 200
    response_body: str = ""
    response_content_type: str = "text/plain"
    response_headers: dict = field(default_factory=dict)


@dataclass
class StoreSession:
    """单个店铺的 CDP 会话（browser/tabs 及控制台、网络追踪）。"""

    store_id: str
    store_name: str
    cdp_port: int
    browser: "Browser"
    tabs: list["Tab"] = field(default_factory=list)
    active_tab_index: int = 0
    launcher_page: str = ""
    open_result: dict = field(default_factory=dict)
    console_messages: collections.deque[ConsoleMessage] = field(
        default_factory=lambda: collections.deque(maxlen=_MAX_CONSOLE_MESSAGES)
    )
    network_requests: collections.deque[NetworkRequest] = field(
        default_factory=lambda: collections.deque(maxlen=_MAX_NETWORK_REQUESTS)
    )
    dialog_action: str = "dismiss"
    dialog_text: str = ""
    iframe_context: Optional["IFrameContext"] = None
    recording: bool = False
    recording_start_url: str = ""
    recording_engine: str = "legacy"  # legacy | dom2
    recording_ring_buffer: Any = None
    recording_seq: int = 0
    recording_binding_name: str = ""
    recording_dom2_handlers: list = field(default_factory=list)
    recording_dom2_frame_handlers: list = field(default_factory=list)
    recording_script_entries: list = field(default_factory=list)
    recording_poll_task: Any = None
    recording_scope: str = "active"
    recording_max_tabs: int = 20
    recording_monotonic_t0: float = 0.0
    recording_attached_targets: set = field(default_factory=set)
    recording_dropped_events: int = 0
    _msg_counter: int = 0
    _req_counter: int = 0
    _listened_tab_ids: set = field(default_factory=set)
    _fetch_tab_ids: set = field(default_factory=set)
    backend_type: str = "ziniao"
    chrome_process: Any = None
    routes: list[RouteEntry] = field(default_factory=list)
    fetch_enabled: bool = False
    har_recording: bool = False
    har_start_time: float = 0.0
    # 基于 profile 的稳定指纹 seed（见 derive_profile_fingerprint）：
    # 紫鸟店铺用 store_id，本机 Chrome 用规范化 user_data_dir 或 port 兜底。
    # 会话级缓存，供 setup_tab_listeners 对新 tab 注入时复用。
    profile_seed: str | None = None

    @property
    def pages(self) -> list["Tab"]:
        """tabs 的别名，兼容外部对 .pages 的访问。"""
        return self.tabs


class _StoreAlreadyRunning(Exception):
    """内部信号：店铺已在其他进程中运行，应改用 connect 复用。"""

    def __init__(self, store_id: str, cdp_port: int):
        self.store_id = store_id
        self.cdp_port = cdp_port
        super().__init__(f"store {store_id} already running on CDP port {cdp_port}")


_LOCK_FILE = _STATE_FILE.with_suffix(".lock")


def _acquire_lock():
    """获取跨进程文件锁，返回锁文件描述符。调用方负责用 _release_lock 释放。"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_RDWR)
    if os.name == "nt":
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    elif fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_lock(fd: int) -> None:
    """释放文件锁并关闭描述符。"""
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_state_locked() -> dict[str, Any]:
    """在已持有锁的前提下读取状态文件（不加锁）。"""
    if not _STATE_FILE.exists():
        return {}
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        _logger.warning("状态文件读取失败，返回空字典")
        return {}


def _write_state_locked(data: dict[str, Any]) -> None:
    """在已持有锁的前提下全量覆盖写入状态文件（不加锁）。"""
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        _logger.warning("状态文件写入失败")


def _read_state_file() -> dict[str, Any]:
    """带锁读取状态文件。"""
    try:
        fd = _acquire_lock()
        try:
            return _read_state_locked()
        finally:
            _release_lock(fd)
    except OSError:
        _logger.warning("无法获取文件锁，直接读取")
        return _read_state_locked()


def _update_state_file(updater) -> None:
    """原子 read-modify-write：在同一把锁内读取、修改、写回状态文件。

    updater: Callable[[dict], None]，就地修改传入的 dict。
    """
    try:
        fd = _acquire_lock()
        try:
            state = _read_state_locked()
            updater(state)
            _write_state_locked(state)
        finally:
            _release_lock(fd)
    except OSError:
        _logger.warning("无法获取文件锁，直接执行更新")
        state = _read_state_locked()
        updater(state)
        _write_state_locked(state)


async def _is_cdp_alive(port: int, timeout: float = 2.0) -> bool:
    """通过 HTTP GET /json/version 检查 CDP 端口是否存活。"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://127.0.0.1:{port}/json/version", timeout=timeout
            )
            return resp.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _ziniao_profile_seed(store_id: str) -> str:
    """紫鸟店铺的稳定指纹 seed：同一 store_id 跨重启稳定。"""
    return f"ziniao:{store_id}"


def _chrome_profile_seed(user_data_dir: str | None, cdp_port: int) -> str:
    """本机 Chrome 的稳定指纹 seed。

    优先使用规范化绝对路径的 user_data_dir（跨重启、跨端口稳定）；
    缺失时退化为 ``chrome:port:<port>``（同一端口稳定，不同端口互不同）。
    """
    if user_data_dir:
        norm = os.path.normcase(os.path.normpath(os.path.abspath(user_data_dir)))
        return f"chrome:ud:{norm}"
    return f"chrome:port:{cdp_port}"


async def _cdp_port_from_profile(user_data_dir: str) -> int | None:
    """读取该 user-data-dir 下 Chrome 写入的 DevToolsActivePort，并确认 CDP 可用。

    仅信任 profile 目录内的端口，避免误连其他 Chrome 实例。
    """
    debug_port_file = Path(user_data_dir) / "DevToolsActivePort"
    if not debug_port_file.is_file():
        return None
    try:
        raw = debug_port_file.read_text(encoding="utf-8", errors="replace").strip()
        port = int(raw.splitlines()[0].strip())
    except (ValueError, OSError, IndexError):
        return None
    if port <= 0 or port > 65535:
        return None
    if await _is_cdp_alive(port):
        return port
    return None


async def _wait_cdp_ready(port: int, timeout_sec: float = 30.0, interval: float = 2.0) -> bool:
    """轮询直到 CDP 端口可用或超时。返回是否就绪。"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if await _is_cdp_alive(port, timeout=min(2.0, interval)):
            return True
        await asyncio.sleep(interval)
    return False


def _format_cdp_connection_error(port: int, exc: Exception) -> str:
    """生成 CDP 连接失败时的友好说明（含 WinError 1225 等）。"""
    msg = (
        f"无法连接到 CDP 端口 {port}。"
        "请按以下顺序检查："
        " 1) 在紫鸟客户端内先手动打开该店铺，确认浏览器窗口已出现；"
        " 2) 在紫鸟设置中确认已开启「远程调试」或「CDP」，并确认端口为 " + str(port) + "；"
        " 3) 本机防火墙/安全软件是否拦截了 127.0.0.1:" + str(port) + "。"
    )
    err = str(exc).strip()
    if "1225" in err or "拒绝" in err or "refused" in err.lower():
        msg += " （当前错误通常表示端口未监听或被拒绝连接。）"
    return msg


async def _connect_cdp(port: int, timeout: float = 30.0) -> "Browser":
    """通过 nodriver 连接到已有的 CDP 端口。"""
    import nodriver  # pylint: disable=import-outside-toplevel

    try:
        browser = await asyncio.wait_for(
            nodriver.Browser.create(host="127.0.0.1", port=port),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"CDP 连接超时（{timeout:.0f}s）。端口 {port} 的 Chrome 可能标签页过多，"
            "请关闭部分标签页后重试。"
        ) from None
    return browser


def _chrome_from_registry() -> str | None:
    """Try to read Chrome install path from Windows registry."""
    if os.name != "nt":
        return None
    try:
        import winreg  # pylint: disable=import-outside-toplevel
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            ):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.isfile(val):
                            return str(val)
                except OSError:
                    continue
    except Exception:
        pass
    return None


def _chrome_path_from_env() -> str | None:
    """Read Chrome executable from environment (CHROME_PATH or CHROME_EXECUTABLE_PATH)."""
    for var in ("CHROME_PATH", "CHROME_EXECUTABLE_PATH"):
        val = os.environ.get(var)
        if val and os.path.isfile(val):
            return val
    return None


def _chrome_user_data_from_env() -> str | None:
    """Read Chrome user-data-dir from environment (CHROME_USER_DATA or CHROME_USER_DATA_DIR)."""
    for var in ("CHROME_USER_DATA", "CHROME_USER_DATA_DIR"):
        val = os.environ.get(var)
        if val:
            return val
    return None


def _find_chrome_executable() -> str:
    """自动检测系统中 Chrome / Chromium 可执行文件路径。

    优先级: CHROME_PATH 环境变量 > 注册表 > 常见路径 > PATH 搜索
    """
    env_path = _chrome_path_from_env()
    if env_path:
        return env_path

    if os.name == "nt":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        reg_path = _chrome_from_registry()
        if reg_path:
            candidates.insert(0, reg_path)
    elif os.uname().sysname == "Darwin" if hasattr(os, "uname") else False:
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    raise RuntimeError(
        "未找到 Chrome 浏览器。请设置环境变量 CHROME_PATH 指定路径，"
        "或安装 Google Chrome。"
    )


def _find_free_port() -> int:
    """获取一个空闲的本地 TCP 端口号。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _truncate_network_store(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n...[truncated]"


async def _network_attach_response_body(
    tab: Any,
    store: StoreSession,
    request_id: str,
) -> None:
    """LoadingFinished 后拉取响应正文（需先 Network.enable 且缓冲区足够）。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    try:
        rid = cdp.network.RequestId(request_id)
        result = await tab.send(cdp.network.get_response_body(request_id=rid))
        if not result:
            return
        body, b64 = result[0], result[1]
        if b64:
            raw = base64.b64decode(body)
            text = raw.decode("utf-8", errors="replace")
        else:
            text = body if isinstance(body, str) else str(body)
        text = _truncate_network_store(text, _MAX_NETWORK_RESPONSE_STORE)
        for req in reversed(store.network_requests):
            if req.cdp_request_id == request_id:
                req.response_body = text
                break
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.debug("Network.getResponseBody failed for %s: %s", request_id, exc)


async def _network_attach_request_post_data(
    tab: Any,
    store: StoreSession,
    request_id: str,
) -> None:
    """部分 POST 仅在 RequestWillBeSent 中带 has_post_data，正文需单独拉取。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    try:
        rid = cdp.network.RequestId(request_id)
        data = await tab.send(cdp.network.get_request_post_data(request_id=rid))
        if data is None:
            return
        s = data if isinstance(data, str) else str(data)
        s = _truncate_network_store(s, _MAX_NETWORK_POST_STORE)
        for req in reversed(store.network_requests):
            if req.cdp_request_id == request_id:
                if not req.post_data:
                    req.post_data = s
                break
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.debug("Network.getRequestPostData failed for %s: %s", request_id, exc)


class SessionManager:
    """管理紫鸟客户端 / Chrome 浏览器生命周期、CDP 连接和页面状态。"""

    def __init__(
        self,
        client: Optional["ZiniaoClient"] = None,
        stealth_config: Optional["StealthConfig"] = None,
        chrome_config: Optional[dict[str, Any]] = None,
    ):
        from .stealth import StealthConfig  # pylint: disable=import-outside-toplevel

        self.client = client
        self.stealth_config = stealth_config or StealthConfig()
        self._chrome_config = chrome_config or {}
        self._stores: dict[str, StoreSession] = {}
        self._active_store_id: Optional[str] = None
        self._client_started = False

    def _require_ziniao_client(self) -> "ZiniaoClient":
        """获取紫鸟客户端实例，未配置时抛出友好错误。"""
        if self.client is None:
            raise RuntimeError(_ZINIAO_NOT_CONFIGURED)
        return self.client

    async def _apply_stealth_to_browser(
        self,
        browser: "Browser",
        *,
        evaluate_existing_documents: bool = True,
        webgl_vendor: bool | None = None,
        profile_seed: Any = None,
    ) -> None:
        """向 Browser 的 tab 注入反检测脚本（若启用）。

        *evaluate_existing_documents=False* 时仅注册 addScriptToEvaluateOnNewDocument，
        不对每个已有页面 evaluate（tab 很多时更快）；调用方应对当前操作页再补一次 evaluate。
        *webgl_vendor* 显式覆盖 ``StealthConfig.webgl_vendor``；Chrome launch/connect
        场景建议传 ``True`` 抹平真实 GPU，紫鸟场景保持默认由客户端处理。
        *profile_seed* 非空字符串时启用稳定指纹派生（见 ``derive_profile_fingerprint``），
        会话级缓存在 ``StoreSession.profile_seed``；为 ``None`` 则 sentinel 走默认路径。
        """
        if not self.stealth_config.enabled:
            return
        from .stealth import _SEED_UNSET, apply_stealth  # pylint: disable=import-outside-toplevel
        await apply_stealth(
            browser,
            config=self.stealth_config,
            evaluate_existing_documents=evaluate_existing_documents,
            webgl_vendor=webgl_vendor,
            profile_seed=profile_seed if profile_seed is not None else _SEED_UNSET,
        )

    async def _evaluate_stealth_on_tab(
        self, tab: "Tab", *, profile_seed: str | None = None,
    ) -> None:
        """对单个 tab 的当前文档执行 stealth（与 apply_stealth 的 evaluate 段一致）。"""
        if not self.stealth_config.enabled or not self.stealth_config.js_patches:
            return
        from .stealth import (  # pylint: disable=import-outside-toplevel
            _SEED_UNSET,
            evaluate_stealth_existing_document,
        )
        await evaluate_stealth_existing_document(
            tab,
            config=self.stealth_config,
            profile_seed=profile_seed if profile_seed is not None else _SEED_UNSET,
        )

    async def _sync_viewport_to_window(self, store: StoreSession) -> None:
        """将 CDP 视口同步为当前窗口内容区尺寸，避免连接后出现右侧/底部大片空白。"""
        if not store.tabs:
            return
        tab = store.tabs[store.active_tab_index] if store.active_tab_index < len(store.tabs) else store.tabs[0]
        try:
            size = await tab.evaluate(
                "({ width: window.innerWidth, height: window.innerHeight })",
                return_by_value=True,
            )
            if not size or not isinstance(size, dict):
                return
            width = int(size.get("width", 0))
            height = int(size.get("height", 0))
            if width <= 0 or height <= 0:
                return
            from nodriver import cdp  # pylint: disable=import-outside-toplevel
            await tab.send(
                cdp.emulation.set_device_metrics_override(
                    width=width,
                    height=height,
                    device_scale_factor=1,
                    mobile=False,
                )
            )
            _logger.debug("视口已同步为窗口尺寸: %dx%d", width, height)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.debug("同步视口到窗口失败（可忽略）: %s", exc)

    def _save_store_state(self, store_id: str, store_name: str,
                          cdp_port: int, browser_oauth: str,
                          backend_type: str = "ziniao") -> None:
        """将已打开会话的 CDP 信息持久化到状态文件。"""
        entry = {
            "store_id": store_id,
            "store_name": store_name,
            "cdp_port": cdp_port,
            "browser_oauth": browser_oauth,
            "backend_type": backend_type,
            "opened_at": time.time(),
        }
        _update_state_file(lambda s: s.update({store_id: entry}))

    @staticmethod
    def _remove_store_state(store_id: str) -> None:
        """从状态文件中移除指定店铺记录。"""
        _update_state_file(lambda s: s.pop(store_id, None))

    def invalidate_session(self, store_id: str) -> None:
        """移除已不可用的会话：停 browser、清内存缓存、清状态文件。

        用于 CDP/WebSocket 断开后让下一次 connect_store / open_store 走重建路径，
        避免在 ``_stores`` 中留下幽灵会话导致后续调用持续抛 WebSocket 关闭异常。
        同步方法：不做网络探活，仅做本地清理，供异常恢复路径安全调用。
        """
        sess = self._stores.pop(store_id, None)
        if sess is not None:
            try:
                sess.browser.stop()
            except Exception:  # noqa: BLE001  # browser 已断时 stop 必然抛，忽略
                pass
        if self._active_store_id == store_id:
            self._active_store_id = next(iter(self._stores), None)
        self._remove_store_state(store_id)

    async def reap_dead_sessions(self, probe_timeout: float = 1.0) -> list[str]:
        """并行探活所有内存缓存会话，对已不可达的调用 ``invalidate_session``。

        供 daemon 的 idle watchdog 每轮顺带调用：把"幽灵会话"的暴露点从
        "下次用户调用时"提前到"后台定期清理时"，让 ``list_all_sessions`` /
        ``active_store_count`` 等只读视图始终反映真实状态。

        Args:
            probe_timeout: 单次 /json/version 探测超时（秒）。不要过大，
                否则一个卡住的会话会拖慢整轮清理。

        Returns:
            本次被清理掉的 store_id 列表。
        """
        if not self._stores:
            return []
        items = [(sid, s.cdp_port) for sid, s in self._stores.items()]
        results = await asyncio.gather(
            *(_is_cdp_alive(port, timeout=probe_timeout) for _, port in items),
            return_exceptions=True,
        )
        dead: list[str] = []
        for (sid, _port), ok in zip(items, results):
            # 探测异常与 False 同等处理：保守视为不可用，避免假活导致幽灵累积。
            if ok is not True:
                dead.append(sid)
        for sid in dead:
            _logger.info("watchdog 清理幽灵会话 %s（CDP 已不可达）", sid)
            try:
                self.invalidate_session(sid)
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("invalidate_session(%s) 失败", sid, exc_info=True)
        return dead

    @staticmethod
    async def get_persisted_stores(
        backend_type: Optional[str] = "ziniao",
    ) -> list[dict[str, Any]]:
        """读取状态文件并验证每个会话的 CDP 连通性，清理失效记录。

        Args:
            backend_type: 按后端类型过滤。None 返回全部，"ziniao" 仅紫鸟，"chrome" 仅 Chrome。
        """
        state = _read_state_file()
        if not state:
            return []
        alive: list[dict[str, Any]] = []
        dead_keys: list[str] = []
        for key, info in state.items():
            if backend_type and info.get("backend_type", "ziniao") != backend_type:
                continue
            port = info.get("cdp_port")
            if port and await _is_cdp_alive(port):
                alive.append(info)
            else:
                dead_keys.append(key)
        if dead_keys:
            def _remove_dead(s: dict) -> None:
                for k in dead_keys:
                    s.pop(k, None)
            _update_state_file(_remove_dead)
        return alive

    async def _is_client_running(self) -> bool:
        """通过心跳请求判断紫鸟客户端是否在运行。"""
        client = self._require_ziniao_client()
        return await asyncio.to_thread(client.heartbeat)

    def _try_switch_to_detected_port(self) -> Optional[int]:
        """检测紫鸟客户端实际运行端口，若与配置不同则自动切换。"""
        from ziniao_webdriver import detect_ziniao_port  # pylint: disable=import-outside-toplevel

        client = self._require_ziniao_client()
        detected = detect_ziniao_port()
        if detected and detected != client.socket_port:
            _logger.warning(
                "配置端口 %s 无响应，检测到紫鸟客户端运行在端口 %s，自动切换",
                client.socket_port, detected,
            )
            client.socket_port = detected
            return detected
        return detected

    async def _ensure_client_running(self) -> None:
        client = self._require_ziniao_client()
        try:
            await asyncio.wait_for(self._do_ensure_client(), timeout=35)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"连接紫鸟客户端超时。请确认：\n"
                f"1) 客户端已以 WebDriver 模式启动（需带 --port 参数）\n"
                f"2) HTTP 端口 {client.socket_port} 与客户端实际端口一致\n"
                "提示：通过桌面图标启动的客户端不支持 WebDriver 模式，"
                "请使用 MCP 的 start_client 工具、命令行 "
                "`ziniao store start-client`，或手动添加 "
                "--run_type=web_driver --ipc_type=http 参数启动。"
            ) from None

    async def _do_ensure_client(self) -> None:
        """_ensure_client_running 的实际逻辑，由外层控制超时。"""
        client = self._require_ziniao_client()
        if self._client_started and await self._is_client_running():
            return
        if await self._is_client_running():
            self._client_started = True
            return
        detected = await asyncio.to_thread(self._try_switch_to_detected_port)
        if detected and await self._is_client_running():
            self._client_started = True
            return
        if await asyncio.to_thread(client.is_process_running):
            raise RuntimeError(
                "紫鸟客户端正在运行，但未启用 WebDriver 模式（HTTP 端口未开放）。\n"
                "请先关闭客户端，然后使用 MCP 的 start_client 工具或 "
                "命令行 `ziniao store start-client` 重新启动，"
                f"或手动以 --run_type=web_driver --ipc_type=http "
                f"--port={client.socket_port} 参数重启。"
            )
        await asyncio.to_thread(client.start_browser)
        await asyncio.to_thread(client.update_core, 15)
        self._client_started = True

    async def start_client(self) -> str:
        """启动紫鸟客户端，若已在运行则直接返回。"""
        client = self._require_ziniao_client()
        try:
            return await asyncio.wait_for(self._do_start_client(), timeout=90)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"启动紫鸟客户端超时（90 秒）。请确认：\n"
                f"1) 客户端路径正确：{client.client_path}\n"
                f"2) HTTP 端口 {client.socket_port} 未被其他程序占用\n"
                "3) 客户端可以手动以 WebDriver 模式正常启动"
            ) from None

    async def _do_start_client(self) -> str:
        """start_client 的实际逻辑，由外层控制超时。"""
        client = self._require_ziniao_client()
        port = client.socket_port
        if await self._is_client_running():
            return f"紫鸟客户端已在运行 (端口 {port})"
        detected = await asyncio.to_thread(self._try_switch_to_detected_port)
        if detected and await self._is_client_running():
            self._client_started = True
            return (
                f"紫鸟客户端已在运行 (端口 {detected})。"
                f"注意：配置端口为 {port}，已自动切换到实际端口。"
            )
        if await asyncio.to_thread(client.is_process_running):
            _logger.info("检测到紫鸟进程但 WebDriver 端口不通，终止旧进程后重启")
            await asyncio.to_thread(client.kill_process, True)
        await asyncio.to_thread(client.start_browser)
        await asyncio.to_thread(client.update_core, 30)
        self._client_started = True
        if not await self._is_client_running():
            return (
                f"紫鸟客户端启动后仍无法连接 (端口 {client.socket_port})。"
                f"请检查 ZINIAO_SOCKET_PORT 是否与客户端实际监听端口一致。"
            )
        return f"紫鸟客户端已启动 (端口 {client.socket_port})"

    async def stop_client(self) -> None:
        """关闭所有紫鸟店铺会话并退出紫鸟客户端。Chrome 会话不受影响。"""
        client = self._require_ziniao_client()
        ziniao_ids = [
            sid for sid, s in self._stores.items()
            if s.backend_type == "ziniao"
        ]
        for store_id in ziniao_ids:
            await self.close_store(store_id)
        def _clear_ziniao(state: dict) -> None:
            for k in list(state):
                if state.get(k, {}).get("backend_type", "ziniao") == "ziniao":
                    del state[k]
        _update_state_file(_clear_ziniao)
        await asyncio.to_thread(client.get_exit)
        self._client_started = False

    async def list_stores(self) -> list[dict]:
        """获取当前账号下的店铺列表。"""
        client = self._require_ziniao_client()
        await self._ensure_client_running()
        return await asyncio.to_thread(client.get_browser_list)

    async def _preflight_check(self, store_id: str) -> None:
        """open_store 前置检查。"""
        client = self._require_ziniao_client()
        store_info = await asyncio.to_thread(client.get_store_info, store_id)
        if store_info is None:
            raise RuntimeError(
                f"店铺 {store_id} 不存在，请通过 list_stores 确认正确的店铺 ID"
            )
        if store_info.get("isExpired"):
            name = store_info.get("browserName", store_id)
            raise RuntimeError(
                f"店铺 {name} ({store_id}) 的代理 IP 已过期，无法打开。"
                "请先在紫鸟客户端中更新代理 IP。"
            )

        state = _read_state_file()
        info = state.get(store_id)
        if info:
            cdp_port = info.get("cdp_port")
            if cdp_port and await _is_cdp_alive(cdp_port):
                _logger.info(
                    "店铺 %s 已在运行 (CDP port=%s)，将通过 connect 复用",
                    store_id, cdp_port,
                )
                raise _StoreAlreadyRunning(store_id, cdp_port)

    async def open_store(self, store_id: str) -> StoreSession:
        """打开指定店铺并建立 CDP 连接与页面监听。"""
        client = self._require_ziniao_client()
        if store_id in self._stores:
            self._active_store_id = store_id
            return self._stores[store_id]

        await self._ensure_client_running()

        try:
            await self._preflight_check(store_id)
        except _StoreAlreadyRunning:
            return await self.connect_store(store_id)

        inject_js = ""
        if self.stealth_config.enabled and self.stealth_config.js_patches:
            from .stealth.js_patches import STEALTH_JS_MINIMAL  # pylint: disable=import-outside-toplevel
            inject_js = STEALTH_JS_MINIMAL

        result = await asyncio.to_thread(
            client.open_store, store_id, js_info=inject_js,
        )
        if not result:
            raise RuntimeError(f"打开店铺失败: {store_id}")

        cdp_port = result.get("debuggingPort")
        if not cdp_port:
            raise RuntimeError("未获取到 CDP 调试端口")

        if not await _wait_cdp_ready(cdp_port, timeout_sec=30.0, interval=2.0):
            raise RuntimeError(
                _format_cdp_connection_error(
                    cdp_port,
                    OSError(f"CDP 端口 {cdp_port} 在 30 秒内未就绪"),
                )
            )

        try:
            browser = await _connect_cdp(cdp_port)
        except Exception as exc:
            raise RuntimeError(_format_cdp_connection_error(cdp_port, exc)) from exc

        profile_seed = _ziniao_profile_seed(store_id)
        await self._apply_stealth_to_browser(browser, profile_seed=profile_seed)
        tabs = _filter_tabs(browser.tabs)

        if not tabs:
            try:
                await browser.get("about:blank", new_tab=True)
                await asyncio.sleep(0.5)
                tabs = _filter_tabs(browser.tabs)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("自动创建新标签页失败（tabs 为空）: %s", exc)

        store_name = result.get("browserName", store_id)
        launcher_page = result.get("launcherPage", "")
        session = StoreSession(
            store_id=store_id,
            store_name=store_name,
            cdp_port=cdp_port,
            browser=browser,
            tabs=tabs,
            active_tab_index=0,
            launcher_page=launcher_page,
            open_result=result,
            profile_seed=profile_seed,
        )

        for tab in session.tabs:
            await self.setup_tab_listeners(session, tab)

        if launcher_page:
            try:
                active_tab = session.tabs[0] if session.tabs else None
                if active_tab:
                    await active_tab.get(launcher_page)
                    _logger.info("已导航到店铺启动页: %s", launcher_page)
            except Exception as exc:
                _logger.warning("导航到启动页失败 (%s): %s", launcher_page, exc)

        self._stores[store_id] = session
        self._active_store_id = store_id

        await self._sync_viewport_to_window(session)

        browser_oauth = result.get("browserOauth", store_id)
        self._save_store_state(store_id, store_name, cdp_port, browser_oauth)

        return session

    async def connect_store(self, store_id: str) -> StoreSession:
        """从状态文件恢复 CDP 连接。连接失败时自动 fallback 到 open_store。"""
        cached = self._stores.get(store_id)
        if cached is not None:
            # 命中内存缓存前必须做一次轻量探活：用户/紫鸟空闲回收/进程异常都会
            # 让底层 CDP WebSocket 断开而缓存对象仍在，直接返回会让后续 tab.send
            # 持续抛 ConnectionClosed，必须重启 daemon 才能恢复。
            if await _is_cdp_alive(cached.cdp_port, timeout=1.0):
                self._active_store_id = store_id
                return cached
            _logger.warning(
                "缓存会话 %s 的 CDP 端口 %s 已不可达，清理并走重建路径",
                store_id, cached.cdp_port,
            )
            self.invalidate_session(store_id)

        state = _read_state_file()
        info = state.get(store_id)
        if info:
            cdp_port = info.get("cdp_port")
            if cdp_port and await _is_cdp_alive(cdp_port):
                try:
                    browser = await _connect_cdp(cdp_port)
                    profile_seed = _ziniao_profile_seed(store_id)
                    await self._apply_stealth_to_browser(
                        browser, profile_seed=profile_seed,
                    )
                    tabs = _filter_tabs(browser.tabs)

                    if not tabs:
                        try:
                            await browser.get("about:blank", new_tab=True)
                            await asyncio.sleep(0.5)
                            tabs = _filter_tabs(browser.tabs)
                        except Exception as _exc:  # pylint: disable=broad-exception-caught
                            _logger.warning("自动创建新标签页失败（tabs 为空）: %s", _exc)

                    session = StoreSession(
                        store_id=store_id,
                        store_name=info.get("store_name", store_id),
                        cdp_port=cdp_port,
                        browser=browser,
                        tabs=tabs,
                        active_tab_index=0,
                        open_result=info,
                        profile_seed=profile_seed,
                    )
                    for tab in session.tabs:
                        await self.setup_tab_listeners(session, tab)

                    self._stores[store_id] = session
                    self._active_store_id = store_id
                    await self._sync_viewport_to_window(session)
                    return session
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    _logger.warning("CDP 重连失败 (port=%s)，fallback 到 open_store: %s", cdp_port, exc)

            self._remove_store_state(store_id)

        return await self.open_store(store_id)

    async def close_store(self, store_id: str) -> None:
        session = self._stores.get(store_id)
        if not session:
            return
        try:
            session.browser.stop()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        if session.backend_type == "ziniao" and self.client is not None:
            browser_oauth = (
                session.open_result.get("browserOauth") or session.store_id
            )
            await asyncio.to_thread(self.client.close_store, browser_oauth)
        elif session.backend_type == "chrome" and session.chrome_process:
            try:
                session.chrome_process.terminate()
                session.chrome_process.wait(timeout=5)
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("Chrome 进程终止失败（可忽略）")

        del self._stores[store_id]
        if self._active_store_id == store_id:
            self._active_store_id = next(iter(self._stores), None)
        self._remove_store_state(store_id)

    def has_active_session(self) -> bool:
        """daemon 内存中是否已有可操作的浏览器会话。"""
        return bool(self._active_store_id and self._active_store_id in self._stores)

    def active_store_count(self) -> int:
        """当前 daemon 持有的浏览器会话总数（含 Ziniao 店铺与 Chrome 实例）。

        idle watchdog 用它判断是否可以安全停机：有任何会话存在时，自动停机会
        触发 ``cleanup`` → ``close_store`` → 实际关闭用户的紫鸟店铺 / 强杀
        ``launch_chrome`` 启动的 Chrome 进程，属于不可逆的用户数据风险。
        """
        return len(self._stores)

    async def attach_from_recording_context(self, ctx: RecordingBrowserContext) -> None:
        """按录制保存的会话信息连接浏览器（connect_store / connect_chrome）。"""
        if ctx.backend_type == "chrome":
            if ctx.cdp_port <= 0:
                raise RuntimeError("录制上下文缺少有效的 CDP 端口，无法连接 Chrome。")
            nm = _chrome_connect_name(ctx.session_id, ctx.cdp_port)
            await self.connect_chrome(ctx.cdp_port, name=nm)
        else:
            await self.connect_store(ctx.session_id)

    def get_active_session(self) -> StoreSession:
        """返回当前活跃的浏览器会话。"""
        if not self._active_store_id or self._active_store_id not in self._stores:
            raise RuntimeError(
                "没有活动的浏览器会话。"
                "请先使用 open_store 打开紫鸟店铺，"
                "或使用 launch_chrome / connect_chrome 连接 Chrome 浏览器。"
            )
        return self._stores[self._active_store_id]

    def get_active_tab(self) -> "Tab":
        """返回当前店铺会话中的活动 Tab。"""
        session = self.get_active_session()
        session.tabs = _filter_tabs(session.browser.tabs)
        if not session.tabs:
            raise RuntimeError("没有打开的页面")
        if session.active_tab_index >= len(session.tabs):
            session.active_tab_index = 0
        return session.tabs[session.active_tab_index]

    async def ensure_active_regular_tab(self, initial_url: str = "") -> "Tab":
        """若已有普通网页标签则返回当前活动标签；否则新建一页（about:blank 或 initial_url）。"""
        store = self.get_active_session()
        store.tabs = _filter_tabs(store.browser.tabs)
        if store.tabs:
            if store.active_tab_index >= len(store.tabs):
                store.active_tab_index = 0
            return store.tabs[store.active_tab_index]

        target = (initial_url or "").strip() or "about:blank"
        try:
            new_tab = await store.browser.get(target, new_tab=True)
        except Exception as exc:
            raise RuntimeError(
                "无法打开新页面（无可用普通标签且创建失败）。请检查 CDP 连接与浏览器状态。",
            ) from exc
        await asyncio.sleep(0.5)
        store.tabs = _filter_tabs(store.browser.tabs)
        if not store.tabs:
            raise RuntimeError(
                "无法打开新页面：创建标签后仍无普通网页标签。"
                "请确认浏览器未仅停留在扩展或内部页面。",
            )
        store.iframe_context = None
        try:
            idx = store.tabs.index(new_tab)
        except ValueError:
            idx = len(store.tabs) - 1
        store.active_tab_index = idx
        t = store.tabs[store.active_tab_index]
        await self.setup_tab_listeners(store, t)
        return t

    async def open_replay_tab(self, initial_url: str = "") -> "Tab":
        """为回放专门新建普通网页标签（不重用当前标签）。"""
        store = self.get_active_session()
        target = (initial_url or "").strip() or "about:blank"
        try:
            new_tab = await store.browser.get(target, new_tab=True)
        except Exception as exc:
            raise RuntimeError(
                "回放时无法打开新标签页。请检查 CDP 连接与浏览器状态。",
            ) from exc
        await asyncio.sleep(0.5)
        store.tabs = _filter_tabs(store.browser.tabs)
        if not store.tabs:
            raise RuntimeError(
                "回放时无法打开新标签页：创建后仍无普通网页标签。",
            )
        store.iframe_context = None
        try:
            idx = store.tabs.index(new_tab)
        except ValueError:
            idx = len(store.tabs) - 1
        store.active_tab_index = idx
        t = store.tabs[store.active_tab_index]
        await self.setup_tab_listeners(store, t)
        return t

    def get_open_store_ids(self) -> list[str]:
        """返回当前已打开店铺的 ID 列表。"""
        return list(self._stores.keys())

    @property
    def active_session_id(self) -> Optional[str]:
        """当前活跃会话的 ID，无活跃会话时为 None。"""
        return self._active_store_id

    # ── Chrome 浏览器管理 ──────────────────────────────────────────────

    def _resolve_chrome_defaults(
        self,
        executable_path: str,
        user_data_dir: str,
        cdp_port: int,
        headless: bool,
    ) -> tuple[str, str, int, bool]:
        """Apply fallback chain: caller arg > env var > chrome_config > built-in default."""
        cc = self._chrome_config

        if not executable_path:
            executable_path = _chrome_path_from_env() or ""
        if not executable_path:
            executable_path = cc.get("executable_path") or ""
        if not executable_path:
            executable_path = _find_chrome_executable()

        if not user_data_dir:
            user_data_dir = _chrome_user_data_from_env() or cc.get("user_data_dir") or ""
        if not user_data_dir:
            _DEFAULT_CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            user_data_dir = str(_DEFAULT_CHROME_USER_DATA_DIR)

        if cdp_port <= 0:
            cdp_port = int(cc.get("default_cdp_port") or 0)
        if cdp_port <= 0:
            cdp_port = _find_free_port()

        if not headless:
            headless = bool(cc.get("headless"))

        return executable_path, user_data_dir, cdp_port, headless

    async def _try_connect_existing_chrome(
        self, user_data_dir: str, *, relaxed_probe: bool = True,
    ) -> int | None:
        """查找已占用该 profile 的 Chrome 的 CDP 端口。

        优先 DevToolsActivePort（与目录绑定）。若 ``relaxed_probe`` 为真，再探测常见端口
        （仅在已确认新进程因 profile 冲突退出等场景使用，降低误连概率）。
        """
        port = await _cdp_port_from_profile(user_data_dir)
        if port is not None:
            return port
        if not relaxed_probe:
            return None

        probe_ports: list[int] = []
        cfg_port = int(self._chrome_config.get("default_cdp_port") or 0)
        if cfg_port > 0:
            probe_ports.append(cfg_port)
        probe_ports.extend([9222, 9333, 9515])

        for p in probe_ports:
            if await _is_cdp_alive(p):
                return p

        return None

    async def _finalize_launched_chrome(
        self,
        session_id: str,
        store_display_name: str,
        connected_port: int,
        url: str,
        chrome_process: Any,
        user_data_dir: str | None = None,
    ) -> StoreSession:
        """在已知 CDP 端口就绪后完成 stealth、会话对象构建与导航。

        *user_data_dir* 参与 profile 稳定 seed：同一 user-data-dir 跨重启
        指纹一致；缺失时退化到 port 维度稳定。
        """
        browser = await _connect_cdp(connected_port)
        tabs = _filter_tabs(browser.tabs)

        if not tabs:
            target = url or "about:blank"
            try:
                await browser.get(target, new_tab=True)
                await asyncio.sleep(0.5)
                tabs = _filter_tabs(browser.tabs)
                url = ""
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("自动创建新标签页失败（tabs 为空）: %s", exc)

        # Stealth 必须在「至少已有 tab」之后注入，否则 addScript 不会挂到新开的页面上。
        # 本机 Chrome launch：默认启用 WebGL vendor 伪造，避免真实 GPU 通过 WebGL Report 泄露。
        profile_seed = _chrome_profile_seed(user_data_dir, connected_port)
        await self._apply_stealth_to_browser(
            browser, webgl_vendor=True, profile_seed=profile_seed,
        )

        session = StoreSession(
            store_id=session_id,
            store_name=store_display_name,
            cdp_port=connected_port,
            browser=browser,
            tabs=tabs,
            active_tab_index=0,
            backend_type="chrome",
            chrome_process=chrome_process,
            profile_seed=profile_seed,
        )

        if session.tabs:
            active_tab = session.tabs[session.active_tab_index]
            await self.setup_tab_listeners(session, active_tab)

        self._stores[session_id] = session
        self._active_store_id = session_id

        if url and session.tabs:
            try:
                from nodriver import cdp as _cdp  # pylint: disable=import-outside-toplevel
                active_tab = session.tabs[session.active_tab_index]
                await active_tab.send(_cdp.page.navigate(url=url))
                await active_tab.sleep(0.5)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("导航到目标 URL 失败 (%s): %s", url, exc)

        await self._sync_viewport_to_window(session)

        self._save_store_state(
            session_id, session.store_name, connected_port, session_id,
            backend_type="chrome",
        )

        return session

    async def launch_chrome(
        self,
        name: str = "",
        executable_path: str = "",
        cdp_port: int = 0,
        user_data_dir: str = "",
        headless: bool = False,
        url: str = "",
    ) -> StoreSession:
        """独立启动一个 Chrome 实例并通过 CDP 连接。

        参数优先级: 函数参数 > 环境变量 (CHROME_PATH / CHROME_USER_DATA) > config > 默认值。
        若 profile 已被占用，自动尝试连接已有实例。
        """
        executable_path, user_data_dir, cdp_port, headless = self._resolve_chrome_defaults(
            executable_path, user_data_dir, cdp_port, headless,
        )

        profile_port = await _cdp_port_from_profile(user_data_dir)
        if profile_port is not None:
            pre_sid = name or f"chrome-{profile_port}"
            if pre_sid in self._stores:
                self._active_store_id = pre_sid
                return self._stores[pre_sid]
            _logger.info(
                "检测到该 user_data_dir 已有开启远程调试的 Chrome（端口 %d），直接连接，不启动新进程",
                profile_port,
            )
            return await self._finalize_launched_chrome(
                pre_sid,
                name or f"Chrome ({profile_port})",
                profile_port,
                url,
                None,
                user_data_dir=user_data_dir,
            )

        session_id = name or f"chrome-{cdp_port}"
        if session_id in self._stores:
            self._active_store_id = session_id
            return self._stores[session_id]

        args = [
            executable_path,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if headless:
            args.append("--headless=new")
        if url:
            args.append(url)

        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            args, **popen_kwargs,
        )

        connected_port: int | None = None
        owns_process = True
        for _attempt in range(15):
            if await _is_cdp_alive(cdp_port):
                connected_port = cdp_port
                break
            if proc.poll() is not None:
                if proc.returncode == 0:
                    existing_port: int | None = None
                    for _ in range(6):
                        existing_port = await self._try_connect_existing_chrome(user_data_dir)
                        if existing_port:
                            break
                        await asyncio.sleep(0.35)
                    if existing_port:
                        _logger.info(
                            "Profile 已被占用，已自动连接到已有 Chrome（端口 %d）；"
                            "关闭会话不会结束该 Chrome 进程",
                            existing_port,
                        )
                        connected_port = existing_port
                        owns_process = False
                        session_id = name or f"chrome-{existing_port}"
                        if session_id in self._stores:
                            self._active_store_id = session_id
                            return self._stores[session_id]
                        break
                    raise RuntimeError(
                        "该 user_data_dir 已被其他 Chrome 占用，且未检测到可连接的远程调试端口 "
                        f"（{user_data_dir}）。若占用该 profile 的窗口不是通过 ziniao launch 打开的，"
                        "请关闭后重试；或为本机 Chrome 添加 --remote-debugging-port 后使用 "
                        "`ziniao connect <端口>`；也可设置 CHROME_USER_DATA 使用其他 profile 目录。"
                    )
                raise RuntimeError(
                    f"Chrome 进程已退出 (exit code {proc.returncode})。"
                    f"请检查路径是否正确: {executable_path}"
                )
            await asyncio.sleep(1)
        else:
            proc.terminate()
            raise RuntimeError(
                f"Chrome CDP 端口 {cdp_port} 在 15 秒内未就绪"
            )

        assert connected_port is not None
        return await self._finalize_launched_chrome(
            session_id,
            name or f"Chrome ({connected_port})",
            connected_port,
            url,
            proc if owns_process else None,
            user_data_dir=user_data_dir,
        )

    async def connect_chrome(
        self, cdp_port: int, name: str = "",
    ) -> StoreSession:
        """连接到一个已运行的 Chrome 实例（通过 CDP 端口）。

        与 ``launch_chrome`` / ``open_store`` 一致：按配置注入 stealth（若启用）。
        外部 Chrome 往往已有大量 tab：注册 *addScriptToEvaluateOnNewDocument* 的同时
        对**所有常规 tab** 并行执行 evaluate，使已存在文档也立即生效；并行调度
        由 ``apply_stealth`` 内部保证，避免按序 evaluate 导致的长尾延迟。
        """
        session_id = name or f"chrome-{cdp_port}"
        cached = self._stores.get(session_id)
        if cached is not None:
            if await _is_cdp_alive(cached.cdp_port, timeout=1.0):
                self._active_store_id = session_id
                return cached
            _logger.warning(
                "缓存 Chrome 会话 %s 的 CDP 端口 %s 已不可达，清理并重建",
                session_id, cached.cdp_port,
            )
            self.invalidate_session(session_id)

        if not await _is_cdp_alive(cdp_port):
            raise RuntimeError(
                f"无法连接到 CDP 端口 {cdp_port}。请确认 Chrome 已启动并带有 "
                f"--remote-debugging-port={cdp_port} 参数。"
            )

        browser = await _connect_cdp(cdp_port)
        tabs = _filter_tabs(browser.tabs)

        if not tabs:
            try:
                await browser.get("about:blank", new_tab=True)
                await asyncio.sleep(0.5)
                tabs = _filter_tabs(browser.tabs)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("自动创建新标签页失败（tabs 为空）: %s", exc)

        # 先保证 tab 列表就绪再注册 addScript；否则后续新建的 tab 没有 OnNewDocument 钩子。
        # evaluate_existing_documents=True：并行对所有 tab evaluate（由 apply_stealth 内部 gather）。
        # 外部 Chrome：默认启用 WebGL vendor 伪造，抹平真实 GPU 信息。
        # connect 场景无从获知 user_data_dir，profile_seed 按 port 维度稳定。
        profile_seed = _chrome_profile_seed(None, cdp_port)
        await self._apply_stealth_to_browser(
            browser,
            evaluate_existing_documents=True,
            webgl_vendor=True,
            profile_seed=profile_seed,
        )

        session = StoreSession(
            store_id=session_id,
            store_name=name or f"Chrome ({cdp_port})",
            cdp_port=cdp_port,
            browser=browser,
            tabs=tabs,
            active_tab_index=0,
            backend_type="chrome",
            profile_seed=profile_seed,
        )

        if session.tabs:
            active_tab = session.tabs[session.active_tab_index]
            await self.setup_tab_listeners(session, active_tab)

        self._stores[session_id] = session
        self._active_store_id = session_id

        await self._sync_viewport_to_window(session)

        self._save_store_state(
            session_id, session.store_name, cdp_port, session_id,
            backend_type="chrome",
        )

        return session

    async def close_chrome(self, session_id: str) -> None:
        """关闭 Chrome 会话。"""
        session = self._stores.get(session_id)
        if not session or session.backend_type != "chrome":
            return
        await self.close_store(session_id)

    def list_chrome_sessions(self) -> list[dict]:
        """列出所有 Chrome 类型的活跃会话。"""
        result = []
        for sid, s in self._stores.items():
            if s.backend_type == "chrome":
                result.append({
                    "session_id": sid,
                    "name": s.store_name,
                    "cdp_port": s.cdp_port,
                    "tabs": len(_filter_tabs(s.browser.tabs)),
                    "is_active": sid == self._active_store_id,
                })
        return result

    # ── 统一会话管理 ──────────────────────────────────────────────────

    def list_all_sessions(self) -> list[dict]:
        """列出所有活跃会话（紫鸟 + Chrome）。"""
        result = []
        for sid, s in self._stores.items():
            result.append({
                "session_id": sid,
                "name": s.store_name,
                "type": s.backend_type,
                "cdp_port": s.cdp_port,
                "tabs": len(_filter_tabs(s.browser.tabs)),
                "is_active": sid == self._active_store_id,
            })
        return result

    def switch_session(self, session_id: str) -> StoreSession:
        """切换当前活跃会话。"""
        if session_id not in self._stores:
            available = ", ".join(self._stores.keys()) if self._stores else "无"
            raise RuntimeError(
                f"会话 '{session_id}' 不存在。可用会话: {available}"
            )
        self._active_store_id = session_id
        return self._stores[session_id]

    def get_session_info(self, session_id: str) -> dict:
        """获取指定会话的详细信息。"""
        session = self._stores.get(session_id)
        if not session:
            raise RuntimeError(f"会话 '{session_id}' 不存在")
        tabs_info = []
        for i, tab in enumerate(_filter_tabs(session.browser.tabs)):
            tabs_info.append({
                "index": i,
                "url": getattr(getattr(tab, "target", None), "url", ""),
                "title": getattr(getattr(tab, "target", None), "title", ""),
            })
        return {
            "session_id": session.store_id,
            "name": session.store_name,
            "type": session.backend_type,
            "cdp_port": session.cdp_port,
            "active_tab_index": session.active_tab_index,
            "tabs": tabs_info,
            "is_active": session.store_id == self._active_store_id,
        }

    async def setup_tab_listeners(self, store: StoreSession, tab: "Tab") -> None:
        """为 tab 绑定 console/network/dialog 等事件监听。

        顺带对**首次接入**的 tab 注入 stealth 脚本，确保通过 ``tab new`` 等路径
        创建的新 tab 也被覆盖（否则仅 open_store / launch / connect 时存在的
        tab 有 OnNewDocument 钩子，新 tab 指纹裸奔）。整个 stealth 脚本自带
        ``__stealth_applied__`` 幂等 guard，重复注册/evaluate 安全。
        """
        if not _is_regular_tab(tab):
            return
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab_id = id(tab)
        if tab_id in store._listened_tab_ids:
            return
        store._listened_tab_ids.add(tab_id)

        if self.stealth_config.enabled and self.stealth_config.js_patches:
            from .stealth import build_stealth_js, _resolve_webgl_vendor  # pylint: disable=import-outside-toplevel
            wv = _resolve_webgl_vendor(
                self.stealth_config,
                True if store.backend_type == "chrome" else None,
            )
            # 使用会话级缓存的 profile_seed：open_store / launch_chrome / connect_chrome
            # 已在 StoreSession 上写入；缺失则回落到 StealthConfig.profile_seed。
            seed = store.profile_seed or self.stealth_config.profile_seed
            script = build_stealth_js(webgl_vendor=wv, profile_seed=seed)
            try:
                await tab.send(
                    cdp.page.add_script_to_evaluate_on_new_document(source=script)
                )
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("setup_tab_listeners: addScript 失败（tab 可能已关闭）")
            try:
                await tab.evaluate(script)
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("setup_tab_listeners: evaluate 失败（tab 可能已关闭）")

        try:
            await tab.send(
                cdp.network.enable(
                    max_post_data_size=_MAX_NETWORK_POST_STORE,
                    max_resource_buffer_size=50 * 1024 * 1024,
                )
            )
        except Exception:  # pylint: disable=broad-exception-caught
            await tab.send(cdp.network.enable())
        await tab.send(cdp.page.enable())
        await tab.send(cdp.runtime.enable())

        def on_console(event: cdp.runtime.ConsoleAPICalled):
            store._msg_counter += 1
            text_parts = []
            for arg in event.args:
                if arg.value is not None:
                    text_parts.append(str(arg.value))
                elif arg.description:
                    text_parts.append(arg.description)
                elif arg.unserializable_value:
                    text_parts.append(arg.unserializable_value)
            store.console_messages.append(
                ConsoleMessage(
                    id=store._msg_counter,
                    level=event.type_,
                    text=" ".join(text_parts),
                    timestamp=time.time(),
                )
            )

        def on_request(event: cdp.network.RequestWillBeSent):
            store._req_counter += 1
            rq = event.request
            pd = ""
            if rq and rq.post_data:
                pd = _truncate_network_store(rq.post_data, _MAX_NETWORK_POST_STORE)
            rid = str(event.request_id)
            store.network_requests.append(
                NetworkRequest(
                    id=store._req_counter,
                    url=rq.url if rq else "",
                    method=rq.method if rq else "",
                    resource_type=event.type_.value if event.type_ else "",
                    request_headers=dict(rq.headers) if rq and rq.headers else {},
                    timestamp=time.time(),
                    cdp_request_id=rid,
                    post_data=pd,
                )
            )
            if rq and getattr(rq, "has_post_data", None) and not pd:
                try:
                    asyncio.get_running_loop().create_task(
                        _network_attach_request_post_data(tab, store, rid)
                    )
                except RuntimeError:
                    pass

        def on_response(event: cdp.network.ResponseReceived):
            rid = str(event.request_id)
            for req in reversed(store.network_requests):
                if req.cdp_request_id == rid:
                    req.status = event.response.status
                    req.status_text = event.response.status_text
                    req.response_headers = (
                        dict(event.response.headers) if event.response.headers else {}
                    )
                    break

        def on_loading_finished(event: cdp.network.LoadingFinished):
            rid = str(event.request_id)
            for req in reversed(store.network_requests):
                if req.cdp_request_id == rid:
                    req.finished_timestamp = time.time()
                    req.encoded_data_length = int(event.encoded_data_length) if event.encoded_data_length else 0
                    break
            try:
                asyncio.get_running_loop().create_task(
                    _network_attach_response_body(tab, store, rid)
                )
            except RuntimeError:
                pass

        async def on_dialog(event: cdp.page.JavascriptDialogOpening):
            accept = store.dialog_action == "accept"
            prompt_text = store.dialog_text if store.dialog_text else None
            await tab.send(
                cdp.page.handle_java_script_dialog(
                    accept=accept,
                    prompt_text=prompt_text,
                )
            )

        tab.add_handler(cdp.runtime.ConsoleAPICalled, on_console)
        tab.add_handler(cdp.network.RequestWillBeSent, on_request)
        tab.add_handler(cdp.network.ResponseReceived, on_response)
        tab.add_handler(cdp.network.LoadingFinished, on_loading_finished)
        tab.add_handler(cdp.page.JavascriptDialogOpening, on_dialog)

    async def cleanup(self) -> None:
        """关闭所有店铺会话。"""
        for store_id in list(self._stores):
            await self.close_store(store_id)
