# ziniao-mcp 工具速查

**Phase 1 探索**时使用以下 MCP 工具交互式操作页面。**Phase 3 生成脚本**时，将 MCP 工具调用转换为对应的 Python 代码（见下方"脚本中的对应写法"）。

## Phase 1 探索用工具

## 连接与生命周期

| 工具 | 参数 | 用途 |
|------|------|------|
| `connect_store(store_id)` | store_id: 店铺 ID | 连接已运行的店铺（推荐） |
| `open_store(store_id)` | store_id: 店铺 ID | 打开并连接店铺（会重启已运行的） |
| `list_stores()` | 无 | 获取所有店铺列表 |
| `list_open_stores()` | 无 | 查看已打开的店铺 |
| `close_store(store_id)` | store_id: 店铺 ID | 关闭店铺 |

## 导航

| 工具 | 参数 | 用途 |
|------|------|------|
| `navigate_page(url)` | url: 目标 URL | 导航到页面 |
| `wait_for(selector, state, timeout)` | selector: CSS 选择器 | 等待元素/页面加载 |
| `list_pages()` | 无 | 列出所有标签页 |
| `select_page(page_index)` | page_index: 索引 | 切换标签页 |
| `new_page(url)` | url: 可选 | 新建标签页 |
| `close_page(page_index)` | page_index: 默认 -1 | 关闭标签页 |

## 页面理解

| 工具 | 参数 | 用途 |
|------|------|------|
| `take_snapshot()` | 无 | 获取 HTML 结构（定位选择器） |
| `take_screenshot(selector, full_page)` | 均可选 | 视觉确认 |
| `evaluate_script(script)` | script: JS 代码 | 提取数据/验证选择器 |

## 输入交互

| 工具 | 参数 | 用途 |
|------|------|------|
| `click(selector)` | selector: CSS 选择器 | 点击元素 |
| `fill(selector, value)` | selector + value | 清空并填写输入框 |
| `fill_form(fields_json)` | JSON 字段列表 | 批量填写表单 |
| `type_text(text, selector)` | text + 可选 selector | 逐字键入（触发事件） |
| `press_key(key)` | key: 按键名 | 按键（Enter/Tab/Escape 等） |
| `hover(selector)` | selector | 鼠标悬停 |
| `drag(source, target)` | 两个选择器 | 拖拽 |
| `handle_dialog(action, text)` | action: accept/dismiss | 处理弹窗 |
| `upload_file(selector, file_paths_json)` | 选择器 + 文件路径 JSON | 上传文件 |

## 网络分析

| 工具 | 参数 | 用途 |
|------|------|------|
| `list_network_requests(url_pattern, limit)` | 均可选 | 列出捕获的请求 |
| `get_network_request(request_id)` | request_id | 获取请求详情 |

## 调试

| 工具 | 参数 | 用途 |
|------|------|------|
| `list_console_messages(level, limit)` | 均可选 | 查看控制台输出 |
| `get_console_message(message_id)` | message_id | 获取完整消息 |
| `emulate(device_name)` | 设备名 | 模拟移动设备 |
| `resize_page(width, height)` | 宽高像素 | 调整视口大小 |

## 脚本中的对应写法

MCP 工具探索阶段的操作，在生成的 Python 脚本中对应的写法。

### 客户端与店铺生命周期

| MCP 工具 | Python 代码（ziniao_webdriver） |
|----------|-------------------------------|
| `start_client` | `client.heartbeat()` / `client.start_browser()` |
| `list_stores` | `client.get_browser_list()` |
| `open_store(id)` | `client.open_store(id)` → 返回含 `debuggingPort` 的 dict |
| `connect_store(id)` | 先 `open_store` 获取端口，再 `nodriver.Browser.create(port=port)` |
| `close_store(id)` | `client.close_store(browser_oauth)` |
| `stop_client` | `client.get_exit()` |

### 浏览器操作

| MCP 工具 | nodriver Python 代码 |
|----------|---------------------|
| `connect_store` | `browser = await nodriver.Browser.create(host="127.0.0.1", port=cdp_port)` |
| `navigate_page(url)` | `await tab.get(url)` |
| `wait_for(selector)` | `await tab.select(selector, timeout=30)` |
| `take_snapshot()` | `html = await tab.get_content()` |
| `click(selector)` | `elem = await tab.select(sel); await elem.click()` |
| `fill(selector, value)` | `elem = await tab.select(sel); await elem.clear_input(); await elem.send_keys(value)` |
| `type_text(text)` | `await tab.send(cdp.input_.dispatch_key_event("char", text=ch))` |
| `press_key(key)` | `await tab.send(cdp.input_.dispatch_key_event(...))` |
| `evaluate_script(js)` | `result = await tab.evaluate(js)` |
| `take_screenshot()` | `await tab.send(cdp.page.capture_screenshot())` |
| `upload_file(sel, paths)` | `elem = await tab.select(sel); await elem.send_file(path)` |
| `list_pages()` | `browser.tabs` |
| `select_page(i)` | `tab = browser.tabs[i]; await tab.bring_to_front()` |
| `new_page(url)` | `tab = await browser.get(url, new_tab=True)` |
