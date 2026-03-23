"""紫鸟 MCP 服务器入口：配置解析、工具注册、启动。"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    from importlib.metadata import PackageNotFoundError, version
    _PACKAGE_VERSION = version("ziniao")
except (ImportError, PackageNotFoundError):
    _PACKAGE_VERSION = "0.0.0.dev"

from mcp.server.fastmcp import FastMCP

from .session import SessionManager, _STATE_DIR

_debug_log = _STATE_DIR / "mcp_debug.log"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_debug_log),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
_logger = logging.getLogger("ziniao-debug")


def _print_package_version_and_exit() -> None:
    """若传入 -V/--package-version 则打印包版本并退出。"""
    if "-V" in sys.argv or "--package-version" in sys.argv:
        print(f"ziniao {_PACKAGE_VERSION}")
        sys.exit(0)


def _resolve_config() -> dict[str, Any]:
    """解析配置，优先级: 环境变量 > 命令行参数 > .env > config.yaml > ~/.ziniao/config.yaml"""
    from .dotenv_loader import load_dotenv  # pylint: disable=import-outside-toplevel
    load_dotenv()

    _print_package_version_and_exit()
    parser = argparse.ArgumentParser(
        description="Automate Ziniao stores and local Chrome browsers with one MCP server."
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
    chrome_yaml: dict[str, Any] = {}
    config_path = args.config
    if not config_path:
        candidates = [
            Path("config/config.yaml"),
            Path(__file__).resolve().parent.parent / "config" / "config.yaml",
            Path.home() / ".ziniao" / "config.yaml",
        ]
        for p in candidates:
            if p.exists():
                config_path = str(p)
                break

    if config_path and Path(config_path).exists():
        import yaml  # pylint: disable=import-outside-toplevel

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
        chrome_yaml = raw.get("chrome", {})

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
        if val:
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

    chrome_env = {
        "executable_path": os.environ.get("CHROME_PATH") or os.environ.get("CHROME_EXECUTABLE_PATH"),
        "default_cdp_port": os.environ.get("CHROME_CDP_PORT"),
        "user_data_dir": os.environ.get("CHROME_USER_DATA") or os.environ.get("CHROME_USER_DATA_DIR"),
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


def _has_ziniao_config(config: dict[str, Any]) -> bool:
    """判断是否配置了紫鸟相关信息（任一关键字段非空即视为已配置）。"""
    return bool(
        config.get("company")
        or config.get("username")
        or config.get("client_path")
        or config.get("socket_port")
    )


def create_server(config: dict[str, Any] | None = None) -> tuple[FastMCP, SessionManager]:
    if config is None:
        config = _resolve_config()

    from .stealth import StealthConfig  # pylint: disable=import-outside-toplevel

    stealth_cfg = StealthConfig.from_dict(config.get("stealth") or {})
    _logger.info("Stealth 配置: enabled=%s, js_patches=%s, human_behavior=%s",
                 stealth_cfg.enabled, stealth_cfg.js_patches, stealth_cfg.human_behavior)

    client = None
    if _has_ziniao_config(config):
        from ziniao_webdriver import ZiniaoClient, detect_ziniao_port  # pylint: disable=import-outside-toplevel
        from ziniao_webdriver.client import _DEFAULT_PORT  # pylint: disable=import-outside-toplevel

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
        _logger.info("紫鸟客户端已配置 (port=%s)", port)
    else:
        _logger.info("未配置紫鸟信息，仅启用 Chrome 浏览器功能")

    session = SessionManager(
        client, stealth_config=stealth_cfg,
        chrome_config=config.get("chrome") or {},
    )
    mcp = FastMCP(
        "ziniao",
        instructions=(
            "Automate Ziniao stores and Chrome browsers: store management (list_stores/open_store), "
            "Chrome management (launch_chrome/connect_chrome), unified session control (browser_session), "
            "page actions (navigate/click/fill), and record/replay (recorder). "
            "If CDP fails (e.g. connection refused): ensure the store is opened in Ziniao client first, "
            "remote debugging/CDP is enabled in Ziniao settings, and firewall allows 127.0.0.1:port."
        ),
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
    """Register MCP prompts for client discovery."""

    @mcp.prompt(
        name="ziniao_mcp",
        title="Ziniao MCP usage guide",
        description="Get usage instructions and common task examples for operating Ziniao stores and Chrome browsers.",
    )
    def ziniao_browser_guide() -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": """使用 ziniao MCP 操控浏览器时：

【紫鸟店铺】
- list_stores 查店铺，open_store(store_id) 打开（已运行的自动复用）。
- 若出现 CDP 连不上或 tabs: 0：先在紫鸟里手动打开该店铺、确认已开启远程调试/CDP，再 list_stores → open_store → tab list；无标签时用 tab new 打开目标页。
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
- Recording: recorder(action='start'/'stop'/'replay'/'list'/'view'/'status').

根据用户目标调用对应工具即可。""",
            },
        ]

    @mcp.prompt(
        name="ziniao_recorder",
        title="Record and replay browser actions",
        description="Record browser actions, stop and save recordings, and replay saved flows.",
    )
    def ziniao_recorder_guide() -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": """Use the recorder tool to capture and replay browser actions:

- **Start**: recorder(action='start'). Open the target page and active tab first; injection records clicks, typing, keys, and navigation. **Full navigations** (e.g. link clicks) re-inject the recorder and log navigate steps automatically.
- **Stop**: recorder(action='stop', name='optional', force=False). Saves under ~/.ziniao/recordings/; if name is set and the .json exists, use force=true to overwrite.
- **Inspect JSON**: recorder(action='view', name='...', metadata_only=False). Loads metadata and actions; metadata_only=true omits the actions array.
- **Status**: recorder(action='status'). Whether the current session is recording and the start URL.
- **Replay**: recorder(action='replay', name='...') or recorder(action='replay', actions_json='[...]'). Use speed to adjust pace.
- **List / delete**: recorder(action='list'); recorder(action='delete', name='...').

When the user asks to record, stop recording, or replay, call the matching action above.""",
            },
        ]


def main() -> None:
    config = _resolve_config()

    _logger.info("=== ziniao serve starting ===")
    _logger.info("Python: %s", sys.version)
    _logger.info("Platform: %s", sys.platform)

    try:
        mcp, _session = create_server(config)
        _logger.info("Server created, starting mcp.run()")
        mcp.run()
    except Exception:
        _logger.exception("Fatal error in main")
        raise


if __name__ == "__main__":
    main()
