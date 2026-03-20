# 紫鸟 MCP 项目任务脚本（使用 uv）
# 用法: make [目标]  或  make help

.PHONY: help install run test test-all test-integration upgrade lock check
.DEFAULT_GOAL := help

help:
	@echo "常用任务："
	@echo "  make install         - 安装依赖"
	@echo "  make run             - 启动 MCP 服务器 (uv run ziniao serve)"
	@echo "  make test            - 运行单元/常规测试（不含集成）"
	@echo "  make test-all        - 运行全部测试（含集成，需 .env）"
	@echo "  make test-integration - 仅运行集成测试（需配置 .env）"
	@echo "  make upgrade         - 升级依赖并更新 lock 后同步安装"
	@echo "  make lock            - 仅更新 lock 文件 (uv.lock)"
	@echo "  make check           - 检查 lock 是否与 pyproject 一致"

install:
	uv sync

run:
	uv run ziniao serve

test:
	uv run pytest tests/ -v --ignore=tests/integration_test.py

test-all:
	uv run pytest tests/ -v

test-integration:
	uv run pytest tests/integration_test.py -v

upgrade:
	uv lock --upgrade
	uv sync

lock:
	uv lock

check:
	uv lock --check
