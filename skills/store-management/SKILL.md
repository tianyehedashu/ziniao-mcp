---
name: store-management
description: 管理紫鸟多店铺的生命周期，包括打开、连接、切换和关闭店铺。当需要管理多个店铺、恢复已打开的店铺会话、或进行批量店铺操作时使用此技能。
allowed-tools: Bash(ziniao:*), ziniao-*
---

## 店铺生命周期

```
list_stores → 获取店铺列表
    │
    ├── open_store → 打开新店铺（启动浏览器实例 + CDP 连接）
    │
    ├── connect_store → 连接已运行的店铺（恢复 CDP，不重启）
    │
    ├── 执行页面操作...
    │
    ├── close_store → 关闭单个店铺
    │
    └── stop_client → 退出客户端（关闭所有店铺）
```

## connect_store vs open_store

| 场景 | 使用 | 原因 |
|------|------|------|
| 不确定店铺是否已打开 | `connect_store` | 已运行则恢复连接，未运行则自动 fallback 到 open |
| 需要强制重启店铺 | `open_store` | 会关闭已运行的实例并重新打开 |
| MCP 进程重启后恢复 | `connect_store` | 从 `~/.ziniao/sessions.json` 恢复 CDP 信息 |
| 首次打开店铺 | 两者均可 | `connect_store` 更安全，会自动 fallback |

**推荐默认使用 `connect_store`**，除非明确需要重启。

## 多店铺管理策略

### 查看状态

```
1. list_stores          → 查看所有店铺（含 is_open 标识）
2. list_open_stores     → 仅查看已打开的店铺（经过 CDP 连通性验证）
```

### 切换店铺

当前架构下，最后一次 `connect_store` / `open_store` / `launch` / `connect` 可能改变 daemon 的活动会话。**Agent 不应把 active session 当作任务状态**：它是人工交互便利，不是并发安全的锁。

```
ziniao session switch <id>  # 仅人工交互时使用
```

Agent / 脚本默认规则：

1. 先 `ziniao --json session list` 获取目标 `session_id`。
2. 每条命令都带 `--store <store_id>` 或 `--session <session_id>`。
3. 批量、多代理、长任务不使用 `session switch` 维持状态。
4. Tab 也视为易变资源：操作前用 `tab list` / `url` / `snapshot` 验证目标页。
5. 长任务前用 `ziniao session health` 检查 CDP 端口；并发编排用 `ziniao cluster acquire --session <id> --ttl <sec>` 记录租约。

### 批量操作模式

对多个店铺执行相同操作时：

1. `list_stores` 获取目标店铺列表
2. 逐个 `open-store` / 自动恢复，并用 `--store "$id"` 固定每条命令目标
3. 每个店铺操作完成后记录结果
4. 最后汇总报告所有店铺的执行情况

注意：不要同时打开超过 5 个店铺，避免系统资源耗尽。

推荐 CLI 模式：

```bash
for id in store_001 store_002; do
    ziniao --store "$id" navigate "https://example.com"
    ziniao --store "$id" wait "body"
    ziniao --store "$id" screenshot "${id}.png"
done
```

## 会话恢复机制

已打开店铺的信息持久化在 `~/.ziniao/sessions.json`：

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

`connect_store` 的恢复流程：
1. 读取状态文件获取 CDP 端口
2. 通过 HTTP GET `/json/version` 验证端口连通性
3. 端口存活 → nodriver `Browser.create()` 恢复 CDP 连接
4. 端口失效 → 清理状态记录 → fallback 到 `open_store` 重新打开

## CLI 等效命令

上述所有操作也可通过 `ziniao` CLI 完成，适合脚本和终端环境：

| MCP 工具 | CLI 命令 |
|----------|----------|
| `list_stores` | `ziniao list-stores` |
| `open_store(id)` | `ziniao open-store <id>` |
| `close_store(id)` | `ziniao close-store <id>` |
| `connect_store(id)` | `ziniao open-store <id>` (自动恢复) |
| `start_client` | `ziniao store start-client` |
| `stop_client` | `ziniao store stop-client` |
| `browser_session(list)` | `ziniao session list` |
| `browser_session(switch)` | `ziniao session switch <id>` |
| 会话健康 | `ziniao session health` |
| 集群租约 | `ziniao cluster status/acquire/release` |

### 多店铺批量示例（CLI）

```bash
# 对所有已打开店铺截图
ziniao --json list-stores --opened-only | jq -r '.data.stores[].store_id' | while read id; do
    ziniao --store "$id" screenshot "${id}.png"
done
```

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| `list_stores` 返回空 | 检查紫鸟账号登录信息（company/username/password）是否正确 |
| `connect_store` 失败 | 店铺浏览器可能已关闭，会自动 fallback 到 `open_store` |
| 打开店铺超时 | 检查紫鸟客户端是否正常运行，网络是否通畅 |
| CDP 端口冲突 | 关闭占用端口的进程，或重启紫鸟客户端 |
