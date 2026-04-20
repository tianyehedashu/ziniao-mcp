[根 CLAUDE](../CLAUDE.md) » **tests**

## 职责

**pytest** 套件：包 API 契约、CLI 行为、会话与站点逻辑、录制与 stealth、编码与 JSON 输出等回归；`integration_test.py` 偏集成/环境敏感场景。

## 布局

- `conftest.py`：共享 fixture。
- `test_*.py`：按主题拆分（`test_client`、`test_session`、`test_sites_*`、`test_recording_*`、`test_cli_*` 等）。

## 运行

```bash
uv sync
uv run pytest
```

`dependency-groups.dev` 提供 pytest、pytest-asyncio、Ruff、Pylint、keyring（测 secret 用）。

**Windows 一键**（见 [docs/dev-environment-windows.md](../docs/dev-environment-windows.md) 的环境偏好建议）：

```powershell
.\scripts\run_tests.ps1
```

## 注意

- 部分测试可能依赖本机 Chrome / 紫鸟环境；失败时先对照 `tests/integration_test.py` 与 README 中的前提说明。
