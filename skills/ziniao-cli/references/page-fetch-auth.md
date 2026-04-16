# Header 注入（`header_inject`）

声明式地从浏览器运行时（Cookie / localStorage / sessionStorage / JS 表达式）读取令牌，写入 HTTP 请求头。适用于 `mode: "fetch"` 的请求。

整体架构、`auth.type` 含义 → [site-fetch-and-presets.md](site-fetch-and-presets.md)。

---

## 一、使用

### 1. 预设 JSON（推荐）

```json
{
  "header_inject": [
    {"header": "x-csrf-token", "source": "cookie", "key": "XSRF-TOKEN"},
    {"header": "Authorization", "source": "localStorage", "key": "auth_token", "transform": "Bearer ${value}"},
    {"header": "X-App-Token", "source": "eval", "expression": "document.querySelector('meta[name=csrf]')?.content"}
  ]
}
```

每项字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `header` | 是 | 写入的 HTTP 请求头名 |
| `source` | 是 | `cookie` / `localStorage` / `sessionStorage` / `eval` |
| `key` | cookie/storage 时 | Cookie 名或 storage key |
| `expression` | eval 时 | JS 表达式，返回令牌值 |
| `transform` | 否 | 值模板，`${value}` 为占位符（如 `"Bearer ${value}"`） |

### 2. CLI

```bash
# 紧凑格式: source:key=header
ziniao network fetch -f ./req.json --inject cookie:XSRF-TOKEN=x-csrf-token

# 多条注入
ziniao network fetch -f ./req.json \
  --inject cookie:XSRF-TOKEN=X-XSRF-TOKEN \
  --inject localStorage:token=Authorization

# JSON 格式
ziniao network fetch -f ./req.json \
  --inject '{"header":"x-csrf-token","source":"cookie","key":"XSRF-TOKEN"}'
```

CLI `--inject` 覆盖文件/预设中的 `header_inject`。

### 3. `fetch-save`（从抓包生成）

`ziniao network fetch-save` 会：

- 在 `request_headers` 中按内部表（`_CSRF_REQUEST_HEADER_NAMES_ORDERED`）匹配第一个 CSRF 头；
- 生成 `header_inject: [{"header": 原始头名, "source": "cookie", "key": "XSRF-TOKEN"}]`；
- 从输出 `headers` 里剔除表中所有同名变体。

### 4. MCP `page_fetch`

| 参数 | 说明 |
|------|------|
| `header_inject` | JSON 数组字符串，如 `'[{"header":"x-csrf-token","source":"cookie","key":"XSRF-TOKEN"}]'` |

---

## 二、实现

### 分层

```text
预设 JSON / CLI / MCP
       ↓
prepare_request（合并参数 + plugin.before_fetch；不做注入校验）
       ↓
_page_fetch（daemon）→ _normalize_header_inject(args)  ← CLI 与 MCP 唯一归一化点
       ↓
_page_fetch_fetch → 页面内 fetch + 通用注入循环
```

- **`_normalize_header_inject`**（`ziniao_mcp/sites/__init__.py`）：校验每项 `header` + `source`，过滤无效项，无有效项时移除 key。仅由 **`dispatch._page_fetch`** 调用。
- **`_page_fetch_fetch`** / **`_page_fetch_js`**（`ziniao_mcp/cli/dispatch.py`）：读取已归一化的 `args["header_inject"]`，生成 JS 按 `source` 类型读值、按 `transform` 变换、写入请求头。与 **`ziniao eval`** 一致：若当前会话存在 **`iframe_context`**（`ziniao nav frame` 进入的子帧），则在 **该 iframe 的 execution context** 内执行脚本；否则在顶层 `tab.evaluate`。紫鸟等多店场景下 RMS 常落在子帧，此前仅顶层执行会导致读不到 `meta` / `localStorage`、CSRF 头缺失（如乐天 **cpnadv** 返回 401）。
- **`fetch-save`**（`ziniao_mcp/cli/commands/network_cmd.py`）：表驱动识别 CSRF 头，生成 `header_inject`。

架构分层与「为何归一化在 `_page_fetch`」→ [site-fetch-and-presets.md](site-fetch-and-presets.md) **架构考量**。

---

## 三、支持的 source 类型

| source | 浏览器内读取方式 | 典型场景 |
|--------|----------------|----------|
| `cookie` | `document.cookie` 正则匹配 | XSRF/CSRF 令牌 |
| `localStorage` | `localStorage.getItem(key)` | SPA JWT 存储 |
| `sessionStorage` | `sessionStorage.getItem(key)` | 临时会话令牌 |
| `eval` | `eval(expression)` | meta 标签、全局变量、DOM |

---

## 四、扩展

### 新增 CSRF 头名识别（`fetch-save`）

将小写形式加入 `_CSRF_REQUEST_HEADER_NAMES_ORDERED`（优先级越靠前越优先）。

### 自定义模板

```bash
ziniao site fork rakuten/some-preset
# 编辑 ~/.ziniao/sites/.../xxx.json 里的 header_inject
```

### 复杂鉴权

当声明式 `header_inject` 无法满足时，用 `mode: "js"` + `script` 在页面内全权处理；或实现 `SitePlugin.before_fetch`。

---

## 五、排错

| 现象 | 排查 |
|------|------|
| 401 / 403 | DevTools 看真实请求头名；预设里 `header_inject[].header` 与之一致；确认标签页已登录。 |
| 过期令牌 | 不要在 JSON 里硬编码令牌值；用 `header_inject` 运行时从 Cookie/storage 读取。 |
| `fetch-save` 未生成注入规则 | 请求头名不在识别表里；扩展 `_CSRF_REQUEST_HEADER_NAMES_ORDERED` 或手改 JSON。 |

---

## 六、相关

- [site-fetch-and-presets.md](site-fetch-and-presets.md) — 架构、会话鉴权、模板总览、分页、js 模式
- 完整命令表：[commands.md](commands.md)
