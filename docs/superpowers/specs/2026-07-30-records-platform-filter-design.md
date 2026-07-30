# 最近记录平台筛选设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话分析、批量上传、人工复核、最近记录筛选、CSV 导出、时间范围筛选和运营概览。当前运营概览已经新增“平台分布”，可以看到 Amazon、TikTok Shop、Shopee 等不同海外电商平台的问题量分布。

但“最近记录”筛选栏目前只支持关键词、问题类型、责任方和复核状态。用户在概览里发现某个平台问题量较高后，还需要通过关键词搜索或导出后手动筛选，操作链路不够顺。

## 目标

- 在“最近记录”筛选栏新增“平台”筛选输入框。
- 平台筛选输入框复用现有 `platform-presets`，支持常用平台预设和自由输入。
- 本地最近记录筛选基于每条记录已有的 `data-platform` 执行。
- 本地平台筛选使用大小写不敏感的包含匹配，例如输入 `tiktok` 可以匹配 `TikTok Shop`。
- `导出筛选 CSV` 同步携带 `platform` 查询参数。
- 服务端筛选导出复用现有 `filter_records(..., platform=...)` 能力。
- README 补充说明最近记录可以按平台筛选和导出。

## 非目标

- 不新增后端接口。
- 不修改 JSONL 存储结构。
- 不修改分析、批量分析或人工反馈接口。
- 不做平台别名标准化。
- 不改变运营概览的平台分布统计口径。
- 不改变原有关键词、问题类型、责任方、复核状态和时间范围筛选语义。
- 不调用模型，不增加供应商请求。

## 推荐方案

在首页模板的 `#record-filter` 表单中新增平台输入框：

```html
<label class="filter-field" for="platform-filter">
  <span>平台</span>
  <input id="platform-filter" name="platform" list="platform-presets" placeholder="全部平台">
</label>
```

前端 `applyRecordFilters()` 读取 `#platform-filter` 的值，并传给 `recordMatchesFilters()`。匹配时将输入和 `record.dataset.platform` 都转为小写后做包含匹配：

```javascript
const platform = document.getElementById("platform-filter")?.value.trim().toLowerCase() || "";
const matchesPlatform = !filters.platform || (record.dataset.platform || "").toLowerCase().includes(filters.platform);
```

`buildFilteredExportUrl()` 在平台筛选不为空时追加：

```javascript
params.set("platform", platform);
```

后端 `/api/records/export.csv` 已经接收 `platform` 参数并调用 `filter_records()`，因此本轮只补齐前端入口和测试，不需要修改服务端业务代码。

## 备选方案

方案 A：使用 `<select>` 固定平台选项。这样能减少输入差异，但会排除没有出现在预设列表里的海外电商平台，不符合当前开放输入策略，因此不采用。

方案 B：点击运营概览平台分布后自动筛选最近记录。交互更顺，但需要给分布列表增加可点击行为和状态同步，复杂度高于本轮需求，因此不采用。

方案 C：先做平台别名标准化再筛选。长期有价值，但会影响统计和导出口径，需要单独设计映射、历史兼容和人工纠偏策略，因此不纳入本轮。

## 数据流

1. 页面渲染最近 10 条记录，每条记录保留已有 `data-platform`。
2. 用户在“平台”筛选框选择预设或手动输入平台关键词。
3. 前端 `applyRecordFilters()` 读取平台、关键词、问题类型、责任方和复核状态。
4. `recordMatchesFilters()` 对当前页面记录执行组合筛选。
5. 页面更新当前显示数量和空状态提示。
6. 用户点击 `导出筛选 CSV` 时，`buildFilteredExportUrl()` 把平台条件写入 `platform` 查询参数。
7. 服务端导出接口基于全部本地 JSONL 记录执行同样的平台过滤。

## 错误处理

- 平台筛选为空：不限制平台。
- 记录缺少 `data-platform`：只有平台筛选为空时匹配；如果用户输入平台条件则不匹配。
- 用户输入不存在的平台：页面展示空状态，筛选导出返回仅表头 CSV。
- 浏览器不支持 `datalist`：平台筛选仍作为普通文本框工作。
- 平台大小写不同：按小写后的包含匹配处理。

## 测试策略

- `tests/test_app.py` 增加首页 HTML 测试，确认存在 `id="platform-filter"`、`name="platform"` 和 `list="platform-presets"`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认包含 `platform-filter`、`matchesPlatform` 和 `params.set("platform", platform)`。
- `tests/test_app.py` 增加或更新筛选导出测试，确认前端导出 URL 会读取平台筛选值。
- `tests/test_record_filters.py` 保留或补充服务端平台过滤测试，确认平台参数仍按大小写不敏感包含匹配工作。
- 全量测试确认现有分析、上传、批量、反馈、导出、概览、详情和平台预设功能不受影响。

## 验收标准

- 首页“最近记录”筛选栏出现“平台”筛选输入框。
- 平台筛选输入框可以使用平台预设，也可以手动输入其他海外电商平台名称。
- 本地最近记录支持按平台大小写不敏感包含筛选。
- 点击 `清空` 可以清除平台筛选条件。
- 点击 `导出筛选 CSV` 时会携带 `platform` 查询参数。
- 服务端筛选导出继续基于全部本地 JSONL 记录执行。
- README 说明最近记录支持平台筛选和筛选导出。
- 全量测试通过。

## 后续可扩展

- 点击运营概览里的平台分布项后自动填入平台筛选。
- 增加平台别名标准化。
- 在筛选栏显示当前平台条件摘要。
- 支持保存常用筛选组合。
