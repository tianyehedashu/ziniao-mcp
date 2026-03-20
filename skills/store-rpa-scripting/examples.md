# RPA 脚本示例

## 示例 1: 批量修改商品价格

场景：从 CSV 读取 SKU 和新价格，逐个在后台修改。

### Phase 1 探索记录（通过 ziniao-mcp 工具完成）

```
# 1. 确认店铺信息
list_stores()
→ 返回: [{"store_id": "store_123", "store_name": "US-Main", ...}]

# 2. 连接目标店铺
connect_store("store_123")
→ 返回: {"status": "connected", "cdp_port": 9222, "tabs": 1}

# 3. 导航到库存管理页面
navigate_page("https://sellercentral.amazon.com/inventory")
→ 返回: {"url": "...", "title": "Manage Inventory", "status": "ok"}

# 4. 等待页面加载完成
wait_for("#myitable-search", timeout=10000)
→ 返回: "元素已出现: #myitable-search"

# 5. 获取页面结构
take_snapshot()
→ 返回: 页面 DOM 结构，发现搜索框 #myitable-search、表格 .mt-table

# 6. 尝试搜索
fill("#myitable-search", "SKU001")
→ 返回: "已填写 1 个字段"
press_key("Enter")
wait_for(".mt-link", timeout=10000)
→ 返回: 搜索结果出现

# 7. 点击编辑
click(".mt-link")
wait_for("#price-input", timeout=15000)
take_snapshot()
→ 返回: 编辑页表单结构，找到 #price-input、#save-btn

# 8. 修改价格并保存
fill("#price-input", "29.99")
take_screenshot()  → 截图确认填写内容
click("#save-btn")
wait_for(".success-message", timeout=15000)
→ 返回: 成功提示出现

# 9. 异常场景探索
# - 搜索不存在的 SKU → 无 .mt-link，需要检测 .no-results
# - 价格格式错误 → .error-message 出现
# - 保存超时 → 15s 后仍无 .success-message
```

### Phase 2 确认步骤

```markdown
## RPA 流程: 批量修改商品价格

### 前置条件
- 紫鸟账号: company=my_company, username=admin
- 客户端路径: D:\ziniao\ziniao.exe
- 目标店铺: store_123 (US-Main)
- 输入数据: prices.csv (列: sku, new_price)

### 操作步骤
| # | 操作 | 选择器/参数 | 等待条件 | 预期结果 |
|---|------|------------|----------|----------|
| 1 | 导航 | URL: .../inventory | `#myitable-search` 出现 | 库存页加载完成 |
| 2 | 搜索 | `#myitable-search` = SKU | `.mt-link` 出现 | 搜索结果显示 |
| 3 | 点击编辑 | `.mt-link` | `#price-input` 出现 | 进入编辑页 |
| 4 | 填写价格 | `#price-input` = 新价格 | — | 价格已填入 |
| 5 | 截图存证 | — | — | 截图保存 |
| 6 | 保存 | `#save-btn` | `.success-message` 出现 | 保存成功 |
| 7 | 返回列表 | 导航回 inventory | `#myitable-search` 出现 | 处理下一条 |

### 异常处理
| 异常 | 检测方式 | 处理策略 |
|------|----------|----------|
| SKU 不存在 | `.no-results` 出现 | 记录跳过 |
| 价格格式错误 | `.error-message` 出现 | 记录错误 |
| 保存超时 | 15s 无 `.success-message` | 重试 1 次 |
```

### Phase 3 生成脚本

```python
"""
RPA: 批量修改商品价格
用途: 从 CSV 读取 SKU 和新价格，在亚马逊后台逐个修改
依赖: pip install nodriver ziniao
输入: prices.csv (列: sku, new_price)
"""

import asyncio
import csv
import logging

import nodriver
from ziniao_webdriver import ZiniaoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZINIAO_CONFIG = {
    "client_path": r"D:\ziniao\ziniao.exe",
    "socket_port": 16851,
    "user_info": {"company": "my_company", "username": "admin", "password": "pass"},
}
STORE_ID = "store_123"
INVENTORY_URL = "https://sellercentral.amazon.com/inventory"


def load_prices(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def update_price(tab, sku: str, new_price: str):
    """修改单个商品价格。"""
    await tab.get(INVENTORY_URL)
    await tab.sleep(2)

    search_box = await tab.select("#myitable-search", timeout=10)
    if not search_box:
        raise RuntimeError("未找到搜索框")
    await search_box.clear_input()
    await search_box.send_keys(sku)
    await tab.sleep(2)

    edit_link = await tab.select(".mt-link", timeout=10)
    if not edit_link:
        raise RuntimeError(f"未找到 SKU {sku} 的编辑链接")
    await edit_link.click()

    price_input = await tab.select("#price-input", timeout=15)
    if not price_input:
        raise RuntimeError("未找到价格输入框")
    await price_input.clear_input()
    await price_input.send_keys(new_price)

    save_btn = await tab.select("#save-btn", timeout=10)
    if not save_btn:
        raise RuntimeError("未找到保存按钮")
    await save_btn.click()

    success = await tab.select(".success-message", timeout=15)
    if not success:
        logger.warning("SKU %s: 未检测到成功提示", sku)
    else:
        logger.info("SKU %s: 价格已更新为 %s", sku, new_price)


async def run():
    client = ZiniaoClient(**ZINIAO_CONFIG)
    if not client.heartbeat():
        logger.info("启动紫鸟客户端...")
        client.start_browser()

    result = client.open_store(STORE_ID)
    if not result:
        raise RuntimeError(f"打开店铺失败: {STORE_ID}")
    cdp_port = result["debuggingPort"]

    browser = await nodriver.Browser.create(host="127.0.0.1", port=cdp_port)
    tab = browser.main_tab
    tasks = load_prices("prices.csv")

    success_count = 0
    for i, task in enumerate(tasks, 1):
        sku, price = task["sku"], task["new_price"]
        logger.info("[%d/%d] 处理 SKU: %s → %s", i, len(tasks), sku, price)
        try:
            await update_price(tab, sku, price)
            success_count += 1
        except Exception as e:
            logger.error("SKU %s 失败: %s", sku, e)
        await asyncio.sleep(2)

    logger.info("完成: %d/%d 成功", success_count, len(tasks))
    browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
```

### Phase 4 过程文档

脚本生成后同时输出以下文档（`rpa_batch_price_doc.md`）：

```markdown
# 批量修改商品价格 — RPA 自动化过程文档

## 1. 概述
- **目标**: 从 CSV 读取 SKU 和新价格，自动在亚马逊后台逐个修改
- **适用平台**: Amazon Seller Central
- **适用店铺**: store_123 (US-Main)
- **生成日期**: 2026-03-10

## 2. 环境准备

### 2.1 依赖安装
pip install nodriver ziniao

### 2.2 紫鸟客户端
- 客户端路径: `D:\ziniao\ziniao.exe`
- 确保客户端版本支持 WebDriver 模式

### 2.3 账号配置
修改脚本中 `ZINIAO_CONFIG`：
| 字段 | 说明 | 当前值 |
|------|------|--------|
| client_path | 紫鸟客户端路径 | `D:\ziniao\ziniao.exe` |
| company | 企业名 | `my_company` |
| username | 登录用户名 | `admin` |
| password | 登录密码 | `***` |

### 2.4 输入数据
- 文件路径: `prices.csv`
- 格式: CSV，UTF-8 编码
- 列: `sku`（商品 SKU）, `new_price`（新价格，如 29.99）
- 示例:
  ```
  sku,new_price
  SKU001,29.99
  SKU002,15.50
  ```

## 3. 探索记录

### 3.1 页面分析
| 页面 | URL | 关键元素 | 备注 |
|------|-----|----------|------|
| 库存管理 | sellercentral.amazon.com/inventory | `#myitable-search`, `.mt-table`, `.mt-link` | 主操作页 |
| 商品编辑 | 动态 URL | `#price-input`, `#save-btn`, `.success-message` | 编辑表单 |

### 3.2 操作流程验证
1. `list_stores()` → 确认 store_123 存在，名称 US-Main
2. `connect_store("store_123")` → CDP 端口 9222，1 个标签页
3. `navigate_page(inventory_url)` → 页面标题 "Manage Inventory"
4. `take_snapshot()` → 发现搜索框 `#myitable-search`
5. `fill("#myitable-search", "SKU001")` + `press_key("Enter")` → 搜索结果出现
6. `click(".mt-link")` → 进入编辑页，发现 `#price-input`
7. `fill("#price-input", "29.99")` + `click("#save-btn")` → `.success-message` 出现
8. 异常测试：搜索不存在 SKU → `.no-results` 出现；价格格式错误 → `.error-message`

### 3.3 选择器稳定性
| 选择器 | 类型 | 稳定性 | 备注 |
|--------|------|--------|------|
| `#myitable-search` | ID | 高 | Amazon 标准组件 |
| `.mt-link` | Class | 中 | 搜索结果中第一个编辑链接 |
| `#price-input` | ID | 高 | 编辑表单标准字段 |
| `#save-btn` | ID | 高 | 保存按钮 |
| `.success-message` | Class | 中 | 保存成功提示 |

## 4. 操作步骤详解
| # | 操作 | 选择器/参数 | 等待条件 | 预期结果 |
|---|------|------------|----------|----------|
| 1 | 导航到库存页 | URL: .../inventory | `#myitable-search` 出现 | 页面加载完成 |
| 2 | 清空搜索框并输入 SKU | `#myitable-search` | — | SKU 已输入 |
| 3 | 按 Enter 搜索 | 键盘 Enter | `.mt-link` 出现 | 搜索结果显示 |
| 4 | 点击编辑链接 | `.mt-link` | `#price-input` 出现 | 进入编辑页 |
| 5 | 清空价格并输入新价格 | `#price-input` | — | 新价格已填入 |
| 6 | 点击保存 | `#save-btn` | `.success-message` 出现 | 保存成功 |
| 7 | 返回库存页处理下一条 | 导航回 inventory | `#myitable-search` 出现 | 循环继续 |

## 5. 脚本使用

### 5.1 运行方式
python rpa_batch_price.py

### 5.2 配置项
| 配置 | 位置 | 说明 |
|------|------|------|
| `ZINIAO_CONFIG` | 脚本顶部 | 紫鸟账号和客户端路径 |
| `STORE_ID` | 脚本顶部 | 目标店铺 ID |
| `INVENTORY_URL` | 脚本顶部 | 库存管理页 URL |
| `prices.csv` | 脚本同目录 | 输入数据文件 |

### 5.3 输出
- 控制台日志: 每条 SKU 的处理进度和结果
- 最终汇总: `完成: X/Y 成功`

## 6. 异常处理
| 异常 | 可能原因 | 解决方式 |
|------|----------|----------|
| 客户端启动失败 | 路径错误/权限不足 | 检查 client_path，以管理员运行 |
| 店铺打开失败 | store_id 错误 | 用 list_stores 确认正确 ID |
| 搜索框未找到 | 页面改版/加载慢 | 增大 timeout，检查选择器 |
| SKU 无结果 | SKU 不存在 | 检查 CSV 数据 |
| 保存超时 | 网络慢 | 增大 timeout 或增加重试 |

## 7. 维护说明
- Amazon 后台改版时需重新探索页面结构，更新选择器
- 定期检查 `.mt-link`、`.success-message` 等 class 选择器是否仍有效
- 紫鸟客户端更新后验证 open_store API 返回格式
```

---

## 示例 2: 提取订单数据

场景：从订单管理页提取近期订单信息，保存为 JSON。

```python
"""
RPA: 提取订单数据
用途: 从店铺后台提取订单列表，保存为 JSON
依赖: pip install nodriver ziniao
"""

import asyncio
import json
import logging
from pathlib import Path

import nodriver
from ziniao_webdriver import ZiniaoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZINIAO_CONFIG = {
    "client_path": r"D:\ziniao\ziniao.exe",
    "socket_port": 16851,
    "user_info": {"company": "my_company", "username": "admin", "password": "pass"},
}
STORE_ID = "store_123"


async def extract_orders(tab) -> list[dict]:
    return await tab.evaluate("""
        Array.from(document.querySelectorAll('.order-row')).map(row => ({
            order_id: row.querySelector('.order-id')?.textContent?.trim(),
            date: row.querySelector('.order-date')?.textContent?.trim(),
            status: row.querySelector('.order-status')?.textContent?.trim(),
            total: row.querySelector('.order-total')?.textContent?.trim(),
        }))
    """)


async def run():
    client = ZiniaoClient(**ZINIAO_CONFIG)
    if not client.heartbeat():
        client.start_browser()

    result = client.open_store(STORE_ID)
    if not result:
        raise RuntimeError(f"打开店铺失败: {STORE_ID}")

    browser = await nodriver.Browser.create(host="127.0.0.1", port=result["debuggingPort"])
    tab = browser.main_tab

    await tab.get("https://sellercentral.amazon.com/orders-v3")
    await tab.sleep(3)

    table = await tab.select(".order-row", timeout=15)
    if not table:
        logger.error("未找到订单数据")
        browser.stop()
        return

    orders = await extract_orders(tab)
    logger.info("提取到 %d 条订单", len(orders))

    output = Path("orders.json")
    output.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存到 %s", output)
    browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 示例 3: 页面状态监控

场景：定时检查页面上的关键指标，变化时发出提醒。

```python
"""
RPA: 页面状态监控
用途: 定时检查页面指标，变化时记录日志
依赖: pip install nodriver ziniao
"""

import asyncio
import logging

import nodriver
from ziniao_webdriver import ZiniaoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZINIAO_CONFIG = {
    "client_path": r"D:\ziniao\ziniao.exe",
    "socket_port": 16851,
    "user_info": {"company": "my_company", "username": "admin", "password": "pass"},
}
STORE_ID = "store_123"
CHECK_INTERVAL = 300
TARGET_URL = "https://seller.example.com/dashboard"


async def get_metric(tab, selector: str) -> str:
    elem = await tab.select(selector, timeout=10)
    if not elem:
        return ""
    return (await tab.evaluate(
        f"document.querySelector('{selector}')?.textContent?.trim()"
    )) or ""


async def run():
    client = ZiniaoClient(**ZINIAO_CONFIG)
    if not client.heartbeat():
        client.start_browser()

    result = client.open_store(STORE_ID)
    if not result:
        raise RuntimeError(f"打开店铺失败: {STORE_ID}")

    browser = await nodriver.Browser.create(host="127.0.0.1", port=result["debuggingPort"])
    tab = browser.main_tab
    await tab.get(TARGET_URL)
    await tab.sleep(3)

    prev_value = None
    while True:
        await tab.evaluate("location.reload()")
        await tab.sleep(5)

        current = await get_metric(tab, ".key-metric-value")
        if prev_value is not None and current != prev_value:
            logger.warning("指标变化: %s → %s", prev_value, current)
        else:
            logger.info("当前指标: %s", current)
        prev_value = current

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 模式总结

| 场景 | 核心模式 | 关键技术 |
|------|----------|----------|
| 批量修改 | CSV 读取 + 循环操作 | `tab.select` + `clear_input` + `send_keys` |
| 数据提取 | JS evaluate 批量获取 | `tab.evaluate` + JSON 序列化 |
| 状态监控 | 定时刷新 + 对比 | `asyncio.sleep` + 循环 |
| 表单填写 | 选择器定位 + 逐字段填写 | `tab.select` + `send_keys` |
| 多页操作 | 分页/翻页循环 | `tab.get` + 页码递增 |
