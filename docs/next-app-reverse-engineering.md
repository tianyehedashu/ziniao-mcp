# Next.js / RSC 应用的 API 逆向方法论

> **读者**：要给 ziniao 新增 site 预设、又发现目标站点是 Next.js / React Server Components / tRPC 混合架构，**没有官方 OpenAPI** 的工程师。
>
> **产出**：一套可复用的五步法，把"浏览器里能做的事"沉淀成 `ziniao <site> <action>` 子命令。本文档以 [site-hub/google-flow](../site-hub/google-flow/README.md)（Google Labs Flow）为落地参考。

---

## 背景：Next.js 应用的"API"其实有四种

现代 Next.js App Router 应用的前后端通信通常混合了四种形态，**不要默认它们都是 REST**：

| 形态 | URL 特征 | 返回体 | 典型鉴权 | 可否直接 fetch 复用 |
|------|---------|--------|---------|-----------------|
| **RSC 流** | `?_rsc=xxxx` / `Accept: text/x-component` | 二进制 `$@1:...` 分块 | Cookie | 可，但解析流格式非常脏；**优先找下层** |
| **tRPC** | `/api/trpc/<router>.<proc>` | `{ result: { data: { json: ... } } }` | Cookie / CSRF | ✅ 推荐，payload 结构稳定 |
| **Next Route Handler** | `/api/<whatever>` | 自定义 JSON | Cookie | ✅ 最好复用的路径 |
| **第三方后端 REST** | 完全不同域名（例如 `aisandbox-pa.googleapis.com`） | gRPC-over-JSON / 自定义 | `Authorization: Bearer` / reCAPTCHA token | ✅ 最稳；绕过 Next 的所有中间层 |

**方法论的核心**：**不要在 RSC 层纠缠**，逐层追到最接近业务的那一层（通常是第三方 REST 或 tRPC）再复用。

---

## 五步法

### Step 1 · HAR 抓真实流量

在 DevTools Network 面板 → 完整执行一次要自动化的业务操作（点按钮、填表单）→ 右键"Save as HAR"。

关注的字段：

- **Request URL**：是否同源？有无查询串 `?_rsc=`？
- **Request Method + Content-Type**：是否 `application/json`？是否 `text/plain`（见 Step 4）？
- **Request Headers**：`Authorization` / `Cookie` / `X-CSRF` / `X-Recaptcha-*`。
- **Initiator**：链到具体 JS 文件（webpack chunk）——后续反查常量的入口。
- **Response**：如果是 RSC 流就直接跳过，找到**更接近业务的下一跳**。

> 捷径：HAR 打开后，先按 **状态码=200 + 尺寸>1KB + 非 text/html** 过滤，余下的就是候选接口池。

### Step 2 · 识别鉴权来源

常见几种：

1. **Cookie-only**：浏览器自动带，CLI 层直接 `fetch(url, { credentials: 'include' })`。最简单。
2. **Bearer token（短期）**：先调一个 session endpoint（常见 `/api/auth/session`、`/api/token`、`/oauth2/token`）拿 `access_token`，再作为 `Authorization: Bearer <token>` 调业务 API。
3. **CSRF / XSRF**：从 Cookie 或 `<meta name="csrf-token">` 取，作为 header（`X-CSRF-Token`）回写。ziniao 的 `header_inject` 就是为此设计，见 [page-fetch-auth.md](./page-fetch-auth.md)。
4. **reCAPTCHA Enterprise token**：业务接口要求页面先 `grecaptcha.enterprise.execute(SITE_KEY, {action:'...'})` 拿动态 token 注入到 body 或 header。特别关注 **site key** 和 **action** 两个常量的识别（见 Step 5）。

一个简单的判断法：看看你能否在 **incognito + 不登录** 状态下从页面 Network 直接复刻这个请求。不能 → 鉴权不仅靠 Cookie，需要组合多种。

### Step 3 · 分层向下钻，优先选"最薄的包装层"

例子（Google Flow 参考图生成）：

```
UI 按钮点击
  ↓
Next RSC 路由 /fx/...?_rsc=abc           ← 放弃这一层
  ↓
Next Route Handler /fx/api/trpc/...      ← 可用，但只是转发
  ↓
第三方后端 aisandbox-pa.googleapis.com   ← 选这一层
```

**选择原则**：

- 如果 Next 只是做**透传** + 鉴权注入，直接打第三方后端（需要自己补鉴权头）。
- 如果 Next 做了**业务校验 / 数据改写**（tRPC 里很常见），就走 tRPC。
- 避免走 RSC：除非走投无路，解析成本过高。

识别是否透传的方法：看 Next Route Handler 的请求体和响应体是否和第三方后端几乎一致。如果 diff 只有 Authorization / X-Goog-* 这类 header，就是透传。

### Step 4 · 绕过 CORS 的两个实用技巧

ziniao 预设是在页面上下文（当前 tab 的 Origin）内 fetch，如果目标接口跨源就会触发 CORS preflight。应对：

#### 技巧 A · 改 Content-Type 变 "simple request"

> [CORS simple request 豁免](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#simple_requests)：`text/plain` / `application/x-www-form-urlencoded` / `multipart/form-data` 三种 MIME 不触发 preflight。

用法：body 仍是 JSON 字符串，Content-Type 声明为 `text/plain;charset=UTF-8`。绝大多数服务端是 `JSON.parse(rawBody)`，照样能解析。

```js
fetch(url, {
  method: 'POST',
  credentials: 'include',
  headers: {
    'content-type': 'text/plain;charset=UTF-8',
    authorization: 'Bearer ' + token,
  },
  body: JSON.stringify(payload),
});
```

实战验证：Google Flow 的 `uploadImage` / `batchGenerateImages` 都用此法跑通。

#### 技巧 B · 让 daemon 出站而非页面出站

页面里 fetch 跨源被 CORS 挡，但 daemon（Python 进程）是普通 HTTP 客户端，没有 CORS 概念。ziniao 的 `httpx` 下载 fifeUrl 就是这种，见 `ziniao_mcp/sites/flow_images.py::_download_fife_url`。适用于**只需下载/上传字节流**、不需要浏览器 Cookie 的场景。

> ⚠️ 如果接口必须带 Cookie（同源策略），仍然要走页面 fetch；此时回到技巧 A。

### Step 5 · 反查魔术常量（webpack bundle）

业务接口常要求**硬编码常量**：reCAPTCHA site key、action 名、模型枚举、某个 header 的 secret salt 等。这些不会出现在 HAR，需要在前端 JS bundle 里搜。

#### 方法

1. DevTools → **Sources** → Cmd/Ctrl+P 按文件搜 `chunk-*.js`。
2. **Cmd/Ctrl+Shift+F** 全局搜关键字。搜索优先级：
   - HAR 里业务响应体的字段名（如 `recaptchaContext`、`batchGenerateImages`）。
   - HAR 里 request body 里出现的枚举值（如 `IMAGE_GENERATION`）。
   - 已知的 API 路径末段（如 `uploadImage`）。
3. 找到后把整个 chunk 下载下来，用 [`prettier --parser babel`](https://prettier.io/) 格式化，搜同一关键字附近的字面量（`6LdsFiUsAAA...`、`'PINHOLE'` 之类）。
4. 验证假设：把常量替换到最小复现请求里跑通 → 写入 preset `script`。

> 实战教训：Google Flow 的 reCAPTCHA action 最初假设是 `'generate'`（直觉命名），实际是 `'IMAGE_GENERATION'`；第一次跑 403，回到 bundle 搜 `execute(` 附近才纠正。**不要靠直觉猜枚举值**。

---

## 写入 ziniao 预设的形态选择

| 场景 | 推荐 preset mode | 例子 |
|------|---------------|------|
| 单次 GET/POST，**参数固定**，Cookie 够用 | `fetch`（声明式 JSON） | `rakuten/reviews-csv` |
| 需要多步：session → project → upload → generate → parse fifeUrl | `js`（自定义 script） | `google-flow/imagen-ref-generate` |
| 需要从 Cookie/localStorage/meta 注入 header | `fetch` + `header_inject` | `rakuten/rms-*`（CSRF） |
| 要读取本地大文件 → 上传 | `js` + `type: file` / `file_list` 变量 | `google-flow/imagen-ref-generate` |

`mode: js` 的 `script` 内可以用 `await` 链式调多个接口；页面上下文的 Cookie / `grecaptcha` / `localStorage` 全部可用。唯一约束是**总时长 < daemon timeout**（默认 auto 120s for `page_fetch`；`--timeout 300` 可显式延长）。

---

## 反模式清单

下面这些做法在调研时会绕远路，**请优先避开**：

1. ❌ **在 Slate.js 编辑器里通过 `execCommand` 注文本**。Slate 不认，必须用 CDP `Input.insertText` 或直接调 API。
2. ❌ **把 RSC 流里的业务 URL 当接口**（`?_rsc=` 的响应不是 JSON）。永远往下一跳找 REST/tRPC。
3. ❌ **在 preset 里硬编码 `Authorization: Bearer <现场抓的 token>`**。token 必有时限，必须动态获取。
4. ❌ **假设 Content-Type 必须是 `application/json`**。当跨源时，`text/plain` 更能跑通。
5. ❌ **靠 `candidatesCount` / `numImages` 这类直觉字段请求批量**。很多 Google API 实际是 `requests[]` 多 item；不抓包直接猜，100% 翻车。
6. ❌ **用 site key 当 secret 藏**。reCAPTCHA site key 本就是公开值；只有 server-side 的 secret key 才保密，浏览器里永远拿不到。
7. ❌ **忽略配额分桶**。PER_MODEL / PER_ENDPOINT / PER_ACCOUNT 各有独立池；429 时换一个维度比重试更有效。

---

## 案例索引

| 案例 | 站点 | 关键点 |
|------|------|-------|
| [google-flow](../site-hub/google-flow/README.md) | Google Labs Flow | RSC 完全绕开；text/plain 绕 CORS；reCAPTCHA Enterprise + site key + action 双常量；fifeUrl daemon 侧下载；多 ref × 多 count 矩阵 |
| [rakuten](../site-hub/rakuten/) | Rakuten RMS | tRPC-style + CSRF `header_inject`；CP932 CSV 解码；offset 分页 |
| [site-fetch-and-presets.md](./site-fetch-and-presets.md) | — | preset JSON schema 全集；`mode: fetch` 声明式字段 |
| [page-fetch-auth.md](./page-fetch-auth.md) | — | `header_inject` 从 Cookie/localStorage/eval 三种源注 header |

---

## 快速 Checklist（给下一个站点抄作业）

```
[ ] 在已登录浏览器里完整跑一次 → 存 HAR
[ ] HAR 过滤出业务 API（非 RSC / 非 text/html）
[ ] 鉴权归类：Cookie / Bearer / CSRF / reCAPTCHA
[ ] 判断是否跨源 → 评估 text/plain 技巧或 daemon 出站
[ ] webpack bundle 反查魔术常量（site key / action / 枚举）
[ ] 选 preset mode：fetch（声明式）还是 js（多步脚本）
[ ] type: file / file_list 处理本地输入
[ ] --save-images / -o 落盘
[ ] 写 SKILL.md 给 agent 用
[ ] README.md 给人看
```
