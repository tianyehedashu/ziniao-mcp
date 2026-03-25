#!/usr/bin/env python3
"""
最小示例：启动紫鸟 WebDriver 客户端 → 打开店铺 → nodriver 连接 CDP。

与本仓库一致：
  ziniao_webdriver.ZiniaoClient.start_browser / update_core / open_store
  （等价于 CLI「ziniao store start-client」+「ziniao open-store」的核心 HTTP 流程）

运行前设置环境变量（或与 ~/.ziniao/.env 一致）：
  ZINIAO_CLIENT_PATH   紫鸟可执行文件路径
  ZINIAO_SOCKET_PORT   HTTP 端口（默认 16851）
  ZINIAO_COMPANY, ZINIAO_USERNAME, ZINIAO_PASSWORD

用法（在 ziniao 仓库根目录）：
  uv run python skills/store-rpa-scripting/scripts/minimal_store_cdp.py <店铺ID>
"""

from __future__ import annotations

import asyncio
import os
import sys

import nodriver
from ziniao_webdriver import ZiniaoClient, ensure_http_ready, open_store_cdp_port


def _client_from_env() -> ZiniaoClient:
    path = os.environ.get("ZINIAO_CLIENT_PATH", "").strip()
    port = int(os.environ.get("ZINIAO_SOCKET_PORT", "16851"))
    company = os.environ.get("ZINIAO_COMPANY", "").strip()
    username = os.environ.get("ZINIAO_USERNAME", "").strip()
    password = os.environ.get("ZINIAO_PASSWORD", "").strip()
    if not path or not company or not username:
        raise SystemExit(
            "请设置 ZINIAO_CLIENT_PATH, ZINIAO_COMPANY, ZINIAO_USERNAME（及 ZINIAO_PASSWORD 如需）"
        )
    return ZiniaoClient(
        client_path=path,
        socket_port=port,
        user_info={
            "company": company,
            "username": username,
            "password": password,
        },
        version="v6",
    )


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("用法: minimal_store_cdp.py <店铺ID>")
    store_id = sys.argv[1]

    client = _client_from_env()
    ensure_http_ready(client, update_core_max_retries=30)
    cdp_port = open_store_cdp_port(client, store_id)

    browser = await nodriver.Browser.create(host="127.0.0.1", port=cdp_port)
    try:
        tab = browser.main_tab
        url = await tab.evaluate("location.href", return_by_value=True)
        print("CDP 已连接, port=", cdp_port, "url=", url)
    finally:
        browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
