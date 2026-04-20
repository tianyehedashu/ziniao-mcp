"""ziniao daemon — long-lived background process that holds browser sessions.

Run directly: ``python -m ziniao_mcp.cli.daemon``
Started automatically by the CLI when no daemon is detected.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from ..logging_setup import configure_logging

_STATE_DIR = Path.home() / ".ziniao"
_PID_FILE = _STATE_DIR / "daemon.pid"
_DEFAULT_PORT = 19816
_IDLE_TIMEOUT = 30 * 60  # 30 minutes

# daemon 默认走共享的 mcp_debug.log；需要独立 daemon.log 时可通过
# ``ZINIAO_LOG_FILE`` 覆盖。关键是不再在根 logger 上直接 DEBUG。
os.environ.setdefault("ZINIAO_LOG_FILE", str(_STATE_DIR / "daemon.log"))
configure_logging(role="daemon")
_logger = logging.getLogger("ziniao-daemon")


def _find_free_port() -> int:
    import socket  # pylint: disable=import-outside-toplevel
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_pid_file(port: int) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(f"{os.getpid()}\n{port}\n")


def _remove_pid_file() -> None:
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class DaemonServer:
    """Asyncio TCP JSON server wrapping a SessionManager."""

    def __init__(self) -> None:
        self._session_manager: Any = None
        self._server: asyncio.AbstractServer | None = None
        self._last_activity: float = time.monotonic()
        self._shutting_down = False
        # 在途请求计数：watchdog 须在命令处理期间避让，避免中途 shutdown 把会话拆掉。
        self._inflight: int = 0

    async def setup(self) -> None:
        from ..server import _resolve_config, _has_ziniao_config  # pylint: disable=import-outside-toplevel
        from ..session import SessionManager  # pylint: disable=import-outside-toplevel

        config = _resolve_config()

        from ..stealth import StealthConfig  # pylint: disable=import-outside-toplevel
        stealth_cfg = StealthConfig.from_dict(config.get("stealth") or {})

        client = None
        if _has_ziniao_config(config):
            from ziniao_webdriver import ZiniaoClient, detect_ziniao_port  # pylint: disable=import-outside-toplevel
            from ziniao_webdriver.client import _DEFAULT_PORT as ZN_DEFAULT  # pylint: disable=import-outside-toplevel

            configured_port = config.get("socket_port")
            if configured_port:
                port = int(configured_port)
            else:
                detected = detect_ziniao_port()
                port = detected if detected else ZN_DEFAULT
            client = ZiniaoClient(
                client_path=config.get("client_path") or "",
                socket_port=port,
                user_info={
                    "company": config.get("company") or "",
                    "username": config.get("username") or "",
                    "password": config.get("password") or "",
                },
                version=config.get("version") or "v6",
            )
        self._session_manager = SessionManager(
            client, stealth_config=stealth_cfg,
            chrome_config=config.get("chrome") or {},
        )
        _logger.info("SessionManager initialized")

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        # 必须在 try 之前初始化：空数据分支会 return，finally 里仍会引用 response；
        # None 表示"无需回写响应"（客户端未发送任何数据），避免历史上靠 broad-except
        # 吞 NameError 导致的静默失败。
        response: dict | None = None
        # 规范写法：+1 紧贴 try 前、-1 在 finally。Python 保证 finally 只在
        # 进入 try 之后才执行，所以任何在 +1 之前抛出的异常都不会触发"白 -1"。
        # 不要把 +1 挪到 try 内：万一未来在 += 1 之前加了会抛的同步代码，
        # finally 反而会在没 +1 的情况下 -1，真的造成计数错位。
        self._inflight += 1
        command: str | None = None
        max_line = 64 * 1024 * 1024
        try:
            # 不能单次 read(上限)：首包可能远小于完整 JSON（flow_run + 内联 HTML），
            # 会截断 → json.loads 报 Unterminated string。按换行累积读到完整一行。
            # 也不用 readuntil(..., n=)：部分 Python/asyncio 组合不支持该关键字参数。
            buf = bytearray()
            raw = ""
            too_large = False
            while True:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=60.0)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > max_line:
                    too_large = True
                    break
                nl = buf.find(b"\n")
                if nl != -1:
                    raw = buf[:nl].decode("utf-8").strip()
                    break
            if too_large:
                response = {
                    "error": (
                        f"Request line exceeds maximum ({max_line} bytes before newline)."
                    ),
                }
            elif not raw and not buf:
                # 空包通常意味着客户端异常断开 / 旧 PowerShell 发送空行 / 端口嗅探。
                # 不刷 _last_activity：否则 find_daemon 的 _is_port_open 探测或
                # 外部端口嗅探会让 idle watchdog 永远到不了阈值。
                _logger.debug(
                    "空连接来自 %s，立即关闭（客户端未发送数据）", addr,
                )
                return
            else:
                if not raw:
                    raw = buf.decode("utf-8").strip()
                request = json.loads(raw)
                command = request.get("command")
                # 只有解析出真实请求后才算作活跃：进入函数即刷会被空包 / 无效 JSON 污染。
                self._last_activity = time.monotonic()
                _logger.debug("Request from %s: %s", addr, command)
                response = await self._dispatch(request)
        except asyncio.TimeoutError:
            response = {"error": "Read timeout"}
        except json.JSONDecodeError as e:
            response = {"error": f"Invalid JSON: {e}"}
        except Exception as exc:
            _logger.exception("Error handling request")
            response = {"error": str(exc)}
        finally:
            # 长耗时命令结束后再刷一次：watchdog 在命令执行期间不会误判空闲。
            # 仅在 command 已解析出（即真实请求）时更新，保持与进入时的判定一致。
            if command is not None:
                self._last_activity = time.monotonic()
            self._inflight = max(0, self._inflight - 1)
            if response is not None:
                try:
                    payload = (
                        json.dumps(response, ensure_ascii=False, default=str) + "\n"
                    )
                    writer.write(payload.encode("utf-8"))
                    await writer.drain()
                except Exception:  # pylint: disable=broad-exception-caught
                    # 升到 warning：CLI 超时后 daemon 仍可能已执行完带副作用的命令
                    # （click/flow_run/page_fetch 等），用户重试会造成重复副作用。
                    # 带上 command 便于事后对账，确认是否出现孤儿执行。
                    _logger.warning(
                        "写回响应失败 (addr=%s, command=%s)：CLI 可能已超时断开，"
                        "若命令具有副作用请检查是否重复执行",
                        addr, command, exc_info=True,
                    )
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # pylint: disable=broad-exception-caught
                # 与"写回响应失败"对齐，留诊断信息；close 失败通常是对端已经 RST。
                _logger.debug("关闭连接失败 (addr=%s)", addr, exc_info=True)

    async def _dispatch(self, request: dict) -> dict:
        from .dispatch import dispatch  # pylint: disable=import-outside-toplevel
        return await dispatch(self._session_manager, request)

    async def run(self, port: int = 0) -> None:
        await self.setup()
        if port <= 0:
            port = _DEFAULT_PORT
            import socket  # pylint: disable=import-outside-toplevel
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
            except OSError:
                port = _find_free_port()

        self._server = await asyncio.start_server(
            self.handle_client, "127.0.0.1", port,
        )
        _write_pid_file(port)
        _logger.info("Daemon started on 127.0.0.1:%d (pid=%d)", port, os.getpid())

        async with self._server:
            idle_task = asyncio.create_task(self._idle_watchdog())
            try:
                await self._server.serve_forever()
            except asyncio.CancelledError:
                pass
            finally:
                idle_task.cancel()
                await self._cleanup()

    async def _idle_watchdog(self) -> None:
        while not self._shutting_down:
            await asyncio.sleep(60)
            # 顺带清理幽灵会话：用户手动关 Chrome / 紫鸟空闲回收 / 进程崩溃都会
            # 让缓存中的 StoreSession 对应的 CDP 已死但对象仍在。定期探活 +
            # invalidate 让只读视图（session list 等）始终反映真实状态，也能
            # 避免 active_store_count 误报而阻塞下面的 idle 判定。
            # 不把它放在 idle 判定之后：清理掉幽灵会话恰恰能让 daemon 进入空闲。
            await self._reap_dead_sessions()
            idle = time.monotonic() - self._last_activity
            if idle <= _IDLE_TIMEOUT:
                continue
            # 有在途请求：正在跑长耗时命令（flow_run / 批量上传等），不能打断。
            if self._inflight > 0:
                _logger.debug(
                    "Idle %.0fs 但仍有 %d 个在途请求，跳过自动关机",
                    idle, self._inflight,
                )
                continue
            # 有活跃会话：强关会误杀用户的 Ziniao 店铺 / Chrome 进程，
            # 必须由用户显式 close_store / stop_client 结束，不走 idle 清理路径。
            active = 0
            try:
                if self._session_manager is not None:
                    active = self._session_manager.active_store_count()
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("读取活跃会话数失败", exc_info=True)
            if active > 0:
                _logger.debug(
                    "Idle %.0fs 但仍有 %d 个活跃浏览器会话，跳过自动关机",
                    idle, active,
                )
                continue
            _logger.info("Idle timeout reached (%.0fs), shutting down", idle)
            await self.shutdown()
            break

    async def _reap_dead_sessions(self) -> None:
        """调用 SessionManager.reap_dead_sessions，任何异常都吞掉避免终止 watchdog。

        加 10s 总超时兜底：探活协程被某种底层卡死时，watchdog 不至于永久阻塞。
        """
        if self._session_manager is None:
            return
        try:
            await asyncio.wait_for(
                self._session_manager.reap_dead_sessions(), timeout=10.0,
            )
        except asyncio.TimeoutError:
            _logger.warning("reap_dead_sessions 超过 10s 未完成，下轮重试")
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("reap_dead_sessions 失败（非致命）", exc_info=True)

    async def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self._server:
            self._server.close()

    async def _cleanup(self) -> None:
        _logger.info("Cleaning up sessions")
        if self._session_manager:
            try:
                await self._session_manager.cleanup()
            except Exception:
                _logger.exception("Error during cleanup")
        _remove_pid_file()
        _logger.info("Daemon stopped")


async def _async_main() -> None:
    server = DaemonServer()

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(server.shutdown()))

    await server.run()


def main() -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    from ..dotenv_loader import load_dotenv  # pylint: disable=import-outside-toplevel
    load_dotenv()
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass
    finally:
        _remove_pid_file()


if __name__ == "__main__":
    main()
