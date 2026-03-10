"""会话管理：紫鸟客户端生命周期 + CDP 连接 + 页面事件追踪 + 跨会话状态持久化"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx

from ziniao_webdriver import ZiniaoClient, detect_ziniao_port

if os.name == "nt":
    import msvcrt
else:
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from .iframe import IFrameContext

_logger = logging.getLogger("ziniao-mcp-debug")

_STATE_DIR = Path.home() / ".ziniao"
_STATE_FILE = _STATE_DIR / "sessions.json"

if TYPE_CHECKING:
    import nodriver
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
    console_messages: list[ConsoleMessage] = field(default_factory=list)
    network_requests: list[NetworkRequest] = field(default_factory=list)
    dialog_action: str = "dismiss"
    dialog_text: str = ""
    iframe_context: Optional["IFrameContext"] = None
    _msg_counter: int = 0
    _req_counter: int = 0
    _listened_tab_ids: set = field(default_factory=set)

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
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
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


_INTERNAL_URL_PREFIXES = ("chrome-extension://", "devtools://", "chrome://")


def _is_regular_tab(tab: "Tab") -> bool:
    """判断 tab 是否为普通网页（过滤掉扩展 offscreen、devtools 等内部页面）。"""
    url = getattr(getattr(tab, "target", None), "url", "") or ""
    return not any(url.startswith(p) for p in _INTERNAL_URL_PREFIXES)


def _filter_tabs(tabs: list) -> list:
    """从 browser.tabs 中过滤出普通网页标签。"""
    return [t for t in tabs if _is_regular_tab(t)]


async def _connect_cdp(port: int) -> "Browser":
    """通过 nodriver 连接到已有的 CDP 端口。"""
    import nodriver  # pylint: disable=import-outside-toplevel

    browser = await nodriver.Browser.create(
        host="127.0.0.1",
        port=port,
    )
    return browser


class SessionManager:
    """管理紫鸟客户端生命周期、CDP 连接和页面状态。"""

    def __init__(
        self,
        client: ZiniaoClient,
        stealth_config: Optional["StealthConfig"] = None,
    ):
        from .stealth import StealthConfig  # pylint: disable=import-outside-toplevel

        self.client = client
        self.stealth_config = stealth_config or StealthConfig()
        self._stores: dict[str, StoreSession] = {}
        self._active_store_id: Optional[str] = None
        self._client_started = False

    async def _apply_stealth_to_browser(self, browser: "Browser") -> None:
        """向 Browser 的所有 tab 注入反检测脚本（若启用）。"""
        if not self.stealth_config.enabled:
            return
        from .stealth import apply_stealth  # pylint: disable=import-outside-toplevel
        await apply_stealth(browser, config=self.stealth_config)

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
                          cdp_port: int, browser_oauth: str) -> None:
        """将已打开店铺的 CDP 信息持久化到状态文件。"""
        entry = {
            "store_id": store_id,
            "store_name": store_name,
            "cdp_port": cdp_port,
            "browser_oauth": browser_oauth,
            "opened_at": time.time(),
        }
        _update_state_file(lambda s: s.update({store_id: entry}))

    @staticmethod
    def _remove_store_state(store_id: str) -> None:
        """从状态文件中移除指定店铺记录。"""
        _update_state_file(lambda s: s.pop(store_id, None))

    @staticmethod
    async def get_persisted_stores() -> list[dict[str, Any]]:
        """读取状态文件并验证每个店铺的 CDP 连通性，清理失效记录。"""
        state = _read_state_file()
        if not state:
            return []
        alive: list[dict[str, Any]] = []
        dead_keys: list[str] = []
        for key, info in state.items():
            port = info.get("cdp_port")
            if port and await _is_cdp_alive(port):
                alive.append(info)
            else:
                dead_keys.append(key)
        if dead_keys:
            _update_state_file(lambda s: [s.pop(k, None) for k in dead_keys])
        return alive

    async def _is_client_running(self) -> bool:
        """通过心跳请求判断紫鸟客户端是否在运行。"""
        return await asyncio.to_thread(self.client.heartbeat)

    def _try_switch_to_detected_port(self) -> Optional[int]:
        """检测紫鸟客户端实际运行端口，若与配置不同则自动切换。"""
        detected = detect_ziniao_port()
        if detected and detected != self.client.socket_port:
            _logger.warning(
                "配置端口 %s 无响应，检测到紫鸟客户端运行在端口 %s，自动切换",
                self.client.socket_port, detected,
            )
            self.client.socket_port = detected
            return detected
        return detected

    async def _ensure_client_running(self) -> None:
        try:
            await asyncio.wait_for(self._do_ensure_client(), timeout=35)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"连接紫鸟客户端超时。请确认：\n"
                f"1) 客户端已以 WebDriver 模式启动（需带 --port 参数）\n"
                f"2) HTTP 端口 {self.client.socket_port} 与客户端实际端口一致\n"
                "提示：通过桌面图标启动的客户端不支持 WebDriver 模式，"
                "请使用 start_client 工具或手动添加 "
                "--run_type=web_driver --ipc_type=http 参数启动。"
            ) from None

    async def _do_ensure_client(self) -> None:
        """_ensure_client_running 的实际逻辑，由外层控制超时。"""
        if self._client_started and await self._is_client_running():
            return
        if await self._is_client_running():
            self._client_started = True
            return
        detected = await asyncio.to_thread(self._try_switch_to_detected_port)
        if detected and await self._is_client_running():
            self._client_started = True
            return
        if await asyncio.to_thread(self.client.is_process_running):
            raise RuntimeError(
                "紫鸟客户端正在运行，但未启用 WebDriver 模式（HTTP 端口未开放）。\n"
                "请先关闭客户端，然后使用 start_client 工具重新启动，"
                f"或手动以 --run_type=web_driver --ipc_type=http "
                f"--port={self.client.socket_port} 参数重启。"
            )
        await asyncio.to_thread(self.client.start_browser)
        await asyncio.to_thread(self.client.update_core, 15)
        self._client_started = True

    async def start_client(self) -> str:
        """启动紫鸟客户端，若已在运行则直接返回。"""
        try:
            return await asyncio.wait_for(self._do_start_client(), timeout=90)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"启动紫鸟客户端超时（90 秒）。请确认：\n"
                f"1) 客户端路径正确：{self.client.client_path}\n"
                f"2) HTTP 端口 {self.client.socket_port} 未被其他程序占用\n"
                "3) 客户端可以手动以 WebDriver 模式正常启动"
            ) from None

    async def _do_start_client(self) -> str:
        """start_client 的实际逻辑，由外层控制超时。"""
        port = self.client.socket_port
        if await self._is_client_running():
            return f"紫鸟客户端已在运行 (端口 {port})"
        detected = await asyncio.to_thread(self._try_switch_to_detected_port)
        if detected and await self._is_client_running():
            self._client_started = True
            return (
                f"紫鸟客户端已在运行 (端口 {detected})。"
                f"注意：配置端口为 {port}，已自动切换到实际端口。"
            )
        if await asyncio.to_thread(self.client.is_process_running):
            _logger.info("检测到紫鸟进程但 WebDriver 端口不通，终止旧进程后重启")
            await asyncio.to_thread(self.client.kill_process, True)
        await asyncio.to_thread(self.client.start_browser)
        await asyncio.to_thread(self.client.update_core, 30)
        self._client_started = True
        if not await self._is_client_running():
            return (
                f"紫鸟客户端启动后仍无法连接 (端口 {self.client.socket_port})。"
                f"请检查 ZINIAO_SOCKET_PORT 是否与客户端实际监听端口一致。"
            )
        return f"紫鸟客户端已启动 (端口 {self.client.socket_port})"

    async def stop_client(self) -> None:
        """关闭所有店铺会话并退出紫鸟客户端。"""
        for store_id in list(self._stores):
            await self.close_store(store_id)
        _update_state_file(lambda s: s.clear())
        await asyncio.to_thread(self.client.get_exit)
        self._client_started = False

    async def list_stores(self) -> list[dict]:
        """获取当前账号下的店铺列表。"""
        await self._ensure_client_running()
        return await asyncio.to_thread(self.client.get_browser_list)

    async def _preflight_check(self, store_id: str) -> None:
        """open_store 前置检查。"""
        store_info = await asyncio.to_thread(self.client.get_store_info, store_id)
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
            self.client.open_store, store_id, js_info=inject_js,
        )
        if not result:
            raise RuntimeError(f"打开店铺失败: {store_id}")

        cdp_port = result.get("debuggingPort")
        if not cdp_port:
            raise RuntimeError("未获取到 CDP 调试端口")

        retries = 3
        browser = None
        for attempt in range(retries):
            try:
                browser = await _connect_cdp(cdp_port)
                break
            except Exception as exc:
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(
                        f"无法连接到 CDP 端口 {cdp_port}，请检查店铺是否已正常打开"
                    ) from exc

        await self._apply_stealth_to_browser(browser)
        tabs = _filter_tabs(browser.tabs)

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
        )

        for tab in session.tabs:
            await self._setup_tab_listeners(session, tab)

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
        if store_id in self._stores:
            self._active_store_id = store_id
            return self._stores[store_id]

        state = _read_state_file()
        info = state.get(store_id)
        if info:
            cdp_port = info.get("cdp_port")
            if cdp_port and await _is_cdp_alive(cdp_port):
                try:
                    browser = await _connect_cdp(cdp_port)
                    await self._apply_stealth_to_browser(browser)
                    tabs = _filter_tabs(browser.tabs)

                    session = StoreSession(
                        store_id=store_id,
                        store_name=info.get("store_name", store_id),
                        cdp_port=cdp_port,
                        browser=browser,
                        tabs=tabs,
                        active_tab_index=0,
                        open_result=info,
                    )
                    for tab in session.tabs:
                        await self._setup_tab_listeners(session, tab)

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
        browser_oauth = (
            session.open_result.get("browserOauth") or session.store_id
        )
        await asyncio.to_thread(self.client.close_store, browser_oauth)
        del self._stores[store_id]
        if self._active_store_id == store_id:
            self._active_store_id = next(iter(self._stores), None)
        self._remove_store_state(store_id)

    def get_active_session(self) -> StoreSession:
        """返回当前选中的店铺会话。"""
        if not self._active_store_id or self._active_store_id not in self._stores:
            raise RuntimeError(
                "没有活动的店铺。请先使用 open_store 打开一个店铺。"
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

    def get_open_store_ids(self) -> list[str]:
        """返回当前已打开店铺的 ID 列表。"""
        return list(self._stores.keys())

    async def _setup_tab_listeners(self, store: StoreSession, tab: "Tab") -> None:
        """为 tab 绑定 console/network/dialog 等事件监听。"""
        if not _is_regular_tab(tab):
            return
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab_id = id(tab)
        if tab_id in store._listened_tab_ids:
            return
        store._listened_tab_ids.add(tab_id)

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
            store.network_requests.append(
                NetworkRequest(
                    id=store._req_counter,
                    url=event.request.url,
                    method=event.request.method,
                    resource_type=event.type_.value if event.type_ else "",
                    request_headers=dict(event.request.headers) if event.request.headers else {},
                    timestamp=time.time(),
                )
            )

        def on_response(event: cdp.network.ResponseReceived):
            for req in reversed(store.network_requests):
                if req.url == event.response.url and req.status is None:
                    req.status = event.response.status
                    req.status_text = event.response.status_text
                    req.response_headers = (
                        dict(event.response.headers) if event.response.headers else {}
                    )
                    break

        async def on_dialog(event: cdp.page.JavascriptDialogOpening):
            accept = store.dialog_action == "accept"
            prompt_text = store.dialog_text if store.dialog_text else None
            await tab.send(
                cdp.page.handle_javascript_dialog(
                    accept=accept,
                    prompt_text=prompt_text,
                )
            )

        tab.add_handler(cdp.runtime.ConsoleAPICalled, on_console)
        tab.add_handler(cdp.network.RequestWillBeSent, on_request)
        tab.add_handler(cdp.network.ResponseReceived, on_response)
        tab.add_handler(cdp.page.JavascriptDialogOpening, on_dialog)

    async def cleanup(self) -> None:
        """关闭所有店铺会话。"""
        for store_id in list(self._stores):
            await self.close_store(store_id)
