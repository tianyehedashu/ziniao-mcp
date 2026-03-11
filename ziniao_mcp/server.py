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
    parser = argparse.ArgumentParser(
        description="紫鸟与 Chrome 浏览器 MCP 服务器 — 统一操控紫鸟店铺与本地 Chrome"
    )
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
                "stealth": raw["ziniao"].get("stealth", {}),
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

    config["stealth"] = yaml_config.get("stealth", {})

    chrome_yaml = {}
    if config_path and Path(config_path).exists():
        import yaml  # pylint: disable=import-outside-toplevel
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}
        chrome_yaml = raw_cfg.get("chrome", {})

    chrome_env = {
        "executable_path": os.environ.get("CHROME_EXECUTABLE_PATH"),
        "default_cdp_port": os.environ.get("CHROME_CDP_PORT"),
        "user_data_dir": os.environ.get("CHROME_USER_DATA_DIR"),
    }
    _port_raw = chrome_env["default_cdp_port"] or chrome_yaml.get("default_cdp_port", 0)
    try:
        _default_cdp_port = int(_port_raw)
    except (ValueError, TypeError):
        _default_cdp_port = 0
    config["chrome"] = {
        "executable_path": chrome_env["executable_path"] or chrome_yaml.get("executable_path", ""),
        "default_cdp_port": _default_cdp_port,
        "user_data_dir": chrome_env["user_data_dir"] or chrome_yaml.get("user_data_dir", ""),
        "headless": chrome_yaml.get("headless", False),
    }

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

    from .stealth import StealthConfig  # pylint: disable=import-outside-toplevel

    stealth_cfg = StealthConfig.from_dict(config.get("stealth") or {})
    _logger.info("Stealth 配置: enabled=%s, js_patches=%s, human_behavior=%s",
                 stealth_cfg.enabled, stealth_cfg.js_patches, stealth_cfg.human_behavior)

    session = SessionManager(client, stealth_config=stealth_cfg)
    mcp = FastMCP(
        "ziniao-mcp",
        instructions="紫鸟店铺与 Chrome 浏览器自动化：店铺管理（list_stores/open_store）、Chrome 管理（launch_chrome/connect_chrome）、统一会话（browser_session）、页面操作（navigate/click/fill）、录制回放（recorder）等，对紫鸟与 Chrome 共用同一套工具。",
    )

    from .tools.chrome import register_tools as register_chrome
    from .tools.debug import register_tools as register_debug
    from .tools.emulation import register_tools as register_emulation
    from .tools.input import register_tools as register_input
    from .tools.navigation import register_tools as register_navigation
    from .tools.network import register_tools as register_network
    from .tools.recorder import register_tools as register_recorder
    from .tools.session_mgr import register_tools as register_session
    from .tools.store import register_tools as register_store

    register_store(mcp, session)
    register_chrome(mcp, session)
    register_session(mcp, session)
    register_input(mcp, session)
    register_navigation(mcp, session)
    register_emulation(mcp, session)
    register_network(mcp, session)
    register_debug(mcp, session)
    register_recorder(mcp, session)
    _register_prompts(mcp)

    return mcp, session


def _register_prompts(mcp: FastMCP) -> None:
    """注册 MCP prompts，供客户端发现并调用。"""

    @mcp.prompt(
        name="ziniao_mcp",
        title="ziniao MCP 使用指引",
        description="获取 ziniao MCP 使用说明与常见任务示例，便于 AI 操控紫鸟店铺和 Chrome 浏览器。",
    )
    def ziniao_browser_guide() -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": """使用 ziniao MCP 操控浏览器时：

【紫鸟店铺】
- list_stores 查店铺，open_store(store_id) 打开（已运行的自动复用）。
- start_client / stop_client 管理紫鸟客户端进程。

【Chrome 浏览器】
- launch_chrome(name=..., url=...) 启动新 Chrome 实例。
- connect_chrome(cdp_port=9222) 连接已运行的 Chrome（需带 --remote-debugging-port 启动）。
- list_chrome / close_chrome 管理 Chrome 会话。

【会话管理】
- browser_session(action='list') 查看所有活跃会话（紫鸟 + Chrome），确认当前操作的是哪个。
- browser_session(action='switch', session_id=...) 切换当前操作目标。
- browser_session(action='info', session_id=...) 查看会话详情。

【通用页面操作】（对紫鸟和 Chrome 通用，作用于当前活跃会话）
- 导航：navigate_page，点击：click，填写：fill，按键：press_key，等待：wait_for，截图：take_screenshot。
- 标签页：tab(action=list/switch/new/close)。iframe：switch_frame(action=list/switch/main)。
- 录制：recorder(action='start'/'stop'/'replay'/'list')。

根据用户目标调用对应工具即可。""",
            },
        ]


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
            if callable(peek_fn):
                data = peek_fn(1)
            else:
                data = b""
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
