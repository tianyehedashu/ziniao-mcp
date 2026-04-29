[根 CLAUDE](../CLAUDE.md) » **docs**

## 职责

给人读的 **产品/架构/运维** 文档（非 AI 专用）；与根 `CLAUDE.md` 互补：后者偏「Agent 导航索引」，本目录偏完整说明与流程图。

## 文档地图


| 文档                                                           | 内容                                                                                                                                                       |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `architecture.md` / `architecture-packages.md`               | 总架构与三包关系、Mermaid 依赖图                                                                                                                                     |
| `installation.md` / `install-uv-windows.md`                  | 安装与 uv                                                                                                                                                   |
| `development.md`                                             | 开发工作流                                                                                                                                                    |
| `cli-json.md` / `cli-llm.md` / `cli-agent-browser-parity.md` | CLI JSON 模式与 Agent 对齐                                                                                                                                    |
| `api-reference.md`                                           | API 参考                                                                                                                                                   |
| `recording.md`                                               | 录制 IR 与回放                                                                                                                                                |
| `stealth.md`                                                 | 反自动化与 JS 注入策略                                                                                                                                            |
| `chrome-security-boundaries-automation.md`                   | Chromium 安全边界（`isTrusted`、用户激活、权限/支付/WebAuthn 等）与 CDP 自动化预期；与隐身文档互补                                                                                      |
| `passive-input-automation.md`                                | 强风控站点的 passive / raw CDP `Input.`* 路径与 `site_policy` 边界（相对 `connect`+stealth）；含**紫鸟侧** `ziniao store passive-open <id>`（daemon 仅代理打开，不 attach、不 stealth） |
| `site-fetch-and-presets.md` / `page-fetch-auth.md`           | 站点抓取与鉴权                                                                                                                                                  |
| `site-ui-flows.md`                                           | `mode: ui` 声明式 UI 流：steps[]、extract/fetch、secret 变量、与 fetch/js 的分工                                                                                       |
| `rpa-flows.md`                                               | `kind: rpa_flow` 控制流、`ziniao flow` CLI、`call_preset` / dry-run / 录制草稿                                                                                    |
| `next-app-reverse-engineering.md`                            | Next.js/RSC/tRPC/第三方 REST 四层模型逆向方法论 + 反模式清单                                                                                                              |
| `iframe.md`                                                  | iframe 相关行为                                                                                                                                              |
| `rakuten-presets-smoke-test.md`                              | 乐天 preset 测试说明                                                                                                                                           |
| `directory-conventions.md`                                   | 仓库目录用途、发布边界、`exports/` 落盘约定                                                                                                                              |


## 维护提示

- 架构类变更请同步 `architecture-packages.md` 与根 `CLAUDE.md` 的模块表，避免两处长期不一致。

