[根 CLAUDE](../CLAUDE.md) » **tests**

## 职责

**pytest** 套件：包 API 契约、CLI 行为、会话与站点逻辑、录制与 stealth、编码与 JSON 输出等回归；`integration_test.py` 偏集成/环境敏感场景。

## 布局

- `conftest.py`：共享 fixture。
- `test_*.py`：按主题拆分（`test_client`、`test_session`、`test_sites_*`、`test_recording_*`、`test_cli_*` 等）。

## 运行

```bash
uv run pytest
```

（根目录 `pyproject.toml` 中 `[dependency-groups] dev` 含 `pytest`、`pytest-asyncio`。）

## 注意

- 部分测试可能依赖本机 Chrome / 紫鸟环境；失败时先对照 `tests/integration_test.py` 与 README 中的前提说明。
