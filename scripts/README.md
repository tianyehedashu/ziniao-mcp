# 开发调试脚本

本目录存放本地开发与调试用脚本，不随包发布。运行前请在本项目根目录下使用 `uv` 环境。

## 脚本说明

### debug_mcp.py

MCP 通信调试代理：在 Cursor 与 `ziniao serve`（或 `python -m ziniao_mcp`）之间做管道转发，并把所有 stdin/stdout 写入 `scripts/mcp_debug.log`，便于排查 Cursor-MCP 协议交互问题。

**使用方式**

1. 在 Cursor 的 MCP 配置中，将服务器启动命令改为执行本脚本，例如：
   - `uv run --directory /path/to/ziniao python scripts/debug_mcp.py`
   - 或在 Windows 上：`uv run --directory E:\project\ziniao python scripts\debug_mcp.py`
2. 紫鸟相关配置通过环境变量传入，不要在本脚本内写死密码等敏感信息。可设置：
   - `ZINIAO_COMPANY`、`ZINIAO_USERNAME`、`ZINIAO_PASSWORD`
   - `ZINIAO_CLIENT_PATH`、`ZINIAO_VERSION`
3. 查看 `scripts/mcp_debug.log` 分析通信内容。

**依赖**

- 需已安装 `uv`，或设置环境变量 `UV_PATH` 指向 uv 可执行文件。
- 项目根目录由脚本根据自身路径自动推导，无需配置。

---

### e2e_cookie_vault_isolated_restore.py

**CookieVault 隔离 profile E2E**：在**已登录**的源 Chrome 会话里导出 AuthSnapshot → 用**全新** ``--user-data-dir`` 启动第二个 Chrome → 在新会话里 ``cookie-vault restore`` → 截图。用于验证「快照能否在干净浏览器里复现登录态」（对话里抖音创作者中心实测流程的脚本化版本）。

**使用方式**（项目根）：

```bash
uv run python scripts/e2e_cookie_vault_isolated_restore.py --source-session chrome-51157
```

仅复用已有快照、跳过 export：

```bash
uv run python scripts/e2e_cookie_vault_isolated_restore.py --source-session chrome-51157 --skip-export --snapshot exports/my.json
```

**注意**

- 默认快照与截图落在 ``exports/``（已在 ``.gitignore`` 忽略）；**含账号 Cookie / storage，勿提交 git**。
- 依赖本机 ziniao daemon；源会话需已在 ``--export-url``（默认 ``https://creator.douyin.com/``）完成登录。

---

### test_spawn.py

模拟 Cursor 通过 subprocess 启动 MCP 服务器的流程：用管道启动 `ziniao serve`，发送一次 `initialize` JSON-RPC 请求，并打印 stdout 响应，用于验证进程与协议是否正常。

**使用方式**

在项目根目录执行：

```bash
uv run python scripts/test_spawn.py
```

或直接：

```bash
python scripts/test_spawn.py
```

（需保证当前环境能正确找到 `ziniao`，建议用 `uv run`。）

**依赖**

- 需已安装 `uv`，或设置 `UV_PATH`。
- 项目根目录自动推导；环境变量 `ZINIAO_*` 未设置时会使用脚本内默认测试值（仅用于连通性测试）。

---

### test_minimal_env.py

在「最小环境」下测试 MCP 服务启动（模拟 Cursor 仅传入 mcp.json 中配置的环境变量）：仅设置 `ZINIAO_*` 与 `SYSTEMROOT`，用管道启动 `ziniao serve`，发送 `initialize` 请求并打印响应，用于验证在类 Cursor 环境下是否能正常跑通。

**使用方式**

在项目根目录执行：

```bash
uv run python scripts/test_minimal_env.py
```

**依赖**

- 需已安装 `uv`，或设置环境变量 `UV_PATH` 指向 uv 可执行文件。
- 项目根目录由脚本根据自身路径自动推导。

---

### e2e_cookie_vault_isolated_restore.py

**CookieVault 隔离 profile E2E**：在**已登录**的源 Chrome 会话里导出 AuthSnapshot → 用**全新** ``--user-data-dir`` 启动第二个 Chrome → 在新会话里 ``cookie-vault restore`` → 截图。用于验证「快照能否在干净浏览器里复现登录态」（抖音创作者中心等场景的手测脚本化版本）。

**使用方式**（项目根）：

```bash
uv run python scripts/e2e_cookie_vault_isolated_restore.py --source-session chrome-51157
```

仅复用已有快照、跳过 export：

```bash
uv run python scripts/e2e_cookie_vault_isolated_restore.py --source-session chrome-51157 --skip-export --snapshot exports/my.json
```

**注意**

- 默认快照与截图落在 ``exports/``（已在 ``.gitignore`` 忽略）；**含账号 Cookie / storage，勿提交 git**。
- 依赖本机 ziniao daemon；源会话需已在 ``--export-url``（默认 ``https://creator.douyin.com/``）完成登录。
