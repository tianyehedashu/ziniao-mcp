# Site Repos & Skills

站点预设仓库管理（repos）与 AI Agent 技能发现（skills）。

## 概述

- **Repos**：Git 仓库作为站点预设的远程来源，CLI 自动克隆/更新到本地。
- **Skills**：遵循 [agentskills.io](https://agentskills.io) 规范的 `SKILL.md` 文件，为 AI Agent 提供站点上下文知识。
- **官方仓库**：`site-hub`（`https://github.com/tianyehedashu/site-hub.git`），首次使用时自动拉取，无需手动 `add`。

## Repo 管理

### 自动初始化

`scan_repos()` 和 `scan_skills()` 内部调用 `ensure_official_repo()`：若 `site-hub` 未注册则自动添加。用户首次执行任何 site 命令时自动完成，无需手动干预。

### 命令

```bash
# 查看已注册仓库
ziniao site repos

# 添加自定义仓库
ziniao site add <git-url>

# 更新所有仓库（git pull）
ziniao site update

# 移除仓库
ziniao site remove <name>
```

### 数据存储

| 路径 | 用途 |
|------|------|
| `~/.ziniao/repos/repos.json` | 仓库注册表（name、url、branch） |
| `~/.ziniao/repos/<name>/` | 克隆的仓库内容 |

## Skills 发现

### 目录结构

遵循 agentskills.io 嵌套布局，一个站点可有多个 skill：

```
site-hub/
  rakuten/
    skills/
      rakuten-ads/SKILL.md
      rakuten-reviews/SKILL.md
    rpp-search.json
    cpa-reports-search.json
    ...
  skills/
    site-development/SKILL.md
```

也兼容旧版扁平布局 `<site>/SKILL.md`。

### SKILL.md 格式

```yaml
---
name: rakuten-ads
description: 简短描述（用于 skills 列表显示和 AI 触发匹配）
allowed-tools: Bash(ziniao:*)
---

# 标题

正文：详细的使用指南、API 说明、示例命令等。
```

`parse_skill_meta()` 解析 YAML frontmatter，支持 UTF-8 BOM（`utf-8-sig`）。

### 命令

```bash
# 列出所有已发现的 skills
ziniao site skills

# 查看某个 skill 的完整内容
ziniao site skills rakuten-ads

# JSON 模式（适用于程序化调用）
ziniao --json site skills
```

### 输出示例

```
$ ziniao site skills
  rakuten-ads          Fetch Rakuten RMS advertising reports ...
  rakuten-reviews      Download and analyze Rakuten product review CSV ...

  Total: 2  |  Details: ziniao site skills <name>
```

```
$ ziniao --json site skills
{
  "success": true,
  "data": {
    "skills": [
      {"name": "rakuten-ads", "description": "...", "path": "..."},
      {"name": "rakuten-reviews", "description": "...", "path": "..."}
    ],
    "count": 2
  }
}
```

## 现有 Skills

| Skill | 站点 | 说明 |
|-------|------|------|
| `rakuten-ads` | Rakuten RMS | 广告报表：RPP 搜索广告、TDA 展示广告、CPA、优惠券效果 |
| `rakuten-reviews` | Rakuten RMS | 评论 CSV 下载与分析 |
| `site-development` | — | 站点适配器开发指南（6 步工作流、3 层认证、JSON 字段参考） |

## 架构

### 发现优先级

```
user-local (~/.ziniao/sites/)
  → repos (~/.ziniao/repos/)
    → entry_points (plugin system)
      → builtin (package bundled)
```

### 关键文件

| 文件 | 职责 |
|------|------|
| `ziniao_mcp/sites/repo.py` | 仓库管理、skills 扫描、`ensure_official_repo()` |
| `ziniao_mcp/sites/__init__.py` | 预设发现、加载、渲染 |
| `ziniao_mcp/cli/commands/site_cmd.py` | `site` 子命令组（list/show/skills/add/update/remove/repos/enable/disable） |

### 与主项目的关系

`site-hub` 作为 git submodule 存在于项目中（`site-hub/`），仅供 IDE 查看/编辑，**不参与运行时扫描**。运行时只扫描 `~/.ziniao/repos/` 下的克隆目录，两者完全独立。

## 用户级 Skill 管理（`ziniao skill`）

### 概述

Skills 发现于 repos（`~/.ziniao/repos/`），但要被 AI agent 使用，需要安装到 agent 的全局 skills 目录。`ziniao skill` 提供了完整的用户级管理：

```bash
ziniao skill agents              # 查看支持的 agent 及其目录
ziniao skill list                # 列出所有可安装的 skills
ziniao skill install <name>      # 安装到默认 agent (cursor)
ziniao skill install <name> -a trae   # 安装到指定 agent
ziniao skill install <name> -a all    # 安装到所有 agent
ziniao skill installed           # 查看已安装的 skills（默认 agent）
ziniao skill installed -a all    # 查看所有 agent 的已安装 skills
ziniao skill remove <name>       # 从默认 agent 移除
ziniao skill remove <name> -a all    # 从所有 agent 移除
```

### 支持的 Agent

| Agent | 全局目录 | 标识 |
|-------|---------|------|
| Trae | `~/.trae/skills/` | `trae` |
| Cursor | `~/.cursor/skills/` | `cursor`（默认） |
| Claude Code | `~/.claude/skills/` | `claude` |
| GitHub Copilot | `~/.github/skills/` | `copilot` |
| Windsurf | `~/.windsurf/skills/` | `windsurf` |
| OpenAI Codex | `~/.codex/skills/` | `codex` |

### 安装机制

`install` 通过 symlink/junction 将 repo 中的 skill 目录链接到 agent 的全局 skills 目录。skill 源文件仍在 `~/.ziniao/repos/` 中，agent 目录只是指向它。

`remove` 只移除 symlink/junction，不删除源文件，也不会误删 agent 原有的非 symlink skills。

### 示例

```bash
# 安装 rakuten-ads 到所有 agent
$ ziniao skill install rakuten-ads -a all
  ✓ rakuten-ads → trae (C:\Users\...\.trae\skills)
  ✓ rakuten-ads → cursor (C:\Users\...\.cursor\skills)
  ✓ rakuten-ads → claude (C:\Users\...\.claude\skills)
  ...

# 查看已安装
$ ziniao skill installed
  cursor (C:\Users\...\.cursor\skills):
    [→] rakuten-ads
    [ ] ziniao-cli
    ...

# 移除
$ ziniao skill remove rakuten-ads -a all
  ✓ Removed rakuten-ads from cursor
  ...
```
