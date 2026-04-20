[根 CLAUDE](../CLAUDE.md) » **scripts**

## 职责

**开发调试脚本**：不随 PyPI wheel 发布；用于 MCP 管道调试、协议 smoke、预设冒烟等。详细说明见同目录 [README.md](README.md)。

## 常见脚本

| 脚本 | 用途 |
|------|------|
| `debug_mcp.py` | Cursor 与 `ziniao serve` 之间的 stdin/stdout 代理与日志 |
| `test_spawn.py` | 子进程启动 MCP 并发送 `initialize` 请求 |
| `rakuten_presets_smoke.py` | 乐天 preset 冒烟（见 `docs/rakuten-presets-smoke-test.md`） |
| `cli_test_all.py` | CLI 批量探测类工具 |

## 运行约定

在项目根使用 `uv run python scripts/<name>.py`（Windows 路径见 `scripts/README.md` 示例）。

**回归测试**：`run_tests.ps1`（Windows）与 `run_tests.sh`（POSIX）在仓库根执行 `uv sync` + `pytest`；Windows 细节见 [docs/dev-environment-windows.md](../docs/dev-environment-windows.md)。
