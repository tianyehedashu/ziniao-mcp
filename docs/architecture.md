# 架构设计

## 整体架构

ziniao-mcp 采用三层架构，将 AI Agent 的意图转化为对浏览器（紫鸟店铺或本地 Chrome）的实际操作；紫鸟与 Chrome 共用同一套会话管理与页面工具。

```
┌──────────────────────────────────────────────────────────┐
│                  AI Agent (Cursor / Claude)               │
│                    通过 MCP 协议通信                       │
└────────────────────────┬─────────────────────────────────┘
                         │ MCP (stdio)
                         ▼
┌──────────────────────────────────────────────────────────┐
│               ziniao_mcp (MCP Server)                     │
│  ┌─────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ server  │→ │ SessionManager│→ │ tools/* (store/chrome │ │
│  │ 配置解析 │  │ 会话 + CDP   │  │ /session/input/nav…)  │ │
│  └─────────┘  └──────┬───────┘  └──────────────────────┘ │
└──────────────────────┼───────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌─────────────────┐  ┌────────────────────────┐
│ ziniao_webdriver │  │ nodriver CDP           │
│ HTTP→紫鸟客户端  │  │ 连接紫鸟/Chrome 的 CDP  │
└────────┬─────────┘  └────────────┬───────────┘
         ▼                          │
┌──────────────────┐   ┌────────────┴────────────┐
│ 紫鸟客户端进程    │   │ 浏览器实例（紫鸟店铺 或   │
│ (ziniao.exe)     │──→│ 本地 Chrome）            │
└──────────────────┘   └────────────────────────┘
```

## 模块职责

### ziniao_webdriver

**职责**：封装与紫鸟客户端的 HTTP 通信。

紫鸟客户端以 WebDriver 模式启动后，在本地监听一个 HTTP 端口（默认 16851）。`ZiniaoClient` 通过向该端口发送 JSON 请求来控制客户端行为。

核心能力：
- 启动/终止紫鸟客户端进程
- 获取店铺列表
- 打开/关闭店铺（打开时返回 CDP 调试端口）
- 更新浏览器内核

### ziniao_mcp

**职责**：MCP 服务器，对外暴露工具供 AI Agent 调用。

#### server.py — 入口与配置

- 解析三层配置（环境变量 > 命令行 > YAML）
- 创建 `ZiniaoClient` 和 `SessionManager` 实例
- 注册所有工具模块
- 通过 FastMCP 启动 MCP（stdio）服务

#### session.py — 会话管理

`SessionManager` 是核心协调层，管理紫鸟与 Chrome 两类浏览器会话：

1. **紫鸟客户端生命周期**：自动检测客户端是否运行，按需启动
2. **Chrome 生命周期**：`launch_chrome` 启动本地 Chrome 或 `connect_chrome` 连接已运行实例
3. **CDP 连接**：通过 nodriver 连接到紫鸟店铺或 Chrome 的 CDP 端口
4. **多会话**：维护 `session_id → StoreSession` 映射，紫鸟店铺与 Chrome 可同时存在，统一切换
5. **页面事件追踪**：自动监听 console、network、dialog 事件
6. **状态持久化**：将已打开会话的 CDP 信息写入 `~/.ziniao/sessions.json`，支持跨进程恢复

#### tools/ — 工具集

每个工具模块通过 `register_tools(mcp, session)` 模式注册，保持模块独立：

| 模块 | 依赖 | 说明 |
|------|------|------|
| `store.py` | `SessionManager` 紫鸟相关方法 | 紫鸟店铺生命周期管理 |
| `chrome.py` | `SessionManager` Chrome 相关方法 | Chrome 启动/连接/关闭 |
| `session_mgr.py` | `SessionManager` 统一会话方法 | 列出/切换/查看所有会话 |
| `input.py` | `session.get_active_tab()` | nodriver Tab 交互 |
| `navigation.py` | `session.get_active_tab()` + `get_active_session()` | 页面/标签页导航 |
| `emulation.py` | `session.get_active_tab()` + nodriver CDP | 设备模拟 |
| `network.py` | `session.get_active_session()` | 读取已捕获的网络数据 |
| `debug.py` | `session.get_active_tab()` + `get_active_session()` | JS 执行、截图、控制台 |
| `recorder.py` | `session.get_active_tab()` | 操作录制与回放、生成 Python 脚本 |

## 数据流

### 打开店铺

```
Agent 调用 open_store("store_123")
    │
    ▼
SessionManager._ensure_client_running()
    │ 检查客户端是否运行，否则启动
    ▼
ZiniaoClient.open_store("store_123")
    │ HTTP POST → 紫鸟客户端
    │ 返回 { debuggingPort: 9222, browserOauth: "xxx", ... }
    ▼
nodriver.Browser.create("http://127.0.0.1:9222")
    │ 建立 CDP 连接
    ▼
创建 StoreSession（browser, tabs）
    │ 绑定 console/request/response/dialog 监听
    ▼
持久化到 ~/.ziniao/sessions.json
    │
    ▼
返回 { status: "success", store_id, store_name, cdp_port, pages }
```

### 恢复已打开店铺

```
Agent 调用 connect_store("store_123")
    │
    ▼
读取 ~/.ziniao/sessions.json
    │ 获取 store_123 的 cdp_port
    ▼
httpx GET http://127.0.0.1:{cdp_port}/json/version
    │ 检查 CDP 端口是否存活
    ▼
├── 存活 → nodriver.Browser.create() → 创建 StoreSession
└── 失效 → 清理状态 → fallback 到 open_store()
```

### 页面操作

```
Agent 调用 click("#submit-btn")
    │
    ▼
session.get_active_tab()
    │ 获取当前活动店铺的活动标签页
    ▼
tab.query("#submit-btn").click()
    │ nodriver 通过 CDP 执行操作
    ▼
返回 "已点击: #submit-btn"
```

## 状态持久化

### 设计动机

MCP 服务器进程可能因 IDE 重启、网络断开等原因终止。已打开的店铺浏览器实例仍在运行（CDP 端口仍可用），需要一种机制让新进程恢复连接。

### 实现

- **存储位置**：`~/.ziniao/sessions.json`
- **文件锁**：通过 `msvcrt.locking`（Windows）/ `fcntl.flock`（Unix）实现跨进程互斥
- **原子更新**：`_update_state_file()` 在同一把锁内完成 read-modify-write
- **健康检查**：`_is_cdp_alive()` 通过 HTTP GET `/json/version` 验证端口连通性
- **自动清理**：`get_persisted_stores()` 读取时自动清理失效记录

### 状态文件结构

```json
{
  "store_123": {
    "store_id": "store_123",
    "store_name": "我的亚马逊店铺",
    "cdp_port": 9222,
    "browser_oauth": "oauth_xxx",
    "opened_at": 1717200000.0
  }
}
```

## 配置解析优先级

```
环境变量 (ZINIAO_*)     ← 最高优先级，适合 CI/CD 和 MCP 集成
    ↓
命令行参数 (--company)  ← 中等优先级，适合手动运行
    ↓
config.yaml             ← 最低优先级，适合本地开发
```

`_resolve_config()` 按此顺序合并，对每个配置项取第一个非空值。
