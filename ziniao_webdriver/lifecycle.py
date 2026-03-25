"""紫鸟客户端生命周期 — 纯同步 helper。

提供 ``ensure_http_ready`` 和 ``open_store_cdp_port``，封装
``heartbeat → start_browser → update_core → heartbeat`` 与
``open_store → debuggingPort`` 的重复逻辑。

面向独立 RPA 脚本与 skill 模板。SessionManager 有自身的异步冷启动
路径（含端口探测与错误文案），不直接调用本模块。
"""

from __future__ import annotations

import logging

from .client import ZiniaoClient

_logger = logging.getLogger("ziniao-webdriver")


def ensure_http_ready(
    client: ZiniaoClient,
    *,
    update_core_max_retries: int = 30,
) -> None:
    """确保紫鸟客户端 HTTP 口可用（WebDriver 模式）。

    若 ``heartbeat()`` 已通则立即返回；否则依次
    ``start_browser()`` → ``update_core(max_retries)`` → ``heartbeat()``。

    :param client: 已初始化的 ZiniaoClient 实例
    :param update_core_max_retries: ``update_core`` 最大重试次数
        （SessionManager._do_ensure_client 传 15，_do_start_client 传 30）
    :raises RuntimeError: 启动后仍无法连接
    :raises FileNotFoundError: client_path 未配置或不存在
    """
    if client.heartbeat():
        return
    client.start_browser()
    client.update_core(update_core_max_retries)
    if not client.heartbeat():
        raise RuntimeError(
            f"紫鸟客户端启动后仍无法连接 (端口 {client.socket_port})。"
            "请检查 ZINIAO_SOCKET_PORT 是否与客户端实际监听端口一致。"
        )


def open_store_cdp_port(
    client: ZiniaoClient,
    store_id: str,
    *,
    js_info: str = "",
) -> int:
    """打开店铺并返回 CDP 调试端口号。

    :param store_id: browserId 或 browserOauth
    :param js_info: 可选的注入 JS（如 STEALTH_JS_MINIMAL）
    :return: debuggingPort（int）
    :raises RuntimeError: 打开失败或响应中缺少 debuggingPort
    """
    result = client.open_store(store_id, js_info=js_info)
    if not result:
        raise RuntimeError(f"打开店铺失败: {store_id}")
    port = result.get("debuggingPort")
    if not port:
        raise RuntimeError(f"店铺 {store_id} 响应中无 debuggingPort")
    return int(port)
