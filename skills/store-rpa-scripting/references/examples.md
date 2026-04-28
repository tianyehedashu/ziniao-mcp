# RPA 示例（仅格式与模式）

**说明**：示例中的 URL、选择器、会话 ID 为示意，以各任务在 Phase 1 中的实测为准。

---

## 示例 1：四阶段长什么样

### Phase 1 — CLI 记录（示意）

```
ziniao list-stores
ziniao open-store "<会话ID>"
ziniao navigate "<入口URL>"
ziniao wait "<页面就绪锚点>" --timeout 60
ziniao snapshot --interactive
ziniao click "<动作A选择器>"
ziniao wait "<下一屏锚点>"
ziniao screenshot step-a.png
# … 按任务继续，直到闭环可复现
```

### Phase 2 — 步骤表（示意）

| # | 动作 | 选择器/参数 | 等待条件 | 预期结果 |
|---|------|------------|----------|----------|
| 1 | navigate | `<入口URL>` | `<就绪锚点>` | 可操作 |
| 2 | click | `<A>` | `<B>` | 进入下一状态 |

### Phase 3 — 脚本骨架（与 CLI 语义对齐）

```python
"""RPA: [任务名] — 依赖: pip install ziniao"""

import asyncio
import logging

import nodriver
from ziniao_webdriver import ZiniaoClient, ensure_http_ready, open_store_cdp_port

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZINIAO_CONFIG = { ... }  # 与运行环境一致
SESSION_ID = "<会话ID>"


async def do_task(tab):
    await tab.get("<入口URL>")
    anchor = await tab.select("<就绪锚点>", timeout=60)
    if not anchor:
        raise RuntimeError("页面未就绪")
    el = await tab.select("<A>", timeout=30)
    if not el:
        raise RuntimeError("未找到 <A>")
    await el.click()
    nxt = await tab.select("<B>", timeout=30)
    if not nxt:
        raise RuntimeError("未进入预期状态")


async def run():
    client = ZiniaoClient(**ZINIAO_CONFIG)
    ensure_http_ready(client, update_core_max_retries=30)
    port = open_store_cdp_port(client, SESSION_ID)
    browser = await nodriver.Browser.create(host="127.0.0.1", port=port)
    try:
        await do_task(browser.main_tab)
    finally:
        browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
```

### Phase 4

按 [../assets/doc-template.md](../assets/doc-template.md) 填写；第 3 节粘贴**真实**命令与输出摘要。

---

## 示例 2：列表数据提取（`evaluate` 模式）

Phase 1 用 `ziniao eval 'JSON.stringify(...)'` 试通后，脚本侧：

```python
rows = await tab.evaluate("""
    Array.from(document.querySelectorAll('<行选择器>')).map(row => ({
        c0: row.querySelector('<单元选择器>')?.textContent?.trim(),
    }))
""")
```

写入 `Path("out.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))`。

---

## 示例 3：定时轮询（监控类）

```python
CHECK_INTERVAL = 300
TARGET_URL = "https://example.com/dashboard"

async def run():
    # … 连接浏览器同示例 1 …
    tab = browser.main_tab
    await tab.get(TARGET_URL)
    while True:
        await tab.evaluate("location.reload()")
        await tab.sleep(5)
        v = await tab.evaluate(
            "document.querySelector('.metric')?.textContent?.trim() || ''"
        )
        logger.info("metric=%s", v)
        await asyncio.sleep(CHECK_INTERVAL)
```

---

## 模式总结

| 目标 | 工具链要点 | 脚本要点 |
|------|------------|----------|
| 流程自动化 | `navigate` → `wait` → `snapshot` → 交互命令链 | `get` / `select` / `click` 与之一致 |
| 批量参数 | CLI 验证一条路径；数据用 CSV/JSON | 循环 + 单条 try/except |
| 抓接口 | `network list` / HAR | 评估是否改 HTTP 客户端直连 |
| 多会话 | `ziniao --store` / `--session` 固定每条命令；不用 `session switch` 写步骤表 | `for` + 每次 `open_store` 或等价 |
