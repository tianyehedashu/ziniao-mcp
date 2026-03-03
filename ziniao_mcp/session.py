"""会话管理：紫鸟客户端生命周期 + CDP 连接 + 页面事件追踪 + 跨会话状态持久化"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx

from ziniao_webdriver import ZiniaoClient

_logger = logging.getLogger("ziniao-mcp-debug")

_STATE_DIR = Path.home() / ".ziniao"
_STATE_FILE = _STATE_DIR / "sessions.json"

if TYPE_CHECKING:
    from playwright.async_api import (  # type: ignore[reportMissingImports]
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )


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
    """单个店铺的 CDP 会话（browser/context/pages 及控制台、网络追踪）。"""

    store_id: str
    store_name: str
    cdp_port: int
    browser: Browser
    context: BrowserContext
    pages: list[Page] = field(default_factory=list)
    active_page_index: int = 0
    open_result: dict = field(default_factory=dict)
    console_messages: list[ConsoleMessage] = field(default_factory=list)
    network_requests: list[NetworkRequest] = field(default_factory=list)
    dialog_action: str = "dismiss"
    dialog_text: str = ""
    _msg_counter: int = 0
    _req_counter: int = 0
    _listened_page_ids: set = field(default_factory=set)


_LOCK_FILE = _STATE_FILE.with_suffix(".lock")


def _acquire_lock():
    """获取跨进程文件锁，返回锁文件描述符。调用方负责用 _release_lock 释放。"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_RDWR)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_lock(fd: int) -> None:
    """释放文件锁并关闭描述符。"""
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
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


class SessionManager:
    """管理紫鸟客户端生命周期、CDP 连接和页面状态。"""

    def __init__(self, client: ZiniaoClient):
        self.client = client
        self._playwright: Optional[Playwright] = None
        self._stores: dict[str, StoreSession] = {}
        self._active_store_id: Optional[str] = None
        self._client_started = False

    async def _ensure_playwright(self) -> "Playwright":
        if not self._playwright:
            from playwright.async_api import async_playwright  # pylint: disable=import-outside-toplevel  # type: ignore[reportMissingImports]
            self._playwright = await async_playwright().start()
        return self._playwright

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
        data = {
            "action": "heartbeat",
            "requestId": str(uuid.uuid4()),
        }
        data.update(self.client.user_info)
        result = await asyncio.to_thread(self.client._send_http, data)  # pylint: disable=protected-access
        return result is not None

    async def _ensure_client_running(self) -> None:
        if self._client_started and await self._is_client_running():
            return
        if await self._is_client_running():
            self._client_started = True
            return
        await asyncio.to_thread(self.client.kill_process, True)
        await asyncio.to_thread(self.client.start_browser)
        await asyncio.to_thread(self.client.update_core)
        self._client_started = True

    async def start_client(self) -> str:
        """启动紫鸟客户端，若已在运行则直接返回。"""
        if await self._is_client_running():
            return "紫鸟客户端已在运行"
        await asyncio.to_thread(self.client.kill_process, True)
        await asyncio.to_thread(self.client.start_browser)
        await asyncio.to_thread(self.client.update_core)
        self._client_started = True
        return "紫鸟客户端已启动"

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

    async def open_store(self, store_id: str) -> StoreSession:
        """打开指定店铺并建立 CDP 连接与页面监听。"""
        if store_id in self._stores:
            self._active_store_id = store_id
            return self._stores[store_id]

        await self._ensure_client_running()
        result = await asyncio.to_thread(self.client.open_store, store_id)
        if not result:
            raise RuntimeError(f"打开店铺失败: {store_id}")

        cdp_port = result.get("debuggingPort")
        if not cdp_port:
            raise RuntimeError("未获取到 CDP 调试端口")

        pw = await self._ensure_playwright()

        retries = 3
        browser = None
        for attempt in range(retries):
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{cdp_port}"
                )
                break
            except Exception as exc:
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(
                        f"无法连接到 CDP 端口 {cdp_port}，请检查店铺是否已正常打开"
                    ) from exc

        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        pages = context.pages or [await context.new_page()]

        store_name = result.get("browserName", store_id)
        session = StoreSession(
            store_id=store_id,
            store_name=store_name,
            cdp_port=cdp_port,
            browser=browser,
            context=context,
            pages=list(pages),
            active_page_index=0,
            open_result=result,
        )

        for page in session.pages:
            self._setup_page_listeners(session, page)

        self._stores[store_id] = session
        self._active_store_id = store_id

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
                pw = await self._ensure_playwright()
                try:
                    browser = await pw.chromium.connect_over_cdp(
                        f"http://127.0.0.1:{cdp_port}"
                    )
                    contexts = browser.contexts
                    context = contexts[0] if contexts else await browser.new_context()
                    pages = context.pages or [await context.new_page()]

                    session = StoreSession(
                        store_id=store_id,
                        store_name=info.get("store_name", store_id),
                        cdp_port=cdp_port,
                        browser=browser,
                        context=context,
                        pages=list(pages),
                        active_page_index=0,
                        open_result=info,
                    )
                    for page in session.pages:
                        self._setup_page_listeners(session, page)

                    self._stores[store_id] = session
                    self._active_store_id = store_id
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
            await session.browser.close()
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

    def get_active_page(self) -> Page:
        """返回当前店铺会话中的活动页面。"""
        session = self.get_active_session()
        session.pages = list(session.context.pages)
        if not session.pages:
            raise RuntimeError("没有打开的页面")
        if session.active_page_index >= len(session.pages):
            session.active_page_index = 0
        return session.pages[session.active_page_index]

    def get_open_store_ids(self) -> list[str]:
        """返回当前已打开店铺的 ID 列表。"""
        return list(self._stores.keys())

    def _setup_page_listeners(self, store: StoreSession, page: Page) -> None:
        """为页面绑定 console/request/response/dialog 等监听并写入 store。"""
        page_id = id(page)
        if page_id in store._listened_page_ids:  # pylint: disable=protected-access
            return
        store._listened_page_ids.add(page_id)  # pylint: disable=protected-access

        def on_console(msg):
            store._msg_counter += 1  # pylint: disable=protected-access
            store.console_messages.append(
                ConsoleMessage(
                    id=store._msg_counter,  # pylint: disable=protected-access
                    level=msg.type,
                    text=msg.text,
                    timestamp=time.time(),
                )
            )

        def on_request(request):
            store._req_counter += 1  # pylint: disable=protected-access
            store.network_requests.append(
                NetworkRequest(
                    id=store._req_counter,  # pylint: disable=protected-access
                    url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                    request_headers=dict(request.headers),
                    timestamp=time.time(),
                )
            )

        def on_response(response):
            for req in reversed(store.network_requests):
                if req.url == response.url and req.status is None:
                    req.status = response.status
                    req.status_text = response.status_text
                    req.response_headers = dict(response.headers)
                    break

        async def on_dialog(dialog):
            if store.dialog_action == "accept":
                await dialog.accept(store.dialog_text or None)
            else:
                await dialog.dismiss()

        page.on("console", on_console)
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("dialog", on_dialog)

    async def cleanup(self) -> None:
        """关闭所有店铺会话并停止 Playwright。"""
        for store_id in list(self._stores):
            await self.close_store(store_id)
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
