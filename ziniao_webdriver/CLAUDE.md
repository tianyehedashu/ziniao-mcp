[根 CLAUDE](../CLAUDE.md) » **ziniao_webdriver**

## 职责

与 **紫鸟桌面客户端** 的本地 HTTP 通信：心跳、店铺列表、打开/关闭浏览器、获取 CDP 调试端口等。文档参考：[紫鸟开放平台](https://open.ziniao.com/docSupport?docId=98)。

## 关键文件

| 文件 | 说明 |
|------|------|
| `client.py` | `ZiniaoClient`：HTTP API 封装 |
| `lifecycle.py` | `ensure_http_ready`、`open_store_cdp_port` 等与打开流程相关的辅助 |
| `cdp_tabs.py` | `filter_tabs`、`is_regular_tab`：标签页过滤 |
| `js_patches.py` | stealth 用 JS 片段的**规范实现**（`build_stealth_js`、`STEALTH_JS` 等）；`ziniao_mcp/stealth/js_patches.py` 为兼容 re-export |

## 依赖

- 主要 `requests` / 标准库；不反向依赖 `ziniao_mcp`。

## 使用场景

- **独立 RPA 脚本**：`from ziniao import ZiniaoClient` 或 `from ziniao_webdriver import …`（等价），再配合 `nodriver` 连接 CDP，无需启动 CLI daemon。

## 测试

- HTTP 契约与客户端行为见 `tests/test_client.py`、`tests/test_ziniao_http_contract.py` 等。
