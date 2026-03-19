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

_STATE_DIR = Path.home() / ".ziniao"
_PID_FILE = _STATE_DIR / "daemon.pid"
_DEFAULT_PORT = 19816
_IDLE_TIMEOUT = 30 * 60  # 30 minutes

logging.basicConfig(
    filename=str(_STATE_DIR / "daemon.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
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
        self._session_manager = SessionManager(client, stealth_config=stealth_cfg)
        _logger.info("SessionManager initialized")

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        self._last_activity = time.monotonic()
        addr = writer.get_extra_info("peername")
        try:
            data = await asyncio.wait_for(reader.read(1024 * 1024), timeout=5.0)
            if not data:
                return
            raw = data.decode("utf-8").strip()
            request = json.loads(raw)
            _logger.debug("Request from %s: %s", addr, request.get("command"))
            response = await self._dispatch(request)
        except asyncio.TimeoutError:
            response = {"error": "Read timeout"}
        except json.JSONDecodeError as e:
            response = {"error": f"Invalid JSON: {e}"}
        except Exception as exc:
            _logger.exception("Error handling request")
            response = {"error": str(exc)}
        finally:
            try:
                payload = json.dumps(response, ensure_ascii=False, default=str) + "\n"
                writer.write(payload.encode("utf-8"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

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
            idle = time.monotonic() - self._last_activity
            if idle > _IDLE_TIMEOUT:
                _logger.info("Idle timeout reached (%.0fs), shutting down", idle)
                await self.shutdown()
                break

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
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass
    finally:
        _remove_pid_file()


if __name__ == "__main__":
    main()
