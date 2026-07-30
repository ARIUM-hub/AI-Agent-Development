# 筛选条件 CSV 导出设计

## 背景

客户使用问题归因智能体已经支持单条分析、批量分析、人工反馈、最近记录筛选、全量 CSV 导出和运营概览。当前“最近记录”筛选只影响页面上展示的最近 10 条记录，而“导出 CSV”始终导出本地 JSONL 中的全部记录。

运营或数据分析专员在复盘时，经常需要把某个平台、某类问题、某个责任方或某种复核状态的记录单独导出到 Excel、飞书表格或 BI 工具中继续处理。本轮目标是在保持现有全量导出不变的前提下，增加一个轻量的“按条件导出 CSV”能力。

## 目标

- 新增支持筛选参数的 CSV 导出能力。
- 筛选范围覆盖当前本地 JSONL 中的全部分析记录，不限于页面最近 10 条。
- 支持按平台、问题类型、责任方、复核状态和关键词筛选。
- 继续复用现有 CSV 字段、UTF-8 BOM 和下载响应格式。
- 在最近记录筛选栏中增加“导出筛选 CSV”入口，读取当前筛选条件生成下载链接。

## 非目标

- 不改变现有 `GET /api/records/export.csv` 全量导出语义。
- 不做 Excel `.xlsx` 导出。
- 不做保存筛选条件。
- 不做服务端分页、数据库查询或异步导出任务。
- 不把页面当前 DOM 的最近 10 条当作导出范围。
- 不调用模型，不增加供应商请求。

## 推荐方案

在后端新增一个记录筛选 helper，输入 `AnalysisStore.list_records()` 返回的记录列表和筛选条件，输出过滤后的记录列表。CSV 端点继续调用 `build_records_csv()` 生成文件，只是在生成前按 URL 查询参数过滤记录。

前端在现有筛选栏旁边增加一个普通按钮。按钮不会提交表单，而是在点击时读取 `record-search`、`issue-filter`、`responsibility-filter`、`feedback-filter` 的当前值，拼接到 `/api/records/export.csv` 查询参数后跳转下载。

这个方案的优点是改动小、可测试、和现有功能边界一致。后端筛选保证导出覆盖全部 JSONL 记录，前端按钮只是一个便利入口。即使 JavaScript 不可用，原有全量导出仍可使用。

## 备选方案

方案 A：只导出页面当前可见的最近记录。实现最简单，但范围只有最近 10 条，容易让用户误以为已经导出全部符合条件的历史记录，因此不采用。

方案 B：新增独立端点 `/api/records/export-filtered.csv`。语义更显式，但会让两个 CSV 端点产生重复逻辑。现阶段使用同一个 `/api/records/export.csv` 加查询参数更轻量。

方案 C：先做 `.xlsx` 筛选导出。对运营更友好，但会引入表格样式、列宽和依赖复杂度，不适合当前 MVP 小步迭代。

## 筛选参数

`GET /api/records/export.csv` 新增可选查询参数：

- `platform`：平台关键词，大小写不敏感，匹配 `analysis.request.platform`。
- `issue_category`：精确匹配 `analysis.attribution.issue_category`。
- `responsibility`：精确匹配 `analysis.attribution.primary_responsibility`。
- `feedback_status`：精确匹配人工复核状态，取值为 `unreviewed`、`accepted`、`corrected`。
- `q`：全文关键词，大小写不敏感，匹配记录 ID、平台、报告、客户问题、问题类型、责任方、证据强度、推荐动作、待补充信息和人工备注。

所有参数都是可选的。多个参数同时存在时使用 AND 逻辑。

## 反馈状态规则

- 没有反馈对象：`unreviewed`。
- `feedback.accepted` 为真：`accepted`。
- 有反馈对象且 `feedback.accepted` 为假：`corrected`。

该规则与运营概览中的反馈状态规则保持一致。

## 用户界面

最近记录筛选栏新增“导出筛选 CSV”按钮。按钮位于“清空”按钮附近，使用已有 `secondary-action` 样式。

点击按钮时：

1. 读取当前筛选控件。
2. 将关键词映射为 `q`，问题类型映射为 `issue_category`，责任方映射为 `responsibility`，复核状态映射为 `feedback_status`。
3. 忽略空值参数。
4. 设置 `window.location.href` 为生成后的导出 URL。

当前页面的筛选仍然只影响最近 10 条记录显示；导出筛选则由服务端基于全部 JSONL 记录执行。README 需要明确这个差异。

## 错误处理

- JSONL 文件不存在：导出只有表头的 CSV。
- 筛选后没有匹配记录：导出只有表头的 CSV。
- 记录缺少字段：按空字符串处理，不影响其它记录导出。
- 未知的 `feedback_status`：不匹配任何记录，导出只有表头的 CSV。

## 测试策略

- 单元测试覆盖筛选 helper：平台关键词、枚举精确匹配、反馈状态、全文关键词、空条件、空结果。
- API 测试覆盖带查询参数的 `/api/records/export.csv`：只导出匹配记录，并保留 UTF-8 BOM 和 CSV 表头。
- 页面测试覆盖“导出筛选 CSV”按钮和前端 JS 钩子。
- 回归测试确认不带查询参数时仍导出全部记录。

## 验收标准

- 用户可以在筛选栏设置条件后点击“导出筛选 CSV”下载符合条件的全部本地记录。
- 原有“导出 CSV”仍导出全部记录。
- 导出的 CSV 仍使用现有字段和 UTF-8 BOM。
- 筛选为空结果时下载只有表头的 CSV。
- 全量测试通过。

## 后续可扩展

- 增加时间范围筛选。
- 增加当前批次导出。
- 增加 `.xlsx` 导出并设置列宽、冻结首行和中文样式。
- 增加导出字段配置。
