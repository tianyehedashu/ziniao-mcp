# iframe 支持

ziniao-mcp 通过**上下文切换 + 元素代理 + 协议级事件**三层架构，让工具透明地在 iframe 内工作。

## 问题背景

CDP（Chrome DevTools Protocol）的 DOM 操作默认针对主文档。当目标元素在 iframe 内部时，`DOM.querySelector` 找到的 node 属于 iframe 的文档上下文，对该 node 调用 `DOM.getContentQuads`、`DOM.resolveNode` 等操作会返回错误：

```
Node with given id does not belong to the document [code: -32000]
```

## 架构设计

```
switch_frame(action="switch", selector="iframe#xxx")
 │
 ├─ 1. DOM 层：tab.select() 找到 iframe 元素
 ├─ 2. DOM 层：DOM.describeNode → 获取 frame_id
 ├─ 3. 隔离世界：Page.createIsolatedWorld(frame_id) → execution_context_id
 │
 └─ 后续所有工具自动走 iframe 路径：
      ├─ find_element → find_element_in_frame
      │   ├─ Runtime.evaluate(context_id) 在 iframe 内执行 JS 查找元素
      │   ├─ 主文档 evaluate → 获取 iframe 视口位置（含 clientLeft/clientTop 边框补偿）
      │   ├─ 坐标合并 → 绝对视口坐标
      │   └─ 返回 IFrameElement 代理
      │
      └─ IFrameElement 代理（协议级交互）
          ├─ click()        → Input.dispatchMouseEvent（视口坐标）
          ├─ get_position() → 返回绝对视口坐标
          ├─ clear_input()  → Ctrl+A + Backspace（协议级键盘事件）
          └─ send_keys()    → Input.dispatchKeyEvent（逐字符）
```

### 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 获取 frame_id | `DOM.describeNode` 读取 `node.frame_id` | 比 URL/name 匹配更可靠，无需遍历 frame tree |
| 帧内 JS 执行 | `Page.createIsolatedWorld` + `Runtime.evaluate(context_id)` | 隔离世界可访问 DOM，`grantUniversalAccess=true` 支持跨域 iframe |
| 元素交互 | CDP `Input.dispatch*Event`（视口坐标） | 协议级事件不受 DOM 文档上下文限制，跨 iframe 直接生效 |
| 坐标计算 | iframe `getBoundingClientRect()` + `clientLeft/Top` + 元素 `getBoundingClientRect()` | 补偿 iframe 边框偏移，得到正确的视口绝对坐标 |
| 元素代理 | `IFrameElement` 类，接口兼容 nodriver `Element` | 对上层代码透明，`find_element` 返回代理后，click/fill/hover 等无需任何修改 |

## 工具 iframe 支持矩阵

### 全自动适配（通过 `find_element` 统一处理）

| 工具 | iframe 行为 |
|------|-------------|
| `click` | 在 iframe 内定位元素 → 计算绝对坐标 → CDP 鼠标事件点击 |
| `hover` | 在 iframe 内定位元素 → 贝塞尔曲线移动到绝对坐标 |
| `fill` | 在 iframe 内定位输入框 → 点击聚焦 → 清除 → 逐字输入 |
| `fill_form` | fields 循环内通过 `find_element` → 支持 iframe |
| `drag` | 源/目标元素均通过 `find_element` 查找 → 坐标拖拽 |
| `upload_file` | iframe 内通过 `find_element` 获取元素 → `DOM.setFileInputFiles(backend_node_id)` |

### 单独适配

| 工具 | 适配方式 |
|------|----------|
| `wait_for` | iframe 模式下通过 `find_element` 轮询查找，300ms 间隔 |
| `evaluate_script` | iframe 模式下通过 `eval_in_frame` 在帧的 isolated world 中执行 JS |
| `take_screenshot` | iframe 内元素截图：获取绝对坐标 → `Page.captureScreenshot(clip=...)` 裁切 |
| `take_snapshot` | iframe 模式下通过 `eval_in_frame("document.documentElement.outerHTML")` 获取帧 HTML |

### 无需适配（协议级/页面级操作，天然跨 iframe）

| 工具 | 原因 |
|------|------|
| `press_key` | CDP `Input.dispatchKeyEvent` 是协议级事件 |
| `handle_dialog` | JS 对话框由页面处理 |
| `navigate_page` / `wait_for`（主文档） | 页面级操作 |
| `list_console_messages` / `get_console_message` | 非 DOM 操作 |
| `list_network_requests` / `get_network_request` | 非 DOM 操作 |
| `emulate` / `resize_page` | 设备/环境级设置 |
| `start_client` / `list_stores` / `open_store` / ... | 生命周期管理 |

## 使用流程

```
1. take_snapshot                                    ← 看到页面有 iframe
2. switch_frame(action="list")                      ← 列出所有 frame
3. switch_frame(action="switch", selector="iframe#target")  ← 切入
4. click / fill / evaluate_script / ...             ← 正常操作（自动走 iframe 路径）
5. switch_frame(action="main")                      ← 切回主文档
```

## 人类行为模拟的 iframe 兼容

`human_behavior.py` 中的拟人化函数均支持可选的 `element` 参数：

| 函数 | element 参数行为 |
|------|-----------------|
| `human_click` | 当 element 为 IFrameElement 时，直接从其获取绝对坐标用于贝塞尔曲线移动和点击 |
| `human_hover` | 同上，移动鼠标到 IFrameElement 的视口坐标 |
| `human_fill` | 将 element 传递给 `human_click` 聚焦，后续键盘事件为协议级 |
| `human_type` | 将 element 传递给 `human_click` 聚焦（若有 selector），后续逐字输入为协议级 |

## 实现文件

| 文件 | 改动 |
|------|------|
| `ziniao_mcp/iframe.py` | **新增**：IFrameContext、IFrameElement 代理、_CompatPosition、eval_in_frame、find_element_in_frame、find_element、collect_frames、switch_to_frame |
| `ziniao_mcp/session.py` | StoreSession 新增 `iframe_context` 字段 |
| `ziniao_mcp/tools/navigation.py` | 新增 `switch_frame` 工具；`wait_for` 改用 `find_element` |
| `ziniao_mcp/tools/input.py` | 所有 7 个元素操作工具（click/fill/fill_form/type_text/hover/drag/upload_file）改用 `find_element`；drag 在 iframe 模式下使用协议级拖拽 |
| `ziniao_mcp/tools/debug.py` | `evaluate_script` 支持 `eval_in_frame`；`take_screenshot` 支持 iframe 元素裁切；`take_snapshot` 支持获取帧 HTML |
| `ziniao_mcp/stealth/human_behavior.py` | `human_click/hover/fill/type` 新增 `element` 参数；新增 `_get_box_from_element` 辅助函数 |

## 已知限制

1. **嵌套 iframe**：当前支持一层 iframe。嵌套 iframe 需先切到外层，再切到内层（需手动多次 switch）。
2. **iframe 导航**：iframe 内页面导航后，isolated world 上下文会失效，需重新 `switch_frame(action="switch")` 刷新上下文。
3. **跨域 iframe**：通过 `grantUniversalAccess=true` 支持，但某些极端安全策略下可能受限。
