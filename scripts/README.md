# 开发调试脚本

本目录存放本地开发与调试用脚本，不随包发布。运行前请在本项目根目录下使用 `uv` 环境。

## 脚本说明

### debug_mcp.py

MCP 通信调试代理：在 Cursor 与 `ziniao-mcp` 之间做管道转发，并把所有 stdin/stdout 写入 `scripts/mcp_debug.log`，便于排查 Cursor-MCP 协议交互问题。

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

### test_spawn.py

模拟 Cursor 通过 subprocess 启动 MCP 服务器的流程：用管道启动 `ziniao-mcp`，发送一次 `initialize` JSON-RPC 请求，并打印 stdout 响应，用于验证进程与协议是否正常。

**使用方式**

在项目根目录执行：

```bash
uv run python scripts/test_spawn.py
```

或直接：

```bash
python scripts/test_spawn.py
```

（需保证当前环境能正确找到 `ziniao-mcp`，建议用 `uv run`。）

**依赖**

- 需已安装 `uv`，或设置 `UV_PATH`。
- 项目根目录自动推导；环境变量 `ZINIAO_*` 未设置时会使用脚本内默认测试值（仅用于连通性测试）。
