# Windows 本地开发环境（uv / pytest）

在 **Windows** 上，`uv sync` 偶发「拒绝访问」、无法覆盖 `Scripts\ruff.exe`、或 `%TEMP%` 下 pytest 清理失败。这些通常不是 uv / 本仓库的 bug，而是本机 IDE / 杀毒 / 语言服务**持有 venv 里的 `.exe` 或 `.pyd` 句柄**。本文给出推荐的用户级处置（不进项目配置），以及本仓库已做的无侵入兜底。

## 项目已内置

| 项 | 说明 |
|----|------|
| `[tool.pytest.ini_options] addopts` | `--basetemp=.pytest_basetemp`，pytest 临时目录落在仓库根，减轻 `%TEMP%` 权限类报错；`testpaths = ["tests"]` |
| `.gitignore` | 忽略 `.pytest_basetemp/`、`_regress_venv/`、`.venv-test/` 等本地目录 |
| `scripts/run_tests.ps1` / `run_tests.sh` | 仓库根一键 `uv sync` + `pytest` |

项目**没有**把 `link-mode` 或 `default-groups` 写进 `pyproject.toml`——那是个人环境偏好，不应污染团队约定。

## 推荐的用户级设置（一次配好，所有 uv 项目受益）

### 1. 把 `link-mode` 设到用户配置

在 `%APPDATA%\uv\uv.toml`（不存在就新建）写：

```toml
link-mode = "copy"
```

或在 PowerShell Profile 里 `setx UV_LINK_MODE copy`（新 shell 生效）。

### 2. 开发工具用 `uv tool`，跟项目 venv 解耦

这样 IDE / 语言服务锁的是**用户目录**下的 `ruff.exe`，不会阻塞仓库 `uv sync`：

```powershell
uv tool install ruff
uv tool install pylint
uv tool update-shell      # 首次用要加 PATH
```

需要时直接 `ruff check .`、`pylint ziniao_mcp`；或零持久化的 `uvx ruff check .`。

### 3. 让 IDE 指向 `uv tool` 里的 ruff（可选）

Cursor / VS Code 的 Ruff 扩展把解释器/可执行文件指向 `%USERPROFILE%\.local\bin\ruff.exe`（`uv tool dir` 能查到），即可彻底避免 venv 内 `ruff.exe` 被 IDE 扩展持有。

## 常用命令

```powershell
# 日常
uv sync
uv run pytest
# 或
.\scripts\run_tests.ps1

# 与 CI 一致
uv run pytest tests/ -v --ignore=tests/integration_test.py
```

## 仍然失败的处置

1. 关掉 IDE 的 Ruff/Pylint/Python 扩展或整个 IDE，再 `uv sync`。
2. 结束持有 `.venv\Scripts\*.exe` 或 `.venv\Lib\**\*.pyd` 句柄的进程（任务管理器或 `Get-Process` 排查）。
3. 仓库放本机 NTFS 盘，避免与 uv 缓存盘跨卷触发链接异常。
4. 极端情况删 `.venv` 重建——若提示"无法删除"，基本是句柄未释放，见第 1–2 步。
