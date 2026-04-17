"""daemon idle watchdog + handle_client 行为测试。

覆盖 regression：
- 有在途请求时 watchdog 不能关机（否则长命令响应会被截断）。
- 有活跃浏览器会话时 watchdog 不能关机（否则 cleanup() 会强关用户的
  Ziniao 店铺 / launch_chrome 进程，造成用户可见的数据丢失）。
- 空闲且无任何会话时才允许关机。
- handle_client 在客户端未发送任何数据时必须正常返回，不得触发未初始化的
  ``response`` 导致的 ``NameError`` / 未回写告警。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ziniao_mcp.cli import daemon as daemon_mod


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch) -> daemon_mod.DaemonServer:
    # 把 idle 阈值调到 0，循环间隔调到几 ms，让测试在真实时间轴上验证 watchdog 行为。
    monkeypatch.setattr(daemon_mod, "_IDLE_TIMEOUT", 0)
    srv = daemon_mod.DaemonServer()
    srv._session_manager = MagicMock()
    srv._session_manager.active_store_count = MagicMock(return_value=0)
    srv.shutdown = AsyncMock(wraps=srv.shutdown)
    return srv


async def _run_watchdog_briefly(
    srv: daemon_mod.DaemonServer, *, sleep_seconds: float = 0.05,
) -> None:
    """把 asyncio.sleep 压成毫秒级后启动一次 watchdog，然后立即回收。"""
    orig_sleep = asyncio.sleep

    async def fast_sleep(_secs: float) -> None:
        await orig_sleep(sleep_seconds)

    old = daemon_mod.asyncio.sleep
    daemon_mod.asyncio.sleep = fast_sleep  # type: ignore[assignment]
    try:
        task = asyncio.create_task(srv._idle_watchdog())
        await orig_sleep(sleep_seconds * 4)
        srv._shutting_down = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        daemon_mod.asyncio.sleep = old  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_idle_skips_shutdown_while_requests_inflight(
    server: daemon_mod.DaemonServer,
) -> None:
    server._last_activity = time.monotonic() - 10_000
    server._inflight = 1
    await _run_watchdog_briefly(server)
    server.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_idle_skips_shutdown_while_sessions_active(
    server: daemon_mod.DaemonServer,
) -> None:
    server._last_activity = time.monotonic() - 10_000
    server._inflight = 0
    server._session_manager.active_store_count = MagicMock(return_value=2)
    await _run_watchdog_briefly(server)
    server.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_idle_shuts_down_when_no_sessions_and_no_inflight(
    server: daemon_mod.DaemonServer,
) -> None:
    server._last_activity = time.monotonic() - 10_000
    server._inflight = 0
    server._session_manager.active_store_count = MagicMock(return_value=0)
    # 阻止真实 server.close() 引发 AttributeError
    server._server = MagicMock()
    await _run_watchdog_briefly(server)
    server.shutdown.assert_awaited()


@pytest.mark.asyncio
async def test_active_store_count_unavailable_is_non_fatal(
    server: daemon_mod.DaemonServer,
) -> None:
    # SessionManager 不存在时 watchdog 仍可正常判定空闲。
    server._last_activity = time.monotonic() - 10_000
    server._inflight = 0
    server._session_manager = None
    server._server = MagicMock()
    await _run_watchdog_briefly(server)
    server.shutdown.assert_awaited()


# ------------------------------------------------------------------ #
#  handle_client: 空数据不得触发未初始化 response（原先被内层 broad-except
#  吞掉 NameError，等于靠运气正确，极易在后续扩展时复发）。
# ------------------------------------------------------------------ #


class _StubReader:
    def __init__(self, payload: bytes = b"") -> None:
        self._payload = payload

    async def read(self, _n: int) -> bytes:
        return self._payload


class _StubWriter:
    def __init__(self) -> None:
        self.written: bytearray = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, _key: str):  # type: ignore[no-untyped-def]
        return ("127.0.0.1", 0)


@pytest.mark.asyncio
async def test_handle_client_empty_data_does_not_raise_and_skips_writeback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    srv = daemon_mod.DaemonServer()
    # 不真正派发；若进入 dispatch，说明空数据分支失效。
    srv._dispatch = AsyncMock(side_effect=AssertionError("dispatch must not run"))

    reader = _StubReader(b"")
    writer = _StubWriter()

    with caplog.at_level("DEBUG", logger=daemon_mod._logger.name):
        await srv.handle_client(reader, writer)  # type: ignore[arg-type]

    # 没有异常、_inflight 正确回零、连接被关闭、空数据不写回任何内容。
    assert srv._inflight == 0
    assert writer.closed is True
    assert bytes(writer.written) == b""
    # 必须留下可观测日志，避免未来排查空包场景时又陷入静默黑洞。
    assert any("空连接" in rec.message for rec in caplog.records), (
        f"空包路径应记 debug 日志，当前 records={[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_handle_client_normal_request_writes_response() -> None:
    srv = daemon_mod.DaemonServer()
    srv._dispatch = AsyncMock(return_value={"ok": True, "value": 42})

    reader = _StubReader(b'{"command":"ping"}\n')
    writer = _StubWriter()

    await srv.handle_client(reader, writer)  # type: ignore[arg-type]

    assert srv._inflight == 0
    assert writer.closed is True
    body = bytes(writer.written).decode("utf-8").strip()
    assert '"ok": true' in body or '"ok":true' in body
    assert '"value": 42' in body or '"value":42' in body
