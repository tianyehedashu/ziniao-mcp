---
name: amazon-operations
description: 通过紫鸟浏览器自动化执行亚马逊卖家后台操作。当用户需要管理亚马逊 Listing、查看订单、分析广告数据、或执行其他亚马逊 Seller Central 操作时使用此技能。
allowed-tools: Bash(ziniao:*), ziniao-*
---

## 亚马逊 Seller Central 导航

### 常用页面 URL

| 页面 | URL |
|------|-----|
| 卖家后台首页 | `https://sellercentral.amazon.com/home` |
| 库存管理 | `https://sellercentral.amazon.com/inventory` |
| 订单管理 | `https://sellercentral.amazon.com/orders-v3` |
| 广告管理 | `https://advertising.amazon.com/cm/campaigns` |
| 业务报告 | `https://sellercentral.amazon.com/business-reports` |
| 品牌分析 | `https://sellercentral.amazon.com/brand-analytics/dashboard` |

不同站点的域名前缀不同（如 `.co.uk`、`.co.jp`、`.de`），操作前通过 `take_snapshot` 确认当前站点。

### 导航流程

```
1. ziniao open-store "<store_id>"      → 打开/恢复目标店铺
2. ziniao --store "<store_id>" navigate "目标URL"
3. ziniao --store "<store_id>" wait "关键元素选择器"
4. ziniao --store "<store_id>" snapshot --interactive
```

Agent 规则：不要依赖 daemon 的 active session；亚马逊多店、多站点、广告/库存等长流程必须每条命令带 `--store <store_id>` 或 `--session <session_id>`。`session switch` 仅用于人工交互调试。并发任务前用 `ziniao session health` 检查会话，必要时用 `ziniao cluster acquire --session <id> --ttl 600` 记录租约。

## 常见操作流程

### Listing 管理

**查看 Listing 列表**：
1. 导航到库存管理页面
2. `take_snapshot` 获取 Listing 表格结构
3. 使用 `evaluate_script` 提取表格数据（如 ASIN、标题、价格、库存）

**编辑 Listing**：
1. 在库存列表中 `click` 目标商品的编辑链接
2. `wait_for` 等待编辑页面加载
3. `take_snapshot` 分析表单结构
4. 使用 `fill` 或 `fill_form` 修改字段
5. `take_screenshot` 确认修改内容
6. 向用户确认后 `click` 提交按钮

### 订单处理

**查看订单**：
1. 导航到订单管理页面
2. 使用日期筛选器或搜索框定位目标订单
3. `take_snapshot` 获取订单详情

**批量操作**：
1. 使用 `evaluate_script` 获取订单列表数据
2. 逐条处理，每条操作后验证结果

### 广告数据分析

1. 导航到广告管理页面
2. 设置日期范围和筛选条件
3. `take_snapshot` 或 `evaluate_script` 提取广告指标数据
4. 汇总分析结果呈现给用户

## 页面结构识别技巧

亚马逊后台页面通常使用以下模式：

- **表格数据**：`<table>` 或 `<div>` 网格布局，用 `evaluate_script` 批量提取效率更高
- **表单字段**：通常有 `name` 或 `id` 属性，优先用这些作为选择器
- **动态加载**：很多内容通过 AJAX 加载，操作后需要 `wait_for` 等待更新
- **弹窗确认**：部分操作会弹出确认对话框，用 `handle_dialog` 预设处理策略

## 多站点操作

跨境电商通常运营多个站点（US、UK、JP、DE 等），每个站点对应不同的店铺：

1. `list_stores` 查看所有店铺，通过 `siteName` 字段识别站点
2. 按站点分组操作，每条命令固定 `--store` / `--session`
3. 注意不同站点的语言和页面结构可能有差异

## 注意事项

- **操作确认**：涉及价格修改、库存调整、Listing 上下架等操作前，必须向用户确认
- **频率控制**：避免过于频繁的页面操作，适当添加等待时间
- **数据准确性**：从页面提取的数据需要交叉验证，页面结构可能随亚马逊更新而变化
- **登录状态**：紫鸟浏览器会维护店铺的登录状态，通常不需要手动登录
