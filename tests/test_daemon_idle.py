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
    # reap_dead_sessions 是 async 方法，必须给 AsyncMock，否则 watchdog 里
    # `await self._session_manager.reap_dead_sessions()` 会把 MagicMock 当成
    # 协程抛 TypeError，污染后续 idle 判定。
    srv._session_manager.reap_dead_sessions = AsyncMock(return_value=[])
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


# ------------------------------------------------------------------ #
#  _last_activity 污染防护：空包 / 无效 JSON 不能刷活跃时间，
#  否则外部端口嗅探会让 idle_watchdog 永远到不了阈值，daemon 不退出。
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_handle_client_empty_data_does_not_refresh_last_activity() -> None:
    srv = daemon_mod.DaemonServer()
    frozen = 1000.0
    srv._last_activity = frozen

    await srv.handle_client(_StubReader(b""), _StubWriter())  # type: ignore[arg-type]

    assert srv._last_activity == frozen, (
        "空连接不得重置 _last_activity，否则端口嗅探可让 watchdog 永远不触发"
    )


@pytest.mark.asyncio
async def test_handle_client_invalid_json_does_not_refresh_last_activity() -> None:
    srv = daemon_mod.DaemonServer()
    frozen = 1000.0
    srv._last_activity = frozen

    await srv.handle_client(_StubReader(b"not a json\n"), _StubWriter())  # type: ignore[arg-type]

    assert srv._last_activity == frozen


@pytest.mark.asyncio
async def test_handle_client_valid_request_refreshes_last_activity() -> None:
    srv = daemon_mod.DaemonServer()
    srv._dispatch = AsyncMock(return_value={"ok": True})
    srv._last_activity = 0.0

    await srv.handle_client(_StubReader(b'{"command":"ping"}\n'), _StubWriter())  # type: ignore[arg-type]

    assert srv._last_activity > 0.0


# ------------------------------------------------------------------ #
#  写回失败：CLI 超时断开后 daemon 仍可能已完成带副作用的命令，
#  必须以 warning 级别日志暴露 command 便于事后对账。
# ------------------------------------------------------------------ #


class _BrokenWriter(_StubWriter):
    async def drain(self) -> None:
        raise ConnectionResetError("client gone")


@pytest.mark.asyncio
async def test_handle_client_writeback_failure_logs_warning_with_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    srv = daemon_mod.DaemonServer()
    srv._dispatch = AsyncMock(return_value={"ok": True})

    with caplog.at_level("WARNING", logger=daemon_mod._logger.name):
        await srv.handle_client(  # type: ignore[arg-type]
            _StubReader(b'{"command":"click"}\n'), _BrokenWriter(),
        )

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "写回失败必须以 warning 级别暴露，debug 会被过滤掉"
    joined = " ".join(r.getMessage() for r in warnings)
    assert "click" in joined, "日志必须带上 command，便于排查孤儿执行"


# ------------------------------------------------------------------ #
#  CDP 断开识别 + dispatch 结构化错误：_is_cdp_disconnected_error 覆盖
#  websockets/ConnectionReset/字符串兜底，且 dispatch 会清掉缓存并返回
#  code=cdp_disconnected，CLI 据此可安全重试。
# ------------------------------------------------------------------ #


class TestCdpDisconnectedError:
    def test_detects_websockets_connection_closed(self) -> None:
        from ziniao_mcp.cli.dispatch import _is_cdp_disconnected_error
        from websockets.exceptions import ConnectionClosedError

        assert _is_cdp_disconnected_error(ConnectionClosedError(None, None)) is True

    def test_detects_connection_reset(self) -> None:
        from ziniao_mcp.cli.dispatch import _is_cdp_disconnected_error

        assert _is_cdp_disconnected_error(ConnectionResetError()) is True
        assert _is_cdp_disconnected_error(BrokenPipeError()) is True

    def test_detects_string_match_for_nodriver_runtime_errors(self) -> None:
        from ziniao_mcp.cli.dispatch import _is_cdp_disconnected_error

        assert _is_cdp_disconnected_error(RuntimeError("connection is closed")) is True
        assert _is_cdp_disconnected_error(
            RuntimeError("no close frame received")
        ) is True

    def test_does_not_mistake_regular_errors(self) -> None:
        from ziniao_mcp.cli.dispatch import _is_cdp_disconnected_error

        assert _is_cdp_disconnected_error(ValueError("bad input")) is False
        assert _is_cdp_disconnected_error(KeyError("x")) is False
        assert _is_cdp_disconnected_error(RuntimeError("element not found")) is False


@pytest.mark.asyncio
async def test_dispatch_cdp_disconnected_invalidates_session_and_returns_code() -> None:
    from ziniao_mcp.cli.dispatch import dispatch

    sm = MagicMock()
    sm._active_store_id = "store-123"
    sm.active_session_id = "store-123"
    sm._stores = {"store-123": object()}
    sm.invalidate_session = MagicMock()

    async def failing_exec(_sm, _cmd, _args):
        raise ConnectionResetError("chrome killed")

    import ziniao_mcp.cli.dispatch as disp_mod
    orig_execute = disp_mod._execute
    disp_mod._execute = failing_exec  # type: ignore[assignment]
    try:
        result = await dispatch(sm, {"command": "click", "args": {}})
    finally:
        disp_mod._execute = orig_execute  # type: ignore[assignment]

    assert result.get("code") == "cdp_disconnected"
    assert result.get("store_id") == "store-123"
    sm.invalidate_session.assert_called_once_with("store-123")


# ------------------------------------------------------------------ #
#  SessionManager.invalidate_session：清内存缓存 + 停 browser + 移状态文件
# ------------------------------------------------------------------ #


def test_invalidate_session_cleans_cache_and_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ziniao_mcp.session import SessionManager

    sm = SessionManager(client=None)
    fake_browser = MagicMock()
    fake_session = MagicMock()
    fake_session.browser = fake_browser
    sm._stores["s1"] = fake_session
    sm._stores["s2"] = MagicMock()
    sm._active_store_id = "s1"

    removed: list[str] = []
    monkeypatch.setattr(
        SessionManager, "_remove_store_state",
        staticmethod(lambda sid: removed.append(sid)),
    )

    sm.invalidate_session("s1")

    assert "s1" not in sm._stores
    assert sm._active_store_id == "s2", "清理活跃会话后必须选下一个会话作为 active"
    fake_browser.stop.assert_called_once()
    assert removed == ["s1"]


def test_invalidate_session_tolerates_browser_stop_failure() -> None:
    from ziniao_mcp.session import SessionManager

    sm = SessionManager(client=None)
    fake_session = MagicMock()
    fake_session.browser.stop.side_effect = RuntimeError("already closed")
    sm._stores["s1"] = fake_session
    sm._active_store_id = "s1"

    sm.invalidate_session("s1")

    assert "s1" not in sm._stores
    assert sm._active_store_id is None


# ------------------------------------------------------------------ #
#  watchdog 顺带清理幽灵会话：
#  - 每轮睡醒都应调用 reap_dead_sessions（把被动清理升级为主动探测）
#  - reap 把死会话清掉后才判定 idle，active_store_count 此时应返回 0
#  - SessionManager.reap_dead_sessions 本身对探活结果的处理（True 保留 /
#    False / 异常 一律视为死，调 invalidate_session）
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_watchdog_invokes_reap_dead_sessions_each_cycle(
    server: daemon_mod.DaemonServer,
) -> None:
    server._last_activity = time.monotonic()  # 不触发 idle shutdown
    server._inflight = 0

    await _run_watchdog_briefly(server, sleep_seconds=0.02)

    assert server._session_manager.reap_dead_sessions.await_count >= 1, (
        "watchdog 每轮必须调用 reap_dead_sessions，否则只读视图看不到死会话"
    )


@pytest.mark.asyncio
async def test_reap_wrapper_swallows_timeout_and_exceptions(
    server: daemon_mod.DaemonServer,
) -> None:
    """_reap_dead_sessions 必须吞掉 TimeoutError / 任意异常，不污染 watchdog 主循环。

    如果不吞：watchdog 的 `while True` 里一次 reap 卡死或抛错就会让协程退出，
    daemon 从此失去后台清理能力，直到重启才会恢复——这是我们要避免的回归。

    这里直接单元测 wrapper，绕开 watchdog 循环的 timing 依赖。
    """
    # Case 1: reap 永不返回 → wait_for 触发 TimeoutError
    async def never_returns() -> list[str]:
        await asyncio.sleep(3600)
        return []

    server._session_manager.reap_dead_sessions = AsyncMock(side_effect=never_returns)
    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
        return await orig_wait_for(coro, timeout=0.02)

    old = daemon_mod.asyncio.wait_for
    daemon_mod.asyncio.wait_for = fast_wait_for  # type: ignore[assignment]
    try:
        await server._reap_dead_sessions()
    finally:
        daemon_mod.asyncio.wait_for = old  # type: ignore[assignment]

    # Case 2: reap 抛任意异常
    server._session_manager.reap_dead_sessions = AsyncMock(
        side_effect=RuntimeError("boom"),
    )
    await server._reap_dead_sessions()

    # Case 3: session_manager 为 None 走短路
    server._session_manager = None
    await server._reap_dead_sessions()


@pytest.mark.asyncio
async def test_watchdog_reap_enables_idle_shutdown_after_clearing_ghosts(
    server: daemon_mod.DaemonServer,
) -> None:
    """关键场景：reap 清掉幽灵会话 → active_store_count 随后变 0 → 允许 idle 关机。

    这是本次补强的核心收益：幽灵会话不再无限阻塞 daemon 空闲回收。
    """
    server._last_activity = time.monotonic() - 10_000
    server._inflight = 0
    server._server = MagicMock()

    store_count = {"value": 2}

    async def reap_clears_ghosts() -> list[str]:
        cleared = ["ghost-1", "ghost-2"]
        store_count["value"] = 0
        return cleared

    server._session_manager.reap_dead_sessions = AsyncMock(side_effect=reap_clears_ghosts)
    server._session_manager.active_store_count = MagicMock(
        side_effect=lambda: store_count["value"],
    )

    await _run_watchdog_briefly(server, sleep_seconds=0.02)

    server.shutdown.assert_awaited()


@pytest.mark.asyncio
async def test_reap_dead_sessions_invalidates_dead_and_keeps_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SessionManager.reap_dead_sessions 的单元行为：按探活结果精准清理。"""
    from ziniao_mcp import session as session_mod

    sm = session_mod.SessionManager(client=None)
    s_alive = MagicMock()
    s_alive.cdp_port = 9001
    s_dead = MagicMock()
    s_dead.cdp_port = 9002
    s_boom = MagicMock()
    s_boom.cdp_port = 9003
    sm._stores["alive"] = s_alive
    sm._stores["dead"] = s_dead
    sm._stores["boom"] = s_boom
    sm._active_store_id = "alive"

    async def fake_probe(port: int, timeout: float = 1.0) -> bool:
        if port == 9001:
            return True
        if port == 9002:
            return False
        raise OSError("network blip")

    monkeypatch.setattr(session_mod, "_is_cdp_alive", fake_probe)

    cleared = await sm.reap_dead_sessions()

    # False 和 Exception 都视为死；只有 True 才保留。
    assert set(cleared) == {"dead", "boom"}
    assert "alive" in sm._stores
    assert "dead" not in sm._stores
    assert "boom" not in sm._stores
    assert sm._active_store_id == "alive"


@pytest.mark.asyncio
async def test_reap_dead_sessions_empty_is_noop() -> None:
    from ziniao_mcp import session as session_mod

    sm = session_mod.SessionManager(client=None)
    cleared = await sm.reap_dead_sessions()
    assert cleared == []
