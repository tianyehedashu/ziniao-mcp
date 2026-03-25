"""CDP Tab 过滤工具 — 纯 duck-typing，无 MCP 依赖。

仅依赖 tab 对象上 ``target.url`` 属性的存在性（nodriver.Tab 满足此协议）。
"""

from __future__ import annotations

_INTERNAL_URL_PREFIXES = ("chrome-extension://", "devtools://", "chrome://")


def is_regular_tab(tab: object) -> bool:
    """判断 tab 是否为普通网页（过滤掉扩展 offscreen、devtools 等内部页面）。"""
    url = getattr(getattr(tab, "target", None), "url", "") or ""
    return not any(url.startswith(p) for p in _INTERNAL_URL_PREFIXES)


def filter_tabs(tabs: list) -> list:
    """从 browser.tabs 中过滤出普通网页标签。"""
    return [t for t in tabs if is_regular_tab(t)]
