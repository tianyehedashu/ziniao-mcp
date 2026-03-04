"""紫鸟 MCP 服务器入口：配置解析、工具注册、启动。"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    from importlib.metadata import PackageNotFoundError, version
    _PACKAGE_VERSION = version("ziniao-mcp")
except (ImportError, PackageNotFoundError):
    _PACKAGE_VERSION = "0.0.0.dev"

from mcp.server.fastmcp import FastMCP

from ziniao_webdriver import ZiniaoClient, detect_ziniao_port
from ziniao_webdriver.client import _DEFAULT_PORT

from .session import SessionManager

_debug_log = Path(__file__).resolve().parent.parent / "mcp_debug.log"
logging.basicConfig(
    filename=str(_debug_log),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
_logger = logging.getLogger("ziniao-mcp-debug")


def _print_package_version_and_exit() -> None:
    """若传入 -V/--package-version 则打印包版本并退出。"""
    if "-V" in sys.argv or "--package-version" in sys.argv:
        print(f"ziniao-mcp {_PACKAGE_VERSION}")
        sys.exit(0)


def _resolve_config() -> dict[str, Any]:
    """解析配置，优先级: 环境变量 > 命令行参数 > config.yaml"""
    _print_package_version_and_exit()
    parser = argparse.ArgumentParser(description="紫鸟 MCP 服务器")
    parser.add_argument("-V", "--package-version", action="store_true", help="显示包版本并退出")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--company", default=None, help="企业名")
    parser.add_argument("--username", default=None, help="用户名")
    parser.add_argument("--password", default=None, help="密码")
    parser.add_argument("--client-path", default=None, help="紫鸟客户端路径")
    parser.add_argument("--socket-port", type=int, default=None, help="HTTP 通信端口")
    parser.add_argument("--version", choices=["v5", "v6"], default=None, help="客户端版本")
    args, _ = parser.parse_known_args()

    yaml_config: dict[str, Any] = {}
    config_path = args.config
    if not config_path:
        candidates = [
            Path("config/config.yaml"),
            Path(__file__).resolve().parent.parent / "config" / "config.yaml",
        ]
        for p in candidates:
            if p.exists():
                config_path = str(p)
                break

    if config_path and Path(config_path).exists():
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if "ziniao" in raw:
            browser_cfg = raw["ziniao"].get("browser", {})
            user_cfg = raw["ziniao"].get("user_info", {})
            yaml_config = {
                "company": user_cfg.get("company"),
                "username": user_cfg.get("username"),
                "password": user_cfg.get("password"),
                "client_path": browser_cfg.get("client_path"),
                "socket_port": browser_cfg.get("socket_port"),
                "version": browser_cfg.get("version"),
            }

    cli_config = {
        "company": args.company,
        "username": args.username,
        "password": args.password,
        "client_path": getattr(args, "client_path", None),
        "socket_port": args.socket_port,
        "version": args.version,
    }

    env_map = {
        "company": "ZINIAO_COMPANY",
        "username": "ZINIAO_USERNAME",
        "password": "ZINIAO_PASSWORD",
        "client_path": "ZINIAO_CLIENT_PATH",
        "socket_port": "ZINIAO_SOCKET_PORT",
        "version": "ZINIAO_VERSION",
    }
    env_config: dict[str, Any] = {}
    for key, env_var in env_map.items():
        val = os.environ.get(env_var)
        if val is not None:
            env_config[key] = int(val) if key == "socket_port" else val

    all_keys = ["company", "username", "password", "client_path", "socket_port", "version"]
    config: dict[str, Any] = {}
    for key in all_keys:
        config[key] = (
            env_config.get(key)
            or cli_config.get(key)
            or yaml_config.get(key)
        )

    return config


def create_server() -> tuple[FastMCP, SessionManager]:
    config = _resolve_config()

    configured_port = config.get("socket_port")
    if configured_port:
        port = int(configured_port)
    else:
        detected = detect_ziniao_port()
        port = detected if detected else _DEFAULT_PORT
        _logger.info("未配置 ZINIAO_SOCKET_PORT，%s端口: %s",
                      "自动检测到" if detected else "使用默认", port)

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

    session = SessionManager(client)
    mcp = FastMCP("ziniao-mcp")

    from .tools.debug import register_tools as register_debug
    from .tools.emulation import register_tools as register_emulation
    from .tools.input import register_tools as register_input
    from .tools.navigation import register_tools as register_navigation
    from .tools.network import register_tools as register_network
    from .tools.store import register_tools as register_store

    register_store(mcp, session)
    register_input(mcp, session)
    register_navigation(mcp, session)
    register_emulation(mcp, session)
    register_network(mcp, session)
    register_debug(mcp, session)

    return mcp, session


def main() -> None:
    # 先解析参数，使 --help 在启动任何线程前退出，避免解释器关闭时与 daemon 线程争用 stdin
    _resolve_config()

    _logger.info("=== ziniao-mcp starting ===")
    _logger.info("Python: %s", sys.version)
    _logger.info("Platform: %s", sys.platform)
    _logger.info("stdin: %s, isatty=%s", sys.stdin, sys.stdin.isatty() if sys.stdin else "N/A")
    _logger.info("stdout: %s, isatty=%s", sys.stdout, sys.stdout.isatty() if sys.stdout else "N/A")
    _logger.info("stdin.buffer: %s", getattr(sys.stdin, 'buffer', 'N/A'))
    _logger.info("stdout.buffer: %s", getattr(sys.stdout, 'buffer', 'N/A'))
    _logger.info("stdin fileno: %s", sys.stdin.fileno() if sys.stdin else "N/A")
    _logger.info("stdout fileno: %s", sys.stdout.fileno() if sys.stdout else "N/A")
    _logger.info("ENV keys: %s", sorted(os.environ.keys()))

    import threading
    def _stdin_monitor():
        """Background thread to log raw stdin activity."""
        try:
            _logger.info("[stdin-monitor] Starting raw read on stdin.buffer")
            peek_fn = getattr(sys.stdin.buffer, "peek", None)
            data = peek_fn(1) if callable(peek_fn) else b""
            _logger.info("[stdin-monitor] peek returned: %s", repr(data[:100] if data else data))
        except Exception as e:
            _logger.info("[stdin-monitor] peek error: %s", e)
            try:
                data = sys.stdin.buffer.read(1)
                _logger.info("[stdin-monitor] read(1) returned: %s", repr(data))
            except Exception as e2:
                _logger.info("[stdin-monitor] read(1) error: %s", e2)
    t = threading.Thread(target=_stdin_monitor, daemon=True)
    t.start()
    t.join(timeout=5)
    _logger.info("[stdin-monitor] Joined (done=%s)", not t.is_alive())

    try:
        mcp, _session = create_server()
        _logger.info("Server created, starting mcp.run()")
        mcp.run()
    except Exception:
        _logger.exception("Fatal error in main")
        raise


if __name__ == "__main__":
    main()
