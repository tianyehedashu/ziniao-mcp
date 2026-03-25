"""
紫鸟客户端通信模块

封装与紫鸟客户端的 HTTP 通信，支持启动客户端、打开/关闭店铺、获取 CDP 调试端口。
参考: https://open.ziniao.com/docSupport?docId=98
"""

from .cdp_tabs import filter_tabs, is_regular_tab
from .client import ZiniaoClient, detect_ziniao_port
from .lifecycle import ensure_http_ready, open_store_cdp_port

__all__ = [
    "ZiniaoClient",
    "detect_ziniao_port",
    "ensure_http_ready",
    "filter_tabs",
    "is_regular_tab",
    "open_store_cdp_port",
]
