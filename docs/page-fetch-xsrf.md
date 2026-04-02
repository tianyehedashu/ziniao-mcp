# XSRF / CSRF 策略（`auth.type: "xsrf"`）

会话鉴权策略之一：从 Cookie 读反 CSRF 令牌，写入请求头。适用于 `auth.type` 为 `xsrf` 的预设。

整体架构、`auth.type` 含义、其他策略 → [site-fetch-and-presets.md](site-fetch-and-presets.md)。

---

## 一、使用

### 1. 预设 JSON（推荐）

```json
{
  "xsrf_cookie": "XSRF-TOKEN",
  "xsrf_headers": ["x-csrf-token"]
}
```

- **`xsrf_cookie`**：从 `document.cookie` 读令牌的 Cookie 名。
- **`xsrf_headers`**：`string[]`，令牌写入的请求头名（按顺序逐个设置）。
- 仅设 `xsrf_cookie`、不写 `xsrf_headers` → 默认 `["X-XSRF-TOKEN"]`。

### 2. CLI

```bash
ziniao network fetch -f ./req.json --xsrf-cookie XSRF-TOKEN

# 重复 --xsrf-header 写入多个请求头
ziniao network fetch -f ./req.json \
  --xsrf-cookie XSRF-TOKEN \
  --xsrf-header X-XSRF-TOKEN \
  --xsrf-header x-csrf-token
```

CLI 传入的 `xsrf_headers` 覆盖文件/预设中的同名字段。

### 3. `fetch-save`（从抓包生成）

`ziniao network fetch-save` 会：

- 在 `request_headers` 中按内部表（`_CSRF_REQUEST_HEADER_NAMES_ORDERED`）匹配第一个 CSRF 头；
- 写入 `xsrf_cookie: "XSRF-TOKEN"` + `xsrf_headers: [原始头名]`；
- 从输出 `headers` 里剔除表中所有同名变体。

### 4. MCP `page_fetch`

| 参数 | 说明 |
|------|------|
| `xsrf_cookie` | Cookie 名 |
| `xsrf_headers` | JSON 数组字符串，如 `'["x-csrf-token"]'`；不传则由 `xsrf_cookie` 触发默认 |

---

## 二、实现

### 分层

```text
预设 JSON / CLI / MCP
       ↓
prepare_request（合并参数 + plugin.before_fetch）
       ↓
_normalize_xsrf（唯一出口：xsrf_cookie + xsrf_headers[]）
       ↓
_page_fetch_fetch → 页面内 fetch + 多头注入
```

- **`_normalize_xsrf`**（`ziniao_mcp/sites/__init__.py`）：`xsrf_cookie` 存在且 `xsrf_headers` 为空时补 `["X-XSRF-TOKEN"]`；过滤空串；无 cookie 时移除 `xsrf_headers`。
- **`_page_fetch_fetch`**（`ziniao_mcp/cli/dispatch.py`）：对 args 副本调用 `_normalize_xsrf`，生成内联 JS 循环 `xsrf_headers` 写入请求头。
- **`fetch-save`**（`ziniao_mcp/cli/commands/network_cmd.py`）：表驱动（`_CSRF_REQUEST_HEADER_NAMES_ORDERED`）识别并剥离。

---

## 三、扩展

### 新增 CSRF 头名

将小写形式加入 `_CSRF_REQUEST_HEADER_NAMES_ORDERED`（优先级越靠前越优先）。无需改注入逻辑。

### 令牌不在 Cookie

用 `mode: "js"` + `script` 在页面内读 meta/DOM/全局变量并发请求；或实现 `SitePlugin.before_fetch`。不要在 `_page_fetch_fetch` 里堆特例。

### 自定义模板

```bash
ziniao site fork rakuten/some-preset
# 编辑 ~/.ziniao/sites/.../xxx.json 里的 xsrf_cookie / xsrf_headers
```

---

## 四、排错

| 现象 | 排查 |
|------|------|
| 401 / 403 | DevTools 看真实请求头名；预设里 `xsrf_headers` 与之一致；确认标签页已登录。 |
| 过期令牌 | 不要在 JSON 里硬编码令牌值；依赖 `xsrf_cookie` 运行时读 Cookie。 |
| `fetch-save` 未生成 xsrf 字段 | 请求头名不在识别表里；扩展 `_CSRF_REQUEST_HEADER_NAMES_ORDERED` 或手改 JSON。 |

---

## 五、相关

- [site-fetch-and-presets.md](site-fetch-and-presets.md) — 模板总览、分页、js 模式
- [api-reference.md](api-reference.md) — MCP `page_fetch` 参数表
- 内置示例：`ziniao_mcp/sites/rakuten/cpnadv-performance-retrieve.json`
