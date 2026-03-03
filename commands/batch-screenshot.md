---
name: batch-screenshot
description: 对所有已打开的紫鸟店铺当前页面进行截图，快速了解各店铺状态
---

# 批量截图

对所有已打开的店铺执行截图：

1. 调用 `list_open_stores` 获取已打开的店铺列表
2. 如果没有已打开的店铺，提示用户先打开店铺
3. 逐个处理每个已打开的店铺：
   a. `connect_store(store_id)` 切换到该店铺
   b. `list_pages` 查看当前标签页
   c. `take_screenshot` 截取当前活动页面
   d. 记录店铺名称、当前页面 URL 和截图
4. 汇总展示所有店铺的截图结果
