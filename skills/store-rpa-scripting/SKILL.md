---
name: store-rpa-scripting
description: 用 ziniao CLI 完成页面与流程调研，确认步骤后生成可独立运行的 Python 自动化脚本（ziniao_webdriver + nodriver + CDP）。适用于 RPA、批量流程、定时任务、运营自动化、浏览器自动化落地。
allowed-tools: Bash(ziniao:*), Bash(python:*)
---

# 工具驱动的 RPA 落地流程

本 skill 约定四阶段工作法：CLI 调研与验证 → 结构化确认 → 独立脚本实现 → 交付文档。URL、选择器、会话标识等以 Phase 1 命令输出与任务输入为准，与定稿步骤表保持一致。

## 核心工作流

```
Phase 1 调研（终端 ziniao，工具调用闭环）
  接入会话 → navigate → wait → snapshot（--interactive）→ get/eval
  → 交互命令逐步验证 → screenshot 佐证 → 异常路径 → network / HAR（如需）
                    ↓
Phase 2 确认（结构化步骤表，用户或任务方审核）
                    ↓
Phase 3 实现（独立 Python，不依赖 CLI 守护进程）
  浏览器接入（ZiniaoClient + open_store 或等价）+ nodriver/CDP
                    ↓
Phase 4 交付文档（可复现：命令记录 + 步骤表 + 运行方式 + 排障）
```

**接入会话**（按任务环境选一，细节查 **ziniao-cli** skill）：紫鸟店铺 `open-store` / 纯 Chrome `launch` / 已有进程 `connect`。

## Agent 执行要点

1. **工具优先**：先给出可执行的 `ziniao` 命令或可映射的脚本动作；结构用 `snapshot`、`get count`、`eval`、`network list` 等确认后再进入下一步交互。
2. **调研再实现**：Phase 2 定稿与 Phase 3 实现只纳入已在页面上用命令验证过的选择器与操作顺序。
3. **语义对齐**：Phase 3 的 `tab.get` / `tab.select` / `evaluate` 与 Phase 1 的 `navigate` / `wait` / `eval` 一一对应，仅替换为进程内 CDP 调用。
4. **一致性**：Phase 2 表格、脚本常量与 Phase 1 终端记录对齐；未定稿前用 `[入口URL]`、`[会话标识]`、`[选择器]` 等占位，定稿后替换为实测值。

## 默认环境（已配置）

- CLI 在 PATH；配置已通过 `ziniao config show` 或等价方式就绪。
- 守护进程与日志：`~/.ziniao/daemon.log`；异常时 `ziniao quit` 重试。
- 命令全集、flag、`--json` 用法以 **ziniao-cli** skill / `references/commands.md` 为准。

## Phase 1：调研（终端）

目标：得到**可复现的命令序列** + **经工具验证的选择器与等待条件**。

### Snapshot 与选择器

- `snapshot --interactive` 的 **`ref`（`@e0`…）不是选择器**；只用 **Selector** 列或手写稳定选择器。
- 导航或 DOM 大变后：**wait → 再 snapshot**。

### 1.1 接入并打开入口

```bash
# 紫鸟店铺示例（会话标识以任务为准）
ziniao list-stores
ziniao open-store "<会话标识>"
# 或：ziniao launch --url "<入口URL>"  /  ziniao connect <port>

ziniao navigate "<入口URL>"
ziniao wait "<就绪选择器>"
ziniao snapshot --interactive
```

多会话：用 `ziniao --store "<id>" <子命令>` 或脚本内循环；**各会话差异只记录任务给定的事实**，不扩展业务解读。

### 1.2 结构与唯一性

- 选择器优先级：`#id` > `[name]` > `[data-testid]` > 稳定 class。
- `ziniao get count "<sel>"` 或 `ziniao eval 'document.querySelectorAll(...).length'` 验证数量。
- 结构化数据：`ziniao eval 'JSON.stringify(...)'`（注意 shell 引号）。

### 1.3 逐步验证（模式，非业务示例）

每步：**操作 → wait → snapshot 或 screenshot → 记录命令与现象**。

```bash
ziniao wait "<依赖元素>"
ziniao click "<sel>"
ziniao fill "<sel>" "<值>"
ziniao wait "<下一屏锚点>" --timeout 60
ziniao screenshot step.png
```

### 命令串联

```bash
ziniao navigate "<url>" && ziniao wait "<sel>" && ziniao screenshot done.png
```

### 1.4 异常与网络

| 场景 | 工具向思路 |
|------|------------|
| 慢加载 | `--timeout` / `wait` 加大 |
| JS 弹窗 | `ziniao act dialog accept` / `dismiss` |
| 懒加载 | `scroll` / `scrollinto` 后再 snapshot |
| 接口调研 | `network list`、`har-start` / `har-stop` |

## Phase 2：确认（输出给用户/任务方）

用步骤表冻结流程；URL、选择器、参数与 Phase 1 记录一致。

```markdown
## 自动化流程: [任务名]

### 前置条件
- CLI / 配置：`ziniao config show`（或当前环境等价说明）
- 会话：[open-store | launch | connect] + [会话标识或说明]
- 入口：[入口URL]
- 外部输入：[数据文件/参数，无则写「无」]

### 操作步骤
| # | 动作 | 选择器/参数 | 等待条件 | 预期结果 |
|---|------|------------|----------|----------|
| 1 | navigate | URL | 锚点出现 | 就绪 |
| … | … | … | … | … |

### 异常与策略
| 异常 | 检测 | 处理 |
|------|------|------|
| 元素缺失 | select None | 重试/跳过/记录 |
| 业务错误提示 | 错误锚点 | 记录并中止或分支 |

### 结果校验
- 用 [选择器/JS] 断言最终状态；批量任务输出汇总。
```

## Phase 3：实现（独立 Python）

在 Phase 2 定稿后生成脚本：**不** `subprocess` 调 `ziniao`；用 `ZiniaoClient` + `nodriver` 直连 CDP（与 Phase 1 语义一致）。

### 生命周期模板

```python
"""RPA: [任务名] — 依赖: pip install nodriver ziniao"""

import asyncio
import logging

import nodriver
from nodriver import cdp
from ziniao_webdriver import ZiniaoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZINIAO_CONFIG = { ... }  # 与运行环境一致
SESSION_ID = "<会话标识>"  # 任务给定


def create_client() -> ZiniaoClient:
    return ZiniaoClient(**ZINIAO_CONFIG)


def ensure_client_running(client: ZiniaoClient) -> None:
    if client.heartbeat():
        return
    client.start_browser()
    if not client.heartbeat():
        raise RuntimeError("客户端未就绪")


def open_session(client: ZiniaoClient, session_id: str) -> int:
    result = client.open_store(session_id)
    if not result or not result.get("debuggingPort"):
        raise RuntimeError("无法取得 CDP 端口")
    return int(result["debuggingPort"])


async def connect_browser(port: int) -> nodriver.Browser:
    return await nodriver.Browser.create(host="127.0.0.1", port=port)


async def do_task(tab):
    """由 Phase 2 步骤生成。"""
    raise NotImplementedError


async def run():
    client = create_client()
    ensure_client_running(client)
    port = open_session(client, SESSION_ID)
    browser = await connect_browser(port)
    tab = browser.main_tab
    try:
        await do_task(tab)
    finally:
        browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
```

**多会话循环**：与 Phase 1 的 `--store` 批量同构——`for id in ids: open → browser → do_task → stop`，单会话失败不拖死全集（记录 errors）。

### 代码规范（与 CLI 映射）

- `tab.select(sel, timeout=秒)` 对应 `ziniao wait`；返回值必须判 `None`。
- `tab.get(url)` 对应 `navigate`；`tab.evaluate` 对应 `eval`。
- 截图：`cdp.page.capture_screenshot`；重试、CSV、批量汇总按需从 Phase 2 生成。

（重试、CSV 循环、截图等模式见 [examples.md](examples.md)。）

## Phase 4：交付文档

`rpa_[task].py` 配套 `rpa_[task]_doc.md`：

1. 概述（目标一句话 + 日期）  
2. 环境（CLI + 脚本依赖）  
3. **探索记录**：Phase 1 的 `ziniao` 命令与输出摘要  
4. Phase 2 步骤表（复制）  
5. 运行方式与配置项  
6. 异常与排障  
7. 维护（选择器/客户端变更注意点）  

模板：[doc-template.md](doc-template.md)。

## 质量检查

### 工具链（Phase 1）

- [ ] 会话接入 → navigate → wait → snapshot 形成闭环  
- [ ] 选择器经 snapshot/get count/eval 之一验证；未使用 `@eN` 作为 CSS  
- [ ] 关键转折有 screenshot 或 snapshot 佐证  
- [ ] 需要抓包时已用 network / HAR  

### 实现（Phase 3）

- [ ] 客户端 heartbeat / 启动与 CDP 连接完整  
- [ ] 可脱离 CLI 守护进程单独 `python` 运行  
- [ ] `select` 带 timeout；`finally` 中断开 browser  

### 文档（Phase 4）

- [ ] 探索记录与 Phase 1 终端命令及输出一致  

## 补充资源

- [tools-reference.md](tools-reference.md) — CLI ↔ Python 对照  
- [doc-template.md](doc-template.md)  
- [examples.md](examples.md) — 格式与代码模式参考  
- 命令全集：**ziniao-cli** skill → `references/commands.md`
