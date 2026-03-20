# 开发指南

## 环境准备

### 前置要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 紫鸟浏览器客户端（已开通 WebDriver 权限）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd ziniao

# 安装依赖
uv sync
```

### 验证安装

```bash
# 查看帮助（MCP 入口）
uv run ziniao serve --help

# 启动 MCP 服务器（需要配置好紫鸟账号信息）
uv run ziniao serve --company "xxx" --username "xxx" --password "xxx" --client-path "D:\ziniao\ziniao.exe"
```

## 项目结构

```
ziniao/
├── ziniao_webdriver/        # 紫鸟客户端 HTTP 通信层
│   ├── __init__.py          # 导出 ZiniaoClient
│   └── client.py            # ZiniaoClient 实现
├── ziniao_mcp/              # MCP 服务器
│   ├── __init__.py          # 导出 create_server, main
│   ├── __main__.py          # python -m ziniao_mcp 入口
│   ├── server.py            # 配置解析 + 工具注册 + 启动
│   ├── session.py           # SessionManager + 状态持久化
│   └── tools/               # MCP 工具集（每个文件一个分类）
│       ├── __init__.py
│       ├── store.py         # 店铺管理
│       ├── input.py         # 输入自动化
│       ├── navigation.py    # 导航
│       ├── emulation.py     # 仿真
│       ├── network.py       # 网络
│       └── debug.py         # 调试
├── config/
│   └── config.yaml          # 默认配置（含敏感信息，不提交）
├── docs/                    # 文档
├── pyproject.toml           # 项目元数据与依赖
├── uv.lock                  # 可选依赖锁（当前 .gitignore 默认忽略）
└── .gitignore
```

## 添加新工具

### 1. 在已有分类中添加

以在 `tools/input.py` 中添加 `double_click` 为例：

```python
# ziniao_mcp/tools/input.py

def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    # ... 已有工具 ...

    @mcp.tool()
    async def double_click(selector: str) -> str:
        """双击页面元素。

        Args:
            selector: CSS 选择器
        """
        tab = session.get_active_tab()
        elem = await tab.select(selector, timeout=10)
        if elem:
            await elem.click()
            await elem.click()
        return f"已双击: {selector}"
```

要点：
- 使用 `@mcp.tool()` 装饰器注册
- 函数 docstring 即为工具描述，会展示给 AI Agent
- `Args` 部分描述参数，MCP 框架自动提取
- 返回值为 `string`，复杂数据用 `json.dumps()` 序列化

### 2. 添加新的工具分类

```python
# ziniao_mcp/tools/cookie.py
"""Cookie 管理工具"""

import json
from mcp.server.fastmcp import FastMCP
from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def list_cookies(url: str = "") -> str:
        """列出当前页面的 Cookie。

        Args:
            url: 可选，按 URL 过滤
        """
        from nodriver import cdp
        tab = session.get_active_tab()
        cookies = await tab.send(cdp.storage.get_cookies())
        return json.dumps([c.to_json() for c in cookies], ensure_ascii=False, indent=2)
```

然后在 `server.py` 中注册：

```python
from .tools.cookie import register_tools as register_cookie
register_cookie(mcp, session)
```

### 3. 工具设计原则

- **单一职责**：每个工具只做一件事
- **docstring 即文档**：AI Agent 通过 docstring 理解工具用途，务必写清楚
- **参数类型明确**：使用 Python 类型注解，MCP 框架自动推断 JSON Schema
- **错误信息友好**：返回人类可读的错误消息，而非裸异常
- **JSON 输出**：复杂返回值统一用 `json.dumps()`，便于 Agent 解析

## 调试

### 日志

MCP 服务器的调试日志写入 `~/.ziniao/mcp_debug.log`（DEBUG 级别，可能含 URL 等敏感信息，勿随意外发）：

```bash
# 实时查看日志
Get-Content $env:USERPROFILE\.ziniao\mcp_debug.log -Wait    # PowerShell
tail -f ~/.ziniao/mcp_debug.log                             # Unix
```

### 测试脚本

项目包含几个调试用测试脚本：

| 脚本 | 用途 |
|------|------|
| `test_minimal_env.py` | 在最小环境下启动 MCP 并发送 `initialize` 请求 |
| `test_spawn.py` | 模拟 Cursor 通过子进程启动 MCP 的流程 |
| `debug_mcp.py` | MCP 通信调试包装器，记录 stdin/stdout |

### 状态文件

已打开店铺的 CDP 信息持久化在 `~/.ziniao/sessions.json`。调试时可直接查看或删除：

```bash
# 查看当前状态
type $env:USERPROFILE\.ziniao\sessions.json    # PowerShell
cat ~/.ziniao/sessions.json                     # Unix

# 清理状态（如果连接异常）
del $env:USERPROFILE\.ziniao\sessions.json      # PowerShell
rm ~/.ziniao/sessions.json                      # Unix
```

## 依赖说明

| 依赖 | 用途 | 引用位置 |
|------|------|----------|
| `mcp` | MCP 协议实现与 FastMCP 框架 | `server.py` |
| `nodriver` | 通过 CDP 连接并操作浏览器（反自动化检测优化） | `session.py` |
| `requests` | 与紫鸟客户端 HTTP 通信 | `client.py` |
| `httpx` | 异步检查 CDP 端口连通性 | `session.py` |
| `PyYAML` | 解析 config.yaml | `server.py` |

### 添加新依赖

```bash
uv add <package-name>
```

## 发布

ziniao-browser 有两个发布渠道：**Cursor Plugin Marketplace** 和 **PyPI**。

### 发布前检查清单

```bash
# 1. 确认所有依赖可正常安装
uv sync

# 2. 确认 MCP Server 可启动
uv run ziniao serve --help

# 3. 确认 Plugin manifest 有效
python -c "import json; json.load(open('.cursor-plugin/plugin.json'))"

# 4. 确认所有 Plugin 组件存在
#    - .cursor-plugin/plugin.json  (manifest)
#    - .mcp.json                   (MCP 配置)
#    - skills/*/SKILL.md           (技能文件)
#    - agents/*.md                 (Agent 文件)
#    - commands/*.md               (命令文件)
```

### 发布到 Cursor Plugin Marketplace

Cursor 插件以 Git 仓库形式分发，经 Cursor 团队审核后上架。

**步骤 1：确保仓库结构合规**

```
ziniao-mcp/
├── .cursor-plugin/
│   └── plugin.json          # 必需：插件清单
├── .mcp.json                # MCP 服务器配置
├── skills/                  # SKILL.md 技能文件
├── agents/                  # Agent 配置
├── commands/                # 命令文件
├── ziniao_mcp/              # MCP Server 源码
├── ziniao_webdriver/        # WebDriver 客户端
├── pyproject.toml
└── README.md
```

**步骤 2：检查 plugin.json**

```json
{
  "name": "ziniao-browser",
  "version": "0.1.0",
  "description": "紫鸟浏览器 AI 自动化工具集 — 跨境电商多店铺浏览器管理、自动化操作与调试",
  "author": { "name": "ziniao" },
  "homepage": "https://open.ziniao.com",
  "license": "MIT",
  "keywords": ["ziniao", "browser", "e-commerce", "automation", "cdp", "cross-border"]
}
```

确保：
- `name` 全小写 kebab-case
- `description` 清晰说明插件用途
- 所有 rules/skills/agents/commands 包含完整的 YAML frontmatter
- README.md 说明了用法和配置项

**步骤 3：推送到公开 Git 仓库**

```bash
git add .
git commit -m "release: v0.2.0 — Cursor Plugin 封装"
git push origin main
```

**步骤 4：提交审核**

前往 [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish) 提交仓库链接。Cursor 团队会审核后发布到 [Marketplace](https://cursor.com/marketplace)。

### 发布到 PyPI

PyPI 包名为 **`ziniao`**。用户可通过 `uvx ziniao serve` 或 `pip install ziniao` 后执行 `ziniao serve` / `ziniao-mcp` 使用 MCP Server（不含 Plugin 组件）。`ziniao-mcp` 为控制台别名，与 `python -m ziniao_mcp` 等价。

#### 前提：注册 PyPI 账号并配置 API Token

1. 在 [pypi.org/account/register](https://pypi.org/account/register/) 注册账号
2. 登录后进入 [pypi.org/manage/account/#api-tokens](https://pypi.org/manage/account/#api-tokens)，创建 API Token（Scope 选 "Entire account" 或指定项目）
3. 配置 token 供 `uv publish` 使用（任选一种）：

```bash
# 方式 A：环境变量（推荐用于 CI）
$env:UV_PUBLISH_TOKEN = "pypi-xxxxxxxx"

# 方式 B：写入 ~/.pypirc（本地开发推荐）
# 创建或编辑 ~/.pypirc 文件：
```

```ini
[pypi]
username = __token__
password = pypi-xxxxxxxx
```

> 如需先在 TestPyPI 验证，同样在 [test.pypi.org](https://test.pypi.org/account/register/) 注册并获取 token。

#### 发布步骤

**步骤 1：更新版本号**

同步更新以下位置的版本号：

| 文件 | 字段 |
|------|------|
| `pyproject.toml` | `version` |
| `.cursor-plugin/plugin.json` | `version` |
| `CHANGELOG.md` | 新增版本条目 |

**步骤 2：构建**

```bash
uv build
```

构建产物在 `dist/` 目录下：

```
dist/
├── ziniao-0.2.0-py3-none-any.whl
└── ziniao-0.2.0.tar.gz
```

**步骤 3：发布**

```bash
# 发布到 PyPI
uv publish

# 或先发布到 TestPyPI 验证
uv publish --publish-url https://test.pypi.org/legacy/
```

**步骤 4：验证**

```bash
# 通过 uvx 免安装运行 MCP
uvx ziniao serve --help

# 或通过 pip 安装
pip install ziniao
ziniao serve --help
# 或（兼容入口）ziniao-mcp --help
```

#### 通过 GitHub Actions 自动发布

仓库已配置 `.github/workflows/publish-pypi.yml`：**推送版本标签时自动构建并发布到 PyPI**。

**一次性配置**（仅需一次）：

1. 打开 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. Name 填 `PYPI_API_TOKEN`，Value 填 PyPI 的 API Token（`pypi-` 开头）
4. 保存

**发布新版本流程**：

1. 在本地更新版本号：修改 `pyproject.toml` 的 `version`（及可选 `.cursor-plugin/plugin.json`、`CHANGELOG.md`）
2. 提交并推送到 `main`：
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to 0.1.1"
   git push origin main
   ```
3. 创建并推送**与版本号一致**的标签（标签必须为 `v` + 版本号，如 `v0.1.1`）：
   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```
4. 打开仓库 **Actions** 页，查看 “Publish to PyPI” 工作流是否运行成功；成功后即可在 PyPI 看到新版本。

> 标签格式必须为 `v*`（如 `v0.1.0`、`v0.1.1`），且 `pyproject.toml` 中的 `version` 需与标签一致（去掉前缀 `v`）。

发布后，用户的 MCP 配置可简化为：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "uvx",
      "args": ["ziniao", "serve"],
      "env": {
        "ZINIAO_COMPANY": "我的公司",
        "ZINIAO_USERNAME": "admin",
        "ZINIAO_PASSWORD": "xxx",
        "ZINIAO_CLIENT_PATH": "D:\\ziniao\\ziniao.exe"
      }
    }
  }
}
```

### MCP 安装深度链接

发布到 Cursor Marketplace 后，可以生成一键安装链接供用户使用：

```
cursor://anysphere.cursor-deeplink/mcp/install?name=ziniao&config=<BASE64_ENCODED_CONFIG>
```

其中 `config` 是 MCP 配置 JSON 的 Base64 编码。生成方式：

```python
import base64, json

config = {
    "command": "uvx",
    "args": ["ziniao", "serve"],
    "env": {
        "ZINIAO_COMPANY": "${ZINIAO_COMPANY}",
        "ZINIAO_USERNAME": "${ZINIAO_USERNAME}",
        "ZINIAO_PASSWORD": "${ZINIAO_PASSWORD}",
        "ZINIAO_CLIENT_PATH": "${ZINIAO_CLIENT_PATH}"
    }
}

encoded = base64.b64encode(json.dumps(config).encode()).decode()
print(f"cursor://anysphere.cursor-deeplink/mcp/install?name=ziniao&config={encoded}")
```
