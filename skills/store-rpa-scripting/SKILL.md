---
name: store-rpa-scripting
description: 通过紫鸟 MCP 工具探索店铺页面结构，梳理操作步骤，然后生成可独立运行的 Python RPA 脚本（基于 nodriver + CDP）。当用户提到 RPA、自动化脚本、批量操作、定时任务、店铺运营脚本、自动化流程时触发。
allowed-tools: Bash(ziniao:*), Bash(python:*), ziniao-*
---

# 店铺运营 RPA 脚本生成

## 核心工作流

```
Phase 1: 探索（通过 ziniao-mcp 工具）
  list_stores → connect_store → navigate_page → take_snapshot
  → click/fill/evaluate 逐步验证 → 截图/snapshot 检测结果
  → 异常场景探索 → API 分析
                    ↓
Phase 2: 确认（结构化步骤文档，用户审核）
                    ↓
Phase 3: 生成脚本（独立运行，不依赖 MCP）
  ziniao_webdriver 管理客户端/店铺 + nodriver 操作浏览器
                    ↓
Phase 4: 生成过程文档（完整复现指南）
  环境准备 + 配置说明 + 操作步骤 + 脚本使用 + 故障排查
```

**关键原则**：
- Phase 1 全程使用 ziniao-mcp 工具交互式探索，不需要手动操作浏览器
- Phase 3 生成的脚本**完全独立于 MCP**，直接使用 `ziniao_webdriver` + `nodriver`，可通过 `python script.py` 独立运行

## Phase 1: 探索（全程使用 ziniao-mcp 工具）

目标：通过 MCP 工具实际操作页面，摸清完整流程和所有细节。

### 1.1 打开店铺并定位目标页面

通过 MCP 工具完成店铺连接和页面定位：

```
- [ ] list_stores() 获取所有店铺，记录目标店铺的 ID 和名称
- [ ] connect_store(store_id) 连接目标店铺（未运行会自动打开）
- [ ] navigate_page(url) 导航到目标页面
- [ ] wait_for(关键元素选择器) 确认页面加载完成
- [ ] take_snapshot() 获取初始页面结构
```

多店铺场景额外探索：
- `list_stores` 确认所有目标店铺 ID 和站点信息
- 逐个 `connect_store` 切换到不同店铺，验证流程在各店铺上一致
- 记录不同店铺间的页面差异（语言、布局、URL 格式）

### 1.2 分析页面结构，提取选择器

1. 从 snapshot 中识别目标元素（按钮、输入框、表格、链接等）
2. 选择器优先级：`#id` > `[name="x"]` > `[data-testid="x"]` > `.parent .child`
3. 验证唯一性：`evaluate_script("document.querySelectorAll('选择器').length")`
4. 对动态内容（列表、表格），用 `evaluate_script` 提取结构化数据试探

### 1.3 逐步交互验证

**关键：每一步操作后都要验证结果，不能假设操作成功。**

```
操作流程（每一步都要做）：
1. 执行操作 → click / fill / type_text / press_key
2. 等待响应 → wait_for(结果元素) 或 tab.sleep
3. 验证结果 → take_snapshot 或 take_screenshot 确认状态变化
4. 记录发现 → 选择器、等待条件、预期结果
```

示例探索过程：

```
# 第一步：点击搜索框，输入关键词
click("#search-input")                    → 确认输入框获得焦点
type_text("SKU001")                       → 确认文字已输入
press_key("Enter")                        → 触发搜索

# 第二步：等待搜索结果
wait_for(".result-table", timeout=10000)  → 确认结果表格出现
take_snapshot()                           → 检查结果内容是否正确

# 第三步：点击目标行的编辑按钮
click(".result-row:first-child .edit-btn") → 进入编辑页
wait_for("#edit-form")                     → 确认编辑表单加载
take_snapshot()                            → 获取表单字段结构

# 第四步：修改字段并提交
fill("#price-input", "29.99")              → 填写新价格
take_screenshot()                          → 截图确认填写内容
click("#save-btn")                         → 提交

# 第五步：检测提交结果
wait_for(".success-toast", timeout=10000)  → 等待成功提示出现
take_snapshot()                            → 确认页面状态已更新
```

### 1.4 探索异常场景

正常流程走通后，还需探索以下情况：

| 场景 | 探索方法 |
|------|----------|
| 元素加载慢/不出现 | 增大 `wait_for` timeout，观察最长等待时间 |
| 操作后弹窗确认 | `handle_dialog(action="accept")` 预设策略，再操作 |
| 动态加载/懒加载 | 滚动页面 → `take_snapshot` 检查新内容是否出现 |
| 翻页/分页 | 点击下一页 → `wait_for` 等待内容刷新 → 记录翻页选择器 |
| 操作失败提示 | `take_snapshot` 查找错误消息元素的选择器 |
| 登录过期/跳转 | 检查 `evaluate_script("location.href")` 是否被重定向 |

### 1.5 API 分析（数据提取类 RPA）

```
1. 在页面上手动执行一次目标操作
2. list_network_requests(url_pattern="api") → 找到关键接口
3. get_network_request(id) → 记录 method、URL、headers、payload
4. 评估：直接调 API 更稳定，还是操作页面更合适？
```

## Phase 2: 确认

将探索结果整理为结构化文档，呈现给用户确认。

**输出模板**：

```markdown
## RPA 流程: [任务名称]

### 前置条件
- 紫鸟账号: company=[企业名], username=[用户名]
- 客户端路径: [path]（如 D:\ziniao\ziniao.exe）
- 目标店铺: [store_id] ([store_name])
- 多店铺场景: [列出所有目标 store_id]（如需）
- 输入数据: [CSV/Excel 路径及格式说明]（如需）

### 操作步骤
| # | 操作 | 选择器/参数 | 等待条件 | 预期结果 |
|---|------|------------|----------|----------|
| 1 | 导航 | URL: ... | `.main-content` 出现 | 页面加载完成 |
| 2 | 点击 | `#search-btn` | `#search-input` 获焦 | 搜索框激活 |
| 3 | 输入 | `#search-input` = "SKU" | — | 文字已填入 |
| 4 | 按键 | Enter | `.result-table` 出现 | 搜索结果显示 |
| 5 | 点击 | `.edit-btn` | `#edit-form` 出现 | 进入编辑页 |
| 6 | 填写 | `#price` = "29.99" | — | 价格已更新 |
| 7 | 截图 | — | — | 存证确认 |
| 8 | 提交 | `#save-btn` | `.success-toast` 出现 | 保存成功 |

### 异常处理
| 异常 | 检测方式 | 处理策略 |
|------|----------|----------|
| 元素未找到 | `tab.select` 返回 None | 重试 3 次，间隔 2s |
| 保存失败 | `.error-message` 出现 | 记录错误，跳过当前项 |
| 页面跳转 | URL 不匹配预期 | 重新导航到目标页 |
| 弹窗拦截 | dialog 事件 | 自动 accept |

### 结果校验
- 操作后通过 [选择器/JS] 验证状态确实已变更
- 批量操作结束后输出成功/失败汇总
```

**确认要点**：
- 每步操作是否都有对应的等待条件和预期结果
- 选择器是否稳定（避免动态 class、随机 id）
- 异常处理策略是否覆盖已知场景
- 批量操作是否需要参数化输入

## Phase 3: 生成 Python 脚本

用户确认后，生成基于 nodriver 的独立 Python 脚本。

### 脚本模板

脚本需包含完整生命周期：配置账号 -> 启动客户端 -> 打开店铺 -> 操作 -> 关闭。

```python
"""
RPA: [任务名称]
用途: [简要描述]
依赖: pip install nodriver ziniao-mcp
"""

import asyncio
import logging

import nodriver
from nodriver import cdp
from ziniao_webdriver import ZiniaoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- 紫鸟账号配置（按实际情况修改）---
ZINIAO_CONFIG = {
    "client_path": r"D:\ziniao\ziniao.exe",
    "socket_port": 16851,
    "user_info": {
        "company": "企业名",
        "username": "用户名",
        "password": "密码",
    },
}
STORE_ID = "目标店铺ID"


def create_client() -> ZiniaoClient:
    return ZiniaoClient(**ZINIAO_CONFIG)


def ensure_client_running(client: ZiniaoClient):
    """确保紫鸟客户端在运行。"""
    if client.heartbeat():
        logger.info("紫鸟客户端已在运行")
        return
    logger.info("启动紫鸟客户端...")
    client.start_browser()
    if not client.heartbeat():
        raise RuntimeError("紫鸟客户端启动失败")
    logger.info("紫鸟客户端启动成功")


def open_store(client: ZiniaoClient, store_id: str) -> int:
    """打开店铺并返回 CDP 端口。"""
    result = client.open_store(store_id)
    if not result:
        raise RuntimeError(f"打开店铺失败: {store_id}")
    cdp_port = result.get("debuggingPort")
    if not cdp_port:
        raise RuntimeError("未获取到 CDP 端口")
    logger.info("店铺已打开: %s, CDP 端口: %d", store_id, cdp_port)
    return cdp_port


async def connect_browser(cdp_port: int) -> nodriver.Browser:
    browser = await nodriver.Browser.create(host="127.0.0.1", port=cdp_port)
    logger.info("已连接到 CDP 端口 %d", cdp_port)
    return browser


async def do_task(tab):
    """核心业务逻辑（由 Phase 2 步骤生成）。"""
    # TODO: 实现具体操作步骤
    pass


async def run():
    client = create_client()
    ensure_client_running(client)
    cdp_port = open_store(client, STORE_ID)
    browser = await connect_browser(cdp_port)
    tab = browser.main_tab

    try:
        await do_task(tab)
        logger.info("RPA 任务完成")
    finally:
        browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
```

### 多店铺批量模板

对多个店铺执行相同操作时：

```python
STORE_IDS = ["store_001", "store_002", "store_003"]

async def run():
    client = create_client()
    ensure_client_running(client)
    results = {"success": 0, "failed": 0, "errors": []}

    for i, store_id in enumerate(STORE_IDS, 1):
        logger.info("[%d/%d] 处理店铺: %s", i, len(STORE_IDS), store_id)
        try:
            cdp_port = open_store(client, store_id)
            browser = await connect_browser(cdp_port)
            tab = browser.main_tab
            await do_task(tab)
            browser.stop()
            results["success"] += 1
        except Exception as e:
            logger.error("店铺 %s 失败: %s", store_id, e)
            results["failed"] += 1
            results["errors"].append({"store_id": store_id, "error": str(e)})
        await asyncio.sleep(2)

    logger.info("完成: %d 成功, %d 失败", results["success"], results["failed"])
```

### 代码生成规范

**元素操作（必须检查 None）**：

```python
elem = await tab.select("#btn", timeout=10)
if not elem:
    raise RuntimeError("未找到元素: #btn")
await elem.click()
```

**操作后等待 + 结果校验**：

```python
await elem.click()
result = await tab.select(".success-toast", timeout=10)
if not result:
    error = await tab.select(".error-message", timeout=3)
    if error:
        msg = await tab.evaluate("document.querySelector('.error-message')?.textContent")
        raise RuntimeError(f"操作失败: {msg}")
    raise RuntimeError("操作后未检测到成功或失败提示")
```

**导航后等待关键元素**：

```python
await tab.get("https://example.com/page")
loaded = await tab.select(".main-content", timeout=15)
if not loaded:
    raise RuntimeError("页面加载超时")
```

**数据提取**：

```python
data = await tab.evaluate("""
    Array.from(document.querySelectorAll('table tbody tr')).map(row => ({
        col1: row.cells[0]?.textContent?.trim(),
        col2: row.cells[1]?.textContent?.trim(),
    }))
""")
```

**重试机制**：

```python
async def retry(coro_fn, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == retries - 1:
                raise
            logger.warning("第 %d 次重试: %s", attempt + 1, e)
            await asyncio.sleep(delay)
```

**批量数据参数化（从 CSV 读取）**：

```python
import csv

def load_tasks(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

async def do_task(tab):
    tasks = load_tasks("tasks.csv")
    results = {"success": 0, "failed": 0, "errors": []}
    for i, task in enumerate(tasks, 1):
        logger.info("[%d/%d] 处理: %s", i, len(tasks), task)
        try:
            await process_single(tab, task)
            results["success"] += 1
        except Exception as e:
            logger.error("失败: %s", e)
            results["failed"] += 1
            results["errors"].append({"task": task, "error": str(e)})
        await asyncio.sleep(1)
    logger.info("完成: %d 成功, %d 失败", results["success"], results["failed"])
```

**截图存证**：

```python
import base64
from pathlib import Path

async def save_screenshot(tab, name: str):
    result = await tab.send(cdp.page.capture_screenshot(format_="png"))
    path = Path(f"screenshots/{name}.png")
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(base64.b64decode(result.data))
    logger.info("截图已保存: %s", path)
```

## Phase 4: 生成过程文档

脚本生成后，**同时输出**一份完整的过程文档（Markdown），方便其他人复现整个流程。

文档命名与脚本对应：`rpa_[task_name].py` → `rpa_[task_name]_doc.md`

文档必须包含以下章节：
1. **概述** — 目标、平台、店铺、日期
2. **环境准备** — 依赖安装、客户端路径、账号配置、输入数据格式
3. **探索记录** — Phase 1 中每步 MCP 工具调用和返回结果的完整记录
4. **操作步骤详解** — Phase 2 确认的步骤表格
5. **脚本使用** — 运行方式、配置项说明、输出说明
6. **异常处理** — 常见问题和解决方式
7. **维护说明** — 页面改版、选择器更新、客户端升级注意事项

详细模板见 [doc-template.md](doc-template.md)，完整示例见 [examples.md](examples.md) 中示例 1 的 Phase 4。

**关键要求**：
- 探索记录要包含**实际的 MCP 工具调用和返回结果**，不是泛泛描述
- 文档应足够详细，让不了解项目的人也能按文档独立复现整个流程

## 质量检查

### 脚本
- [ ] 包含紫鸟账号配置（company/username/password/client_path）
- [ ] 有客户端启动检查（heartbeat → start_browser）
- [ ] 有店铺打开逻辑（open_store → 获取 CDP 端口）
- [ ] 可通过 `python script.py` 独立运行，**不依赖 MCP**
- [ ] 多店铺场景有循环切换和独立错误处理
- [ ] 每个 `tab.select()` 都有 `timeout`，返回值都检查了 `None`
- [ ] 每步操作后都有等待条件
- [ ] 关键操作后有结果校验
- [ ] 异常场景有处理（重试/跳过/记录/截图）
- [ ] 敏感操作前有日志或确认
- [ ] 批量操作有进度日志和汇总报告
- [ ] finally 中调用 `browser.stop()` 断开连接

### 过程文档
- [ ] 包含完整的环境准备和配置说明
- [ ] 包含 Phase 1 的探索记录（实际工具调用和返回结果）
- [ ] 包含 Phase 2 的完整步骤表格
- [ ] 包含脚本运行方式和配置项说明
- [ ] 包含异常处理和故障排查指南
- [ ] 不了解项目的人能按文档独立复现

## 补充资源

- 工具速查表：[tools-reference.md](tools-reference.md)
- 完整 RPA 示例：[examples.md](examples.md)
- 过程文档模板：[doc-template.md](doc-template.md)
