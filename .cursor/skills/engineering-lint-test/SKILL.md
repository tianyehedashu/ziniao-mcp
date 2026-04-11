---
name: engineering-lint-test
description: ziniao 仓库 Python 3.10+（uv、ziniao / ziniao_mcp / ziniao_webdriver）：改代码前读根目录 pyproject.toml 的 [tool.ruff]、[tool.pylint]；Ruff 自动修复仅限格式与无语义风险；禁止滥用 # type: ignore、无理由 noqa、Any/cast 或改业务语义压检查。pytest + pytest-asyncio，策略见 tests/CLAUDE.md；核心逻辑变更需补测；禁止为绿灯改错断言；难测时说明设计缺陷与解耦方向。CI 与 task.ps1 默认排除 tests/integration_test.py。触发词：lint、ruff、pylint、pytest、单测、集成测、测试失败、uv run、task.ps1。
---

# 工程纪律：Lint 与需求驱动测试

在代码生成、修改与修复中与 `strict-code-review` 配合：本技能约束**执行过程**（Lint 与测试），审查技能约束**交付前评审**。

## 技术栈与边界

| 维度 | 约定 |
|------|------|
| 语言 | Python ≥3.10（`pyproject.toml` `[project].requires-python`） |
| 运行 | `uv sync` / `uv run …`；Windows 可用 `task.ps1` |
| 包 | `ziniao`、`ziniao_mcp`、`ziniao_webdriver` |
| Lint | Ruff 为主（`[tool.ruff]` / `[tool.ruff.lint]`），Pylint 为辅（`[tool.pylint]`）；根目录 `skills/` 在 Ruff `extend-exclude` 中 |
| 测试 | pytest、pytest-asyncio；分层见 `tests/CLAUDE.md` |
| CI | `.github/workflows/ci.yml`：`uv run pytest tests/ -v --ignore=tests/integration_test.py`（集成测需环境，默认不进 CI） |

调整 `pyproject.toml` 工具区块属团队决策；未经用户要求，不在普通任务中放宽规则。

## 启用时机

| 场景 | 侧重 |
|------|------|
| 编写或修改 Python、修 Bug、用户要求 lint/格式化 | Lint 工具链 |
| 新功能、核心业务变更、测试失败 | 测试与设计演进 |

## 一、Lint：配置优先、修复有界

**改代码前**通读 `pyproject.toml`：`[tool.ruff]`、`[tool.ruff.lint]`、`per-file-ignores`、`[tool.pylint.*]`。单文件已有 `per-file-ignores` 时，先弄清历史原因再决定沿用或重构移除。生成代码即对齐 Ruff 风格，避免事后堆 `noqa`。

**允许**：`ruff check --fix`、`ruff format` 等与当前规则一致的格式及低风险风格修复。

**禁止**（为消告警牺牲正确性或契约）：

- 用 `Any`、`cast(..., Any)`、无依据 `# type: ignore` 掩盖类型或协议问题
- 用 `# noqa` 大面积屏蔽以掩盖逻辑缺陷、异常处理或 API 误用（除非用户同意且注释写明理由与风险）
- 为通过检查改写业务分支、默认值或对外契约

遇行为类 Ruff 规则、Pylint 语义提示或需改签名才能「干净」的类型问题时：用简短中文说明根因 → 给出可验证、小步可回滚的重构方案 → **语义相关改动须经用户确认**。

## 二、测试：需求驱动、拒绝创可贴

核心业务路径（CLI、HTTP 契约、站点预设、会话、录制、stealth 等，见 `tests/` 划分）变更时，在 `tests/` 补充或更新用例，风格对齐 `conftest.py`、既有模块与 `tests/CLAUDE.md`。用例围绕需求与风险（空值、编码、异步边界、外部 I/O 与 mock 边界），避免无行为意义的断言堆砌。

与 CI 一致的验证：

```bash
uv run pytest tests/ -v --ignore=tests/integration_test.py
```

Windows：`.\task.ps1 test`；含集成：`.\task.ps1 test-all` 或 `test-integration`（见 `task.ps1`）。用户明确不要求测试时，回复中用一句话说明风险即可。

测试失败时禁止：无原则改 `expected`/快照以迁就错误实现；在业务代码打补丁「骗过」断言。顺序应为：理解失败 → 判断预期是否合理 → 修实现，或仅在测试本身错误时修测试。

当出现 fixture/mock 过深、单测脆弱常红、I/O 与业务同模块难拆等情况时，停止盲补补丁，向用户说明**难测原因**（耦合、隐式全局、缺少注入点等）与**演进方向**（拆模块、依赖注入、缩小单元边界）。

## 三、执行前自检

```
Lint
- [ ] 已读 pyproject.toml 中 ruff / pylint 相关段
- [ ] Ruff 修复仅限格式或已确认无语义风险
- [ ] 非格式问题已说明根因与方案，必要时已获确认

测试
- [ ] 已跑或与 CI 一致的 pytest（默认排除 integration_test）
- [ ] 核心变更有对应测试或已声明例外
- [ ] 未通过改断言或糊补丁强行绿灯
- [ ] 难测/频败已给出缺陷识别与重构方向
```

## 与其他技能

- PR/Diff 评审遵循 `strict-code-review` 的格式与条数限制。
- 浏览器与店铺自动化以 `ziniao-cli`、`store-rpa-scripting` 等为主；本技能仅约束其中的代码质量与测试部分。
