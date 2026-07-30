# 平台概览下钻筛选设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话分析、批量上传、人工复核、最近记录筛选、筛选导出 CSV、时间范围筛选和运营概览。最近两轮已经补齐了“运营概览”的平台分布，以及“最近记录”的平台筛选输入框。

当前用户能在概览中看到 Amazon、TikTok Shop、Shopee 等平台的问题量分布，也能在最近记录筛选栏手动输入平台进行筛选。但这两个能力还没有连接起来：用户看到某个平台问题量高时，需要手动复制或输入平台名称，才能查看最近记录里的相关样本。

## 目标

- 在“运营概览”的“平台分布”卡片中支持点击平台行。
- 点击平台后自动填入最近记录筛选栏的 `#platform-filter`。
- 点击后复用现有 `applyRecordFilters()` 立即筛选当前页面最近记录。
- 点击后滚动到最近记录区域，帮助用户从概览直接下钻。
- 仅平台分布启用点击；问题类型、责任方、证据强度和复核状态保持纯展示。
- 不新增后端接口，不修改 JSONL，不改变平台统计口径。
- README 补充说明可以从平台分布点击下钻筛选。

## 非目标

- 不做平台别名标准化。
- 不改变运营概览统计结果。
- 不改变 `导出筛选 CSV` 逻辑。
- 不新增服务端筛选接口。
- 不做跨页或全量记录前端加载。
- 不让问题类型、责任方、证据强度或复核状态分布变成可点击筛选。
- 不调用模型，不增加供应商请求。

## 推荐方案

扩展现有前端 `summaryDistribution(title, labelGroup, items = [])`。当 `labelGroup === "platform"` 时，把每个分布行的标签渲染成按钮：

```html
<button type="button" class="summary-filter-link" data-summary-platform-filter="Amazon">Amazon</button>
```

其他分布仍渲染为普通文本，避免用户误以为所有概览维度都能下钻。

在 `DOMContentLoaded` 中新增绑定函数 `bindSummaryPlatformFilters(document)`。由于运营概览是异步加载并用 `innerHTML` 重绘，绑定应在 `renderRecordsSummary(summary)` 渲染完成后再调用一次：

```javascript
bindSummaryPlatformFilters(container);
```

点击处理函数读取按钮上的 `data-summary-platform-filter`，把值写入 `#platform-filter`，调用现有 `applyRecordFilters()`，再滚动到 `#recent-records` 或最近记录所在 section。

## 备选方案

方案 A：点击平台后直接跳转到筛选导出 CSV。这个路径适合导出，但不适合快速查看样本，会跳出当前分析工作台，因此不采用。

方案 B：所有概览分布都支持点击筛选。长期可以扩展，但本轮只完成平台链路；如果同时支持问题类型、责任方和复核状态，需要设计多筛选状态同步，范围会变大，因此不采用。

方案 C：后端新增平台明细接口。这样可以展示全量平台记录，但会新增 API、分页和状态管理。本轮目标是小步连接现有能力，因此不采用。

## 数据流

1. 前端加载 `/api/records/summary?range=...`。
2. `renderRecordsSummary(summary)` 渲染运营概览卡片。
3. `summaryDistribution("平台分布", "platform", summary.platforms)` 为平台值生成可点击按钮。
4. 用户点击某个平台按钮。
5. 前端把平台值写入 `#platform-filter`。
6. 前端调用现有 `applyRecordFilters()`，本地筛选当前最近记录。
7. 页面滚动到最近记录区域，用户可以查看筛选后的样本。
8. 如果用户再点击 `导出筛选 CSV`，现有逻辑会带上 `platform` 参数。

## 错误处理

- 页面没有 `#platform-filter`：点击不报错，直接返回。
- 页面没有最近记录区域：仍然设置筛选并应用筛选，不执行滚动。
- 平台值为空：不写入筛选框，不触发筛选。
- 概览为空：继续展示“暂无数据 0”，不生成下钻按钮。
- 运营概览因时间范围切换重绘：重绘后重新绑定平台按钮点击事件。

## 测试策略

- `tests/test_app.py` 更新静态 JS hook 测试，确认包含 `bindSummaryPlatformFilters`、`applySummaryPlatformFilter` 和 `data-summary-platform-filter`。
- `tests/test_app.py` 更新概览 hook 测试，确认平台分布渲染使用 `summaryDistribution("平台分布", "platform", summary.platforms)`。
- `tests/test_app.py` 增加样式 hook 测试，确认存在 `.summary-filter-link` 样式。
- 全量测试确认现有分析、上传、批量、反馈、导出、最近记录筛选、平台筛选、概览时间范围和详情展开不受影响。

## 验收标准

- 平台分布中的平台名称以按钮形式呈现。
- 点击平台按钮后，最近记录平台筛选框自动填入对应平台名称。
- 点击平台按钮后，当前页面最近记录立即按平台筛选。
- 点击平台按钮后，页面滚动到最近记录区域。
- 非平台分布仍保持纯展示，不出现下钻按钮。
- 缺少筛选框或最近记录区域时点击不会报错。
- README 说明可以点击平台分布下钻筛选。
- 全量测试通过。

## 后续可扩展

- 支持问题类型、责任方和复核状态分布点击筛选。
- 支持点击平台后自动触发筛选导出。
- 在已下钻状态下显示“来自概览下钻”的提示。
- 增加平台别名标准化后，让下钻使用标准平台名。
