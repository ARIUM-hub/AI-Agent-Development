# 复核待办快捷筛选设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话分析、批量上传、人工复核、最近记录筛选、筛选导出 CSV、导出筛选条件提示、真实导出数量预估、运营概览和记录详情复制。当前“最近记录”区域已经有 `复核状态` 下拉框，支持筛选 `未复核`、`已认可` 和 `已修正`。

但运营人员进入工作台时，最常见的下一步是先处理还没有人工确认的客户问题。现在他们需要先找到筛选栏，再打开复核状态下拉框，再选择 `未复核`。这个路径可用，但不像一个“待办入口”。本轮目标是在最近记录区域增加一个轻量快捷入口，让运营人员一键进入待复核工作流。

## 目标

- 在“最近记录”区域新增 `只看待复核` 快捷按钮。
- 快捷按钮显示当前页面最近记录中的待复核数量，例如 `只看待复核（3）`。
- 点击按钮后，把现有 `#feedback-filter` 设置为 `unreviewed`。
- 点击按钮后复用现有本地筛选逻辑，刷新 `#filter-count`、空状态、导出筛选条件提示和真实导出数量预估。
- 当当前复核状态筛选已经是 `unreviewed` 时，按钮呈现激活态。
- 再次点击激活态按钮时，清除复核状态筛选，恢复为全部复核状态，同时保留平台、关键词、问题类型和责任方等其他筛选条件。
- 现有 `清空` 按钮继续清空全部筛选，并让快捷按钮退出激活态。
- README 补充说明可以用 `只看待复核` 快速进入人工复核队列。

## 非目标

- 不新增后端接口。
- 不改变 JSONL 存储结构或反馈保存逻辑。
- 不改变“最近记录”按时间倒序展示的行为。
- 不新增独立待办页面或重复记录列表。
- 不改变现有 `feedback-filter` 下拉框选项。
- 不改变 CSV 导出接口或导出参数语义。
- 不调用模型，不增加供应商请求。

## 推荐方案

在最近记录筛选表单中增加一个快捷按钮：

```html
<button class="secondary-action review-queue-toggle" type="button" data-review-queue-toggle>
  只看待复核（0）
</button>
```

前端新增：

- `bindReviewQueueToggle()`：绑定按钮点击。
- `toggleReviewQueueFilter()`：如果 `#feedback-filter` 当前不是 `unreviewed`，设置为 `unreviewed`；如果已经是 `unreviewed`，设置为空字符串。
- `updateReviewQueueToggle()`：统计当前页面 `#recent-records .record[data-feedback-status="unreviewed"]` 的数量，更新按钮文案和激活态。

点击快捷按钮后调用现有链路：

```text
applyRecordFilters()
updateExportFilterSummary()
updateExportCountPreview()
updateReviewQueueToggle()
```

为了避免重复代码，可以把现有筛选变化后的联动刷新抽成小函数，例如 `refreshRecordFilterViews()`，统一负责：

- `applyRecordFilters()`
- `updateExportFilterSummary()`
- `updateExportCountPreview()`
- `updateReviewQueueToggle()`

`bindRecordFilters()` 的 input/change、`resetRecordFilters()`、平台分布下钻和快捷按钮点击都调用这个统一函数。这样后续增加更多筛选联动时，不容易漏掉某个提示。

## 展示文案

默认：

```text
只看待复核（3）
```

没有待复核记录：

```text
只看待复核（0）
```

按钮激活态：

```text
只看待复核（3）
```

激活态通过样式表达，例如按钮增加 `is-active` class，并设置 `aria-pressed="true"`。

## 备选方案

方案 A：新增独立“复核待办”区块。入口更醒目，但会和最近记录重复展示同一批数据，页面信息密度上升，也会引入额外的空状态和详情复制绑定逻辑，因此不采用。

方案 B：默认把未复核记录排在最近记录顶部。运营路径更短，但会改变“最近记录”按时间倒序的直觉，且可能让用户误解记录时间顺序，因此不采用。

方案 C：只在运营概览的复核状态分布中支持点击 `未复核` 下钻。这个方向有价值，但入口位置离“最近记录”操作区较远；本轮先做最近记录区域内的一键待办入口。

## 数据流

1. 页面渲染最近记录和筛选栏。
2. 页面初始化时 `bindReviewQueueToggle()` 绑定快捷按钮。
3. `updateReviewQueueToggle()` 统计当前页面最近记录中的 `data-feedback-status="unreviewed"` 数量。
4. 用户点击 `只看待复核`。
5. 前端把 `#feedback-filter` 设置为 `unreviewed`。
6. 前端执行统一筛选刷新，最近记录只显示未复核记录。
7. 导出筛选条件提示显示 `复核状态：未复核`。
8. 真实导出数量预估按 `feedback_status=unreviewed` 请求后端计数。
9. 用户再次点击激活态按钮。
10. 前端清空 `#feedback-filter`，保留其他筛选条件，并重新刷新视图。
11. 用户点击 `清空` 时，所有筛选清空，快捷按钮退出激活态。

## 错误处理

- 快捷按钮不存在：绑定函数直接返回，不影响现有筛选。
- `#feedback-filter` 不存在：点击函数直接返回，不抛错。
- 最近记录列表为空：按钮显示 `只看待复核（0）`。
- 页面新增单条分析记录：新记录默认为 `unreviewed`，刷新后待复核数量同步增加。
- 人工反馈保存成功后：当前页面已有记录卡片不会立即改变复核状态；本轮不改反馈保存后的卡片状态同步，用户刷新页面后状态会来自后端记录。后续可单独优化反馈保存后的即时状态更新。
- 导出数量预估失败：沿用现有 `预计数量暂不可用` 降级，不影响待复核筛选。

## 测试策略

- `tests/test_app.py` 更新首页 HTML 测试，确认存在 `data-review-queue-toggle`、`review-queue-toggle`、`aria-pressed="false"` 和默认文案 `只看待复核`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认包含 `bindReviewQueueToggle`、`toggleReviewQueueFilter`、`updateReviewQueueToggle`、`refreshRecordFilterViews`、`data-review-queue-toggle`、`aria-pressed` 和 `is-active`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认快捷按钮会设置 `feedbackFilter.value = "unreviewed"`，并且重复点击会清空复核状态。
- `tests/test_app.py` 更新静态 CSS hook 测试，确认包含 `.review-queue-toggle` 和 `.review-queue-toggle.is-active`。
- README 补充说明 `只看待复核` 会复用当前筛选与导出预估能力。
- 全量测试确认现有分析、上传、批量、反馈、最近记录筛选、筛选导出、导出条件提示、导出数量预估、运营概览、平台下钻和记录详情复制不受影响。

## 验收标准

- 页面出现 `只看待复核（N）` 快捷按钮。
- N 等于当前页面最近记录中未复核记录数量。
- 点击按钮后，复核状态下拉框变为 `未复核`。
- 点击按钮后，最近记录列表只显示未复核记录。
- 点击按钮后，导出筛选条件提示和预计导出数量同步刷新。
- 按钮在 `unreviewed` 筛选状态下呈激活态并设置 `aria-pressed="true"`。
- 再次点击激活态按钮后，只清除复核状态筛选，保留其他筛选条件。
- 点击现有 `清空` 后，快捷按钮退出激活态。
- 不新增后端接口，不改变导出 CSV 和 JSONL 存储行为。
- 全量测试通过。

## 后续可扩展

- 人工反馈保存成功后，立即更新当前记录卡片的 `data-feedback-status` 和待复核数量。
- 在运营概览的 `未复核` 分布项上支持点击下钻到待复核筛选。
- 增加“下一条待复核”跳转按钮。
- 支持按平台拆分待复核队列。
