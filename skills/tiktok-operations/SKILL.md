---
name: tiktok-operations
description: 通过紫鸟浏览器自动化执行 TikTok Shop 跨境卖家后台操作。当用户需要管理 TikTok Shop 商品、查看订单、设置营销活动、分析店铺数据、或执行其他 TikTok Shop Seller Center 操作时使用此技能。
---

## TikTok Shop Seller Center 导航

### 域名说明

TikTok Shop 跨境卖家后台使用两个主要域名：

| 域名 | 用途 |
|------|------|
| `seller.tiktokshopglobalselling.com` | 全球卖家入口、首页、下载中心 |
| `seller.tiktokglobalshop.com` | 卖家中心核心功能（商品/订单/数据等） |

所有页面通过 `shop_region` 参数区分市场站点（如 `?shop_region=PH` 为菲律宾）。

### 常用页面 URL

| 页面 | URL |
|------|-----|
| 卖家首页 | `https://seller.tiktokshopglobalselling.com/homepage?shop_region={region}` |
| 商品管理 | `https://seller.tiktokglobalshop.com/product/manage?shop_region={region}` |
| 订单管理 | `https://seller.tiktokglobalshop.com/order?shop_region={region}` |
| 数据罗盘 | `https://seller.tiktokglobalshop.com/compass/data-overview?shop_region={region}` |
| 营销中心 | `https://seller.tiktokglobalshop.com/promotion?shop_region={region}` |
| 达人合作 | `https://seller.tiktokglobalshop.com/affiliate?shop_region={region}` |
| 财务中心 | `https://seller.tiktokglobalshop.com/finance?shop_region={region}` |
| 客服管理 | `https://seller.tiktokglobalshop.com/customer-service?shop_region={region}` |
| 店铺设置 | `https://seller.tiktokglobalshop.com/account/shop?shop_region={region}` |
| 下载中心 | `https://seller.tiktokshopglobalselling.com/download-center` |

`{region}` 常见值：`PH`（菲律宾）、`TH`（泰国）、`VN`（越南）、`MY`（马来西亚）、`SG`（新加坡）、`ID`（印尼）、`UK`（英国）、`US`（美国）。

操作前通过 `take_snapshot` 确认当前页面和站点区域。

### 导航流程

```
1. connect_store("store_id")         → 连接目标店铺
2. navigate_page("目标URL")           → 导航到目标页面
3. wait_for("关键元素选择器")           → 等待页面加载
4. take_snapshot()                    → 获取页面结构
```

## 常见操作流程

### 商品管理

**查看商品列表**：
1. 导航到商品管理页面
2. `take_snapshot` 获取商品表格结构
3. 使用 `evaluate_script` 提取商品数据（如商品名、SKU、价格、库存、状态）

**上传/编辑商品**：
1. 在商品列表中 `click` 目标商品的编辑按钮，或点击"添加商品"
2. `wait_for` 等待编辑页面加载
3. `take_snapshot` 分析表单结构
4. 使用 `fill` 或 `fill_form` 填写/修改字段（商品名、描述、价格、库存、规格等）
5. 上传商品图片时需通过文件上传控件处理
6. `take_screenshot` 确认修改内容
7. 向用户确认后 `click` 提交按钮

**批量操作**：
1. TikTok Shop 支持 Excel 批量上传，可引导用户通过下载中心获取模板
2. 也可逐条使用 `evaluate_script` 提取列表数据后批量处理

### 订单处理

**查看订单**：
1. 导航到订单管理页面
2. 通过标签页切换订单状态（待发货/待处理/已完成/已取消）
3. `take_snapshot` 获取订单列表和详情

**订单发货**：
1. 在待发货订单列表中定位目标订单
2. `click` 发货按钮
3. `wait_for` 等待发货弹窗/页面加载
4. `fill` 物流单号、选择物流方式
5. 向用户确认后 `click` 确认发货

**订单筛选**：
- URL 支持查询参数筛选：`sort_field`、`sort_type`、`subTab`、`tab`
- 示例：`/order?sort_field=7&sort_type=1&subTab=to_ship_all&tab=to_ship&shop_region=PH`

### 营销活动

**设置促销**：
1. 导航到营销中心页面
2. `take_snapshot` 查看可用的营销工具（优惠券/折扣/限时特卖等）
3. `click` 创建新活动
4. `fill_form` 填写活动信息（活动名称、时间、折扣力度、适用商品）
5. 向用户确认后提交

**达人合作（Affiliate）**：
1. 导航到达人合作页面
2. 设置佣金计划或查看达人带货数据
3. 可通过 `evaluate_script` 提取达人销售数据

### 数据分析

1. 导航到数据罗盘页面（Compass）
2. 设置日期范围和维度筛选
3. `take_snapshot` 或 `evaluate_script` 提取关键指标（GMV、订单数、转化率、流量等）
4. 汇总分析结果呈现给用户

### 财务管理

1. 导航到财务中心
2. `take_snapshot` 获取结算信息（收入、佣金、平台费用、退款等）
3. 使用 `evaluate_script` 提取交易明细数据

## 页面结构识别技巧

TikTok Shop 卖家后台页面通常使用以下模式：

- **表格数据**：商品/订单列表使用表格或卡片布局，用 `evaluate_script` 批量提取效率更高
- **标签页导航**：订单状态、商品状态等通过顶部标签页切换，注意 `click` 后需 `wait_for` 等待内容刷新
- **表单字段**：使用 Ant Design 等 UI 组件库，输入框通常嵌套在 `.ant-form-item` 中
- **动态加载**：大量内容通过异步加载，操作后需要 `wait_for` 等待更新
- **弹窗/抽屉**：确认操作、编辑详情常使用 Modal/Drawer 组件，用 `handle_dialog` 或等待弹窗元素出现后操作

## 多站点操作

TikTok Shop 跨境卖家可运营多个市场站点（PH、TH、VN、MY、SG 等），同一账号下通过 `shop_region` 切换：

1. `list_stores` 查看所有店铺
2. 通过 `navigate_page` 切换 `shop_region` 参数切换市场
3. 不同市场的商品、订单、数据独立管理
4. 注意不同市场的语言、货币、物流和合规要求差异

## 注意事项

- **操作确认**：涉及商品上下架、价格修改、库存调整、订单发货等操作前，必须向用户确认
- **频率控制**：避免过于频繁的页面操作，适当添加等待时间
- **数据准确性**：从页面提取的数据需要交叉验证，页面结构可能随 TikTok Shop 更新而变化
- **登录状态**：紫鸟浏览器会维护店铺的登录状态，通常不需要手动登录
- **合规风险**：不同市场有不同的商品合规要求，自动化操作前注意合规审核
