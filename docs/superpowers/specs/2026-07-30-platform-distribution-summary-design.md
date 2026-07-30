# 平台分布概览设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话分析、批量上传、人工复核、最近记录筛选、CSV 导出、时间范围筛选和运营概览。上一轮已经为平台来源输入框增加了 Amazon、TikTok Shop、Shopee、Walmart Marketplace、eBay、Shopify、AliExpress、Lazada、Temu、Shein 等常用海外电商平台预设，同时保留自定义输入。

当前运营概览能看到总记录数、复核状态、问题类型、责任方和证据强度分布，但还不能直接看到不同平台的问题量分布。对于海外电商运营场景，平台维度是判断问题集中来源、安排平台运营跟进和导出复盘时的重要入口。

## 目标

- 在运营概览中新增“平台分布”统计。
- 后端 summary 响应新增 `platforms` 数组，格式与现有分布字段一致。
- 平台来源从 `analysis.request.platform` 读取。
- 平台为空、缺失或纯空白时统一统计为 `unknown`。
- 排序规则沿用现有分布：数量降序，数量相同按值升序。
- 现有 `range=all|7d|30d` 时间范围筛选自动作用于平台分布。
- 前端复用现有分布卡片渲染能力展示平台名称和数量。
- README 补充说明运营概览包含平台分布。

## 非目标

- 不做平台别名标准化，例如不把 `tiktok` 自动合并为 `TikTok Shop`。
- 不改变历史 JSONL 记录。
- 不修改分析接口、批量接口或反馈接口。
- 不新增数据库或迁移脚本。
- 不改变 CSV 导出字段和过滤条件。
- 不接入平台 API。
- 不调用模型，不增加供应商请求。

## 推荐方案

在 `build_records_summary(records)` 内新增一个 `platforms` 计数器。遍历记录时，从 `record["analysis"]["request"]["platform"]` 读取平台来源，并复用当前 `_value()` 工具处理缺失、空白和 `None`。返回值中新增：

```python
"platforms": _rank(platforms)
```

前端 `renderRecordsSummary(summary)` 在现有 `summary-grid` 中新增：

```javascript
${summaryDistribution("平台分布", "platform", summary.platforms)}
```

`labelFor()` 对未知 label group 已经会回退显示原始值，因此平台名称无需新增映射表。这样可以直接显示 Amazon、TikTok Shop、Shopee 或用户手动输入的其他海外电商平台。

## 备选方案

方案 A：只在前端根据最近 10 条记录统计平台分布。这个方案实现快，但只覆盖当前页面记录，和运营概览“基于全部本地 JSONL 记录”的语义不一致，因此不采用。

方案 B：后端新增独立 `/api/records/platforms/summary` 接口。边界清晰，但会增加接口和前端请求数量；当前 summary 已经承担概览统计，新增字段更简单，因此不采用。

方案 C：先做平台别名标准化再统计。长期有价值，但会改变统计口径，需要设计映射、历史兼容和人工纠偏策略，不适合本轮小步增强。

## 数据流

1. 用户通过粘贴、上传或批量上传提交平台来源。
2. 分析结果仍按现有结构写入 JSONL：`analysis.request.platform`。
3. 运营概览接口读取本地 JSONL 记录。
4. `filter_records(..., range=range)` 先按时间范围过滤记录。
5. `build_records_summary()` 基于过滤后的记录统计平台分布。
6. 前端读取 `/api/records/summary?range=...` 的 `platforms` 字段。
7. 页面在“运营概览”中展示“平台分布”卡片。

## 错误处理

- 记录缺少 `analysis`、`request` 或 `platform`：平台统计为 `unknown`。
- 平台值为 `None` 或空白字符串：平台统计为 `unknown`。
- 没有任何记录：`platforms` 返回空数组，前端展示“暂无数据 0”。
- 旧记录没有平台字段：不会抛错，按 `unknown` 聚合。

## 测试策略

- `tests/test_summary.py` 增加平台分布统计测试，覆盖排序和多平台计数。
- `tests/test_summary.py` 增加空值、缺失值归为 `unknown` 的断言。
- `tests/test_app.py` 更新 summary API 测试，确认响应包含 `platforms`。
- `tests/test_app.py` 更新空 summary 测试，确认 `platforms` 为空数组。
- `tests/test_app.py` 增加静态 JS hook 断言，确认前端渲染包含“平台分布”和 `summary.platforms`。
- 全量测试确认现有分析、上传、批量、筛选、导出、时间范围和详情功能不受影响。

## 验收标准

- `/api/records/summary` 返回平台分布字段 `platforms`。
- 平台分布格式为 `[{ "value": "<platform>", "count": <number> }]`。
- 平台分布遵守现有时间范围筛选。
- 首页运营概览展示“平台分布”卡片。
- 空记录、旧记录或异常记录不会导致概览失败。
- README 明确说明运营概览包含平台分布。
- 全量测试通过。

## 后续可扩展

- 增加平台别名标准化。
- 在最近记录筛选栏增加平台筛选项。
- 在 CSV 筛选导出按钮旁展示当前平台统计摘要。
- 允许团队维护自定义平台预设列表。
