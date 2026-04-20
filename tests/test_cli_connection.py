"""CLI → daemon 传输层测试：send_command 的连接失败重试。

30min idle 自退 / daemon 崩溃的窗口期内，find_daemon 可能短暂返回旧 port
让 socket.create_connection 抛 ConnectionRefused。send_command 必须在
**未写入任何数据前**重试一次，避免用户看到偶发"第一条命令失败、重跑就好"。
重试若发生在写入后是不允许的（会造成重复副作用）。
"""

from __future__ import annotations

import socket as socket_mod
from unittest.mock import MagicMock

import pytest

from ziniao_mcp.cli import connection as conn_mod


class _FakeSocket:
    """最小 socket stub：记录 sendall / recv 调用。"""

    def __init__(self, response: bytes = b'{"ok":true}\n') -> None:
        self.sent: bytearray = bytearray()
        self._response = response
        self._emitted = False
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def shutdown(self, _how: int) -> None:
        return None

    def settimeout(self, _t: float) -> None:
        return None

    def recv(self, _n: int) -> bytes:
        if self._emitted:
            return b""
        self._emitted = True
        return self._response

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _patch_ensure_daemon(monkeypatch: pytest.MonkeyPatch, port: int = 19816) -> MagicMock:
    mock = MagicMock(return_value=port)
    monkeypatch.setattr(conn_mod, "ensure_daemon", mock)
    return mock


def test_send_command_retries_once_on_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_mock = _patch_ensure_daemon(monkeypatch)
    fake_sock = _FakeSocket()
    calls: list[int] = []

    def flaky_create_connection(_addr, timeout):  # type: ignore[no-untyped-def]
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionRefusedError("daemon just died")
        return fake_sock

    monkeypatch.setattr(socket_mod, "create_connection", flaky_create_connection)
    monkeypatch.setattr(conn_mod.socket, "create_connection", flaky_create_connection)
    monkeypatch.setattr(conn_mod.time, "sleep", lambda _s: None)

    unlinked: list[bool] = []
    fake_pid_file = MagicMock()
    fake_pid_file.unlink = MagicMock(side_effect=lambda missing_ok=False: unlinked.append(True))
    monkeypatch.setattr(conn_mod, "_PID_FILE", fake_pid_file)

    result = conn_mod.send_command("session_list", {}, None, timeout=5.0)

    assert result == {"ok": True}
    assert len(calls) == 2, "第一次 ConnectionRefused 后应重试恰好 1 次"
    assert ensure_mock.call_count == 2, "每次尝试前都要重新 ensure_daemon"
    assert unlinked, "重试前应清掉 stale pid 文件，迫使下一轮重启 daemon"


def test_send_command_does_not_retry_after_data_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sendall/recv 阶段失败不能触发重试 —— 避免对带副作用命令造成重复执行。"""
    _patch_ensure_daemon(monkeypatch)

    class _MidFailSocket(_FakeSocket):
        def recv(self, _n: int) -> bytes:
            raise ConnectionResetError("peer RST after send")

    fake_sock = _MidFailSocket()
    create_calls: list[int] = []

    def once_create_connection(_addr, timeout):  # type: ignore[no-untyped-def]
        create_calls.append(1)
        return fake_sock

    monkeypatch.setattr(socket_mod, "create_connection", once_create_connection)
    monkeypatch.setattr(conn_mod.socket, "create_connection", once_create_connection)

    with pytest.raises(ConnectionResetError):
        conn_mod.send_command("click", {}, None, timeout=5.0)

    assert len(create_calls) == 1, (
        "数据已写入后不得重试：click/flow_run 等带副作用命令重试会造成重复执行"
    )


def test_send_command_gives_up_after_second_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ensure_daemon(monkeypatch)
    calls: list[int] = []

    def always_fail(_addr, timeout):  # type: ignore[no-untyped-def]
        calls.append(1)
        raise ConnectionRefusedError("never up")

    monkeypatch.setattr(socket_mod, "create_connection", always_fail)
    monkeypatch.setattr(conn_mod.socket, "create_connection", always_fail)
    monkeypatch.setattr(conn_mod.time, "sleep", lambda _s: None)
    fake_pid_file = MagicMock()
    fake_pid_file.unlink = MagicMock()
    monkeypatch.setattr(conn_mod, "_PID_FILE", fake_pid_file)

    with pytest.raises(RuntimeError, match="无法连接 daemon"):
        conn_mod.send_command("ping", {}, None, timeout=5.0)

    assert len(calls) == 2, "最多重试 1 次，避免在 daemon 真不可用时无限重试"
