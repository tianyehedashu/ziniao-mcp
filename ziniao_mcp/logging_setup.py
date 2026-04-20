"""集中式日志配置 —— 避免无节制写盘拖垮 asyncio 事件循环。

背景：历史上 server.py / daemon.py 各自调用 ``logging.basicConfig`` 设置
根 logger 为 DEBUG，并把所有日志（含 nodriver / websockets 的 DEBUG 帧、
以及 CDP schema drift 引发的 KeyError traceback）无轮换写入单个
``~/.ziniao/mcp_debug.log``。在 creator.douyin.com 这类高流量页面上，
该文件能在几小时内涨到 10+ GB，FileHandler 的同步 I/O 会阻塞 daemon
的 asyncio 事件循环，进而让 CLI 端看到 "socket 被重置 / preset 超时"。

本模块提供幂等的 ``configure_logging`` 入口：

* 默认挂 ``RotatingFileHandler`` (20MB × 3 份)；
* 只由环境变量升降级，默认 WARNING（应用自身的 ``ziniao-*`` / ``ziniao_mcp.*``
  logger 单独给一档，默认 INFO）；
* 对已知高噪声、与 ziniao 业务无关的第三方 logger（nodriver / websockets /
  asyncio / urllib3 / httpx 等）硬性压到 ERROR，避免 CDP schema 漂移或
  网络事件洪流再次把日志打爆。

环境变量：

* ``ZINIAO_LOG_LEVEL``：应用 logger 级别（DEBUG/INFO/WARNING/ERROR），默认 INFO；
* ``ZINIAO_LOG_ROOT_LEVEL``：根 logger 级别（影响第三方库），默认 WARNING；
* ``ZINIAO_LOG_MAX_BYTES``：单文件字节上限，默认 ``20_000_000``；
* ``ZINIAO_LOG_BACKUPS``：保留的历史份数，默认 ``3``；
* ``ZINIAO_LOG_FILE``：覆盖默认 ``~/.ziniao/mcp_debug.log`` 路径。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_STATE_DIR = Path.home() / ".ziniao"

# 用一个标记 attribute 保证多次 import / 多角色调用都只初始化一次。
_SENTINEL_ATTR = "_ziniao_logging_configured"

_APP_LOGGER_NAMES = (
    "ziniao",
    "ziniao_mcp",
    "ziniao-debug",
    "ziniao-daemon",
    "ziniao-network",
    "ziniao-mcp-debug",
)

_NOISY_LOGGER_NAMES = (
    "nodriver",
    "nodriver.core.connection",
    "websockets",
    "websockets.client",
    "websockets.server",
    "asyncio",
    "urllib3",
    "httpx",
    "httpcore",
)


def _level_from_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip().upper()
    if not raw:
        return default
    return logging.getLevelName(raw) if raw.isalpha() else default


def _int_from_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def configure_logging(role: str = "app") -> logging.Logger:
    """Configure rotating file logging for the current process (idempotent).

    ``role`` 仅影响日志记录的标识字符串（server / daemon / cli），
    handler 只注册一次。

    返回一个通用命名 logger ``ziniao`` 供调用方直接使用。
    """
    root = logging.getLogger()
    if getattr(root, _SENTINEL_ATTR, False):
        return logging.getLogger("ziniao")

    log_path = Path(os.environ.get("ZINIAO_LOG_FILE") or (_STATE_DIR / "mcp_debug.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = _int_from_env("ZINIAO_LOG_MAX_BYTES", 20 * 1024 * 1024)
    backups = _int_from_env("ZINIAO_LOG_BACKUPS", 3)

    handler = RotatingFileHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backups,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter(
            fmt=f"%(asctime)s %(levelname)s [{role}] %(name)s: %(message)s",
        ),
    )
    handler.setLevel(logging.DEBUG)

    root_level = _level_from_env("ZINIAO_LOG_ROOT_LEVEL", logging.WARNING)
    root.setLevel(root_level)
    root.addHandler(handler)

    app_level = _level_from_env("ZINIAO_LOG_LEVEL", logging.INFO)
    for name in _APP_LOGGER_NAMES:
        logging.getLogger(name).setLevel(app_level)

    # nodriver 0.48.1 对 Chrome 147+ 的 CDP schema drift（Cookie.sameParty 等
    # 字段缺失）会在 _listener 里每事件抛 KeyError 并 INFO 级打印完整 cookie
    # dump + traceback，是日志暴涨的直接放大源；直接压到 ERROR。
    for name in _NOISY_LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.ERROR)

    setattr(root, _SENTINEL_ATTR, True)
    return logging.getLogger("ziniao")
