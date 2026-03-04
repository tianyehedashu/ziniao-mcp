"""紫鸟浏览器 MCP 服务器 - 让 AI Agent 操控紫鸟店铺"""

from .server import create_server, main

__all__ = ["create_server", "main"]

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    __version__ = "0.0.0.dev"
else:
    try:
        __version__ = version("ziniao-mcp")
    except PackageNotFoundError:
        __version__ = "0.0.0.dev"
