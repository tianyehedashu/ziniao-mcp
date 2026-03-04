"""集成测试脚本 — 真实连接紫鸟客户端，测试查看/打开/关闭店铺。"""

import logging
import os
import sys
import time
from pathlib import Path

import pytest

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.getLogger("ziniao-webdriver").setLevel(logging.ERROR)

from ziniao_webdriver.client import ZiniaoClient


def _user_info():
    return {
        "company": os.environ.get("ZINIAO_COMPANY"),
        "username": os.environ.get("ZINIAO_USERNAME"),
        "password": os.environ.get("ZINIAO_PASSWORD"),
    }


PORT = int(os.environ.get("ZINIAO_SOCKET_PORT", "16851"))


@pytest.mark.parametrize("version", ["v5", "v6"])
def test_version(version: str):
    env_key = f"ZINIAO_V{version[1:]}_CLIENT_PATH"
    client_path = os.environ.get(env_key, "")
    print(f"\n{'='*50}")
    print(f"  {version.upper()} 集成测试")
    print(f"{'='*50}")
    print(f"客户端路径: {client_path}")
    print(f"文件存在: {os.path.exists(client_path)}")

    if not os.path.exists(client_path):
        print(f"[SKIP] 客户端文件不存在，跳过 {version}")
        return False

    client = ZiniaoClient(client_path, PORT, _user_info(), version=version)

    # 1) 心跳检查，不通则启动
    if not client.heartbeat():
        print("客户端未运行，正在启动...")
        client.start_browser()
        time.sleep(5)
        if not client.heartbeat():
            print("[FAIL] 启动后心跳仍然失败")
            return False

    print("[PASS] heartbeat OK")

    # 2) 查看店铺列表
    print("\n--- 查看店铺列表 ---")
    stores = client.get_browser_list()
    print(f"店铺数量: {len(stores)}")
    if not stores:
        print("[WARN] 无店铺数据，跳过打开/关闭测试")
        return True

    for s in stores[:5]:
        name = s.get("browserName", "?")
        bid = s.get("browserId", "?")
        oauth = s.get("browserOauth", "?")
        print(f"  - {name}  (id={bid}, oauth={oauth})")
    if len(stores) > 5:
        print(f"  ... 还有 {len(stores) - 5} 个店铺")

    print("[PASS] get_browser_list OK")

    # 3) 打开第一个店铺
    first = stores[0]
    store_id = str(first.get("browserId") or first.get("browserOauth", ""))
    store_name = first.get("browserName", store_id)
    print(f"\n--- 打开店铺: {store_name} ---")
    result = client.open_store(store_id)
    if result:
        dp = result.get("debuggingPort")
        print(f"[PASS] 打开成功! debuggingPort={dp}")
    else:
        print("[FAIL] 打开店铺失败")
        return False

    # 4) 关闭店铺
    time.sleep(3)
    oauth = str(first.get("browserOauth") or result.get("browserOauth", ""))
    if oauth:
        print(f"\n--- 关闭店铺: {store_name} ---")
        closed = client.close_store(oauth)
        print(f"[{'PASS' if closed else 'FAIL'}] close_store = {closed}")
    else:
        print("[WARN] 无 browserOauth，跳过关闭")

    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "both"

    if target in ("v5", "both"):
        test_version("v5")
    if target in ("v6", "both"):
        test_version("v6")
