# 分析记录汇总看板设计

## 背景

客户使用问题归因智能体已经具备单条分析、批量分析、人工复核、CSV 导出和最近记录筛选能力。记录可以被创建、复核、查找和带出表格后，运营或数据分析专员下一步需要快速判断：当前问题主要集中在哪些类型、责任方分布如何、判断证据是否充分、复核进度怎么样。

本轮目标是在不引入数据库、图表库或复杂后台的前提下，为工作台增加轻量运营概览。

## 已确认范围

- 新增后端接口：`GET /api/records/summary`。
- 统计对象：当前本地 JSONL 中的全部分析记录。
- 统计维度：
  - 问题类型。
  - 优先责任方。
  - 证据强度。
  - 复核状态。
- 首页新增“运营概览”区域。
- 概览展示总记录数、已复核数、已修正数和各维度 Top 统计。
- 使用原生 HTML、CSS、JavaScript 渲染，不引入图表库。
- 不接入模型供应商，不做批量模型请求。

## 非目标

- 不做时间范围筛选。
- 不做趋势折线图。
- 不做 SKU、ASIN、店铺或产品维度统计。
- 不做数据库迁移。
- 不做复杂 BI 报表。
- 不改变 CSV 导出语义。
- 不改变最近记录本地筛选行为。

## 推荐方案

采用“后端汇总 API + 前端轻量渲染”方案。

后端从 `AnalysisStore.list_records()` 读取已合并反馈的记录，计算汇总 JSON。前端页面加载时调用 `/api/records/summary`，使用卡片和横向条形列表展示结果。这样可以避免模板承担统计逻辑，也为后续加时间筛选或更多维度预留清晰接口。

## 后端接口

新增：

```text
GET /api/records/summary
```

响应结构：

```json
{
  "total_records": 12,
  "reviewed_records": 8,
  "corrected_records": 3,
  "issue_categories": [{"value": "function_use", "count": 5}],
  "responsibilities": [{"value": "customer_service_training", "count": 6}],
  "evidence_strengths": [{"value": "likely", "count": 7}],
  "feedback_statuses": [{"value": "accepted", "count": 5}]
}
```

排序规则：

- 各维度按 `count` 降序。
- 数量相同按 `value` 字母序升序。
- 空值统一归为 `unknown`。

复核状态规则：

- `unreviewed`：`feedback` 为空。
- `accepted`：`feedback.accepted` 为 `true`。
- `corrected`：`feedback` 存在且 `accepted` 为 `false`。

## 后端模块设计

新增一个轻量汇总模块：

```text
src/customer_issue_agent/summary.py
```

职责：

- 接收 `list[dict]` 形式的记录。
- 计算基础总数。
- 计算维度计数。
- 返回适合 API 直接 JSON 序列化的 dict。

不把汇总逻辑写进 `app.py`，避免 FastAPI 路由文件继续膨胀。

## 前端设计

首页在工作台输入/结果区域和“最近记录”之间增加“运营概览”区。

区域内容：

- 总记录数。
- 已复核数。
- 已修正数。
- 问题类型 Top 列表。
- 责任方 Top 列表。
- 证据强度分布。
- 复核状态分布。

渲染方式：

- 页面初始 HTML 提供空容器和加载提示。
- JavaScript 页面加载后请求 `/api/records/summary`。
- 成功后渲染统计卡片。
- 失败时显示“概览加载失败，请刷新页面重试”。
- 无记录时显示 0 和“暂无数据”。

标签显示：

- 前端复用现有枚举中文映射。
- 复核状态新增映射：`unreviewed` 为“未复核”，`accepted` 为“已认可”，`corrected` 为“已修正”。

## 错误处理与降级

- JSONL 文件不存在：接口返回全 0 和空列表。
- 记录缺失字段：对应维度按 `unknown` 统计。
- 前端请求失败：页面显示中文错误，不影响分析、筛选或导出功能。
- JavaScript 不可用：页面仅不显示动态概览，不影响核心功能。

## 测试策略

自动测试覆盖：

- 汇总模块能统计总记录数、已复核数和已修正数。
- 汇总模块能按问题类型、责任方、证据强度和复核状态计数排序。
- 空记录返回全 0 和空列表。
- `/api/records/summary` 返回汇总 JSON。
- 首页包含运营概览容器和加载提示。
- 静态 JS 包含汇总加载和渲染函数。
- 静态 CSS 包含汇总看板样式。

回归验证：

- 全量 `python -m pytest -q` 通过。
- 单条分析、批量分析、人工反馈、CSV 导出、最近记录筛选仍可用。

## 后续扩展

- 增加时间范围筛选。
- 增加按平台统计。
- 增加当前筛选结果汇总。
- 增加 SKU、ASIN、店铺维度。
- 增加趋势图和异常提醒。
