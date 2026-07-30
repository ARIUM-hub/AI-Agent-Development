# 导出前记录数预估设计

## 背景

客户使用问题归因智能体已经支持海外电商平台客服会话分析、批量上传、人工复核、最近记录筛选、筛选导出 CSV、运营概览时间范围筛选、平台分布下钻、记录详情复制，以及导出筛选条件提示。当前 `导出筛选 CSV` 会把平台、关键词、问题类型、责任方、复核状态和时间范围传给后端导出接口，页面也会提示“本次筛选导出将应用哪些条件”。

但运营人员在导出前仍不知道这些条件最终会匹配多少条本地 JSONL 记录。尤其是页面只展示最近 10 条样本，而筛选导出会基于全部本地记录执行；如果只看页面筛选数量，容易误以为导出数量就是当前页面可见数量。本轮目标是在导出前展示真实导出记录数预估，让导出行为更可预期。

## 目标

- 在导出筛选条件提示附近新增记录数预估提示，例如 `预计导出 12 条`。
- 预估数量必须使用后端真实导出口径，基于全部本地 JSONL 记录，而不是页面最近 10 条样本。
- 新增轻量后端接口 `GET /api/records/export-count`。
- 预估接口参数与 `/api/records/export.csv` 保持一致：`platform`、`issue_category`、`responsibility`、`feedback_status`、`q`、`range`。
- 后端复用现有 `filter_records()`，避免复制筛选规则。
- 前端在页面初始化、筛选输入、筛选重置、时间范围切换、平台分布下钻时刷新预估数量。
- 预估请求失败时不阻断筛选和导出，只显示 `预计数量暂不可用`。
- 快速连续输入时避免旧请求结果覆盖新请求结果。
- README 补充说明筛选导出前会展示真实预计导出数量。

## 非目标

- 不修改 `/api/records/export.csv` 的响应格式、文件名、CSV 字段或编码。
- 不改变现有导出 URL 参数语义。
- 不改变 JSONL 存储结构。
- 不把页面本地筛选数量当作真实导出数量。
- 不新增模型调用，不增加供应商请求。
- 不做复杂分页、导出任务队列或异步后台任务。

## 推荐方案

新增 `GET /api/records/export-count` 接口：

```http
GET /api/records/export-count?platform=amazon&feedback_status=corrected&range=30d
```

返回：

```json
{"count": 12}
```

后端实现直接复用 `filter_records(store.list_records(), ...)`，参数与 CSV 导出接口保持一致，然后返回匹配记录数。这样预估数量和真实 CSV 导出的筛选口径一致，后续如果筛选规则变化，也只需要维护 `filter_records()`。

前端在现有 `#export-filter-summary` 附近新增只读提示区：

```html
<p id="export-count-preview" class="export-count-preview" aria-live="polite">预计导出数量加载中...</p>
```

新增 `updateExportCountPreview()`，它读取同一组筛选控件，构建 `/api/records/export-count` 请求。为了减少重复逻辑，可以抽出 `buildExportFilterParams()`，让 `buildFilteredExportUrl()` 和 `buildExportCountPreviewUrl()` 共用同一套参数收集逻辑：

- `buildExportFilterParams()` 返回 `URLSearchParams`。
- `buildFilteredExportUrl()` 继续返回 `/api/records/export.csv` 或带 query string 的 URL。
- `buildExportCountPreviewUrl()` 返回 `/api/records/export-count` 或带 query string 的 URL。

快速输入时，前端维护一个递增请求序号，例如 `latestExportCountRequestId`。每次请求前递增，响应回来时只有当前序号仍是最新请求才更新 DOM；否则丢弃旧结果。这样不用引入额外依赖，也能避免慢请求覆盖新输入。

## 展示文案

默认加载中：

```text
预计导出数量加载中...
```

成功：

```text
预计导出 12 条
```

无匹配：

```text
预计导出 0 条
```

失败：

```text
预计数量暂不可用
```

该文案只表达真实后端筛选数量，不替代现有页面本地筛选计数 `当前显示 N / M 条`。

## 备选方案

方案 A：直接复用页面本地筛选数量。实现最快，但页面只包含最近 10 条样本，和 CSV 导出全部 JSONL 的真实数量可能不一致，因此不采用。

方案 B：扩展 `/api/records/summary`，让运营概览接口同时支持所有导出筛选条件。这样也能得到真实数量，但会混淆“运营概览”和“导出预估”的职责，并扩大现有 summary 接口语义，因此不采用。

方案 C：点击导出按钮前才请求数量并弹窗确认。可以减少请求次数，但增加导出阻力，也不符合当前页面已经有只读导出提示的轻量交互，因此不采用。

## 数据流

1. 页面渲染最近记录筛选栏、`#export-filter-summary` 和 `#export-count-preview`。
2. 页面初始化时前端读取当前筛选条件和时间范围。
3. `updateExportFilterSummary()` 更新条件提示。
4. `updateExportCountPreview()` 请求 `/api/records/export-count`。
5. 后端读取全部本地 JSONL 记录，复用 `filter_records()` 得到匹配列表。
6. 后端返回 `{ "count": N }`。
7. 前端显示 `预计导出 N 条`。
8. 用户修改平台、关键词、问题类型、责任方、复核状态，或切换时间范围。
9. 前端重新更新条件提示和数量预估。
10. 用户点击 `导出筛选 CSV`。
11. 现有 `/api/records/export.csv` 继续按同一组参数导出 CSV。

## 错误处理

- 预估提示区不存在：前端更新函数直接返回，不影响页面其他功能。
- 某个筛选控件不存在：对应参数忽略，和现有导出 URL 构建保持一致。
- 后端预估接口返回非 2xx：前端显示 `预计数量暂不可用`。
- 网络异常或 JSON 解析失败：前端显示 `预计数量暂不可用`。
- 快速连续输入产生多个请求：只有最后一次请求可以更新预估提示。
- 非法 `range` 值：后端 `filter_records()` 继续按现有 `_range_value()` 规则回退为 `all`。
- 预估数量为 0：正常显示 `预计导出 0 条`，不阻止用户导出只有表头的 CSV。

## 测试策略

- `tests/test_app.py` 新增后端接口测试，写入多条 JSONL 记录后请求 `/api/records/export-count`，确认平台、时间范围和关键词筛选后的 `count` 与 CSV 导出口径一致。
- `tests/test_app.py` 新增空结果测试，确认不匹配条件返回 `{"count": 0}`。
- `tests/test_app.py` 更新首页 HTML 测试，确认存在 `id="export-count-preview"`、`class="export-count-preview"`、`aria-live="polite"` 和默认加载文案。
- `tests/test_app.py` 更新静态 JS hook 测试，确认包含 `updateExportCountPreview`、`buildExportCountPreviewUrl`、`buildExportFilterParams`、`/api/records/export-count`、`预计导出` 和 `预计数量暂不可用`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认筛选输入、重置、时间范围切换和平台下钻会触发预估刷新。
- `tests/test_app.py` 更新静态 CSS hook 测试，确认包含 `.export-count-preview`。
- README 补充说明预估数量来自后端真实导出口径，不限于页面最近 10 条。
- 全量测试确认现有分析、上传、批量、反馈、筛选、筛选导出、导出筛选条件提示、运营概览、平台下钻和复制详情不受影响。

## 验收标准

- 页面在导出筛选条件提示附近显示预计导出数量。
- 无筛选条件时，预估数量等于全部本地 JSONL 记录数。
- 有筛选条件时，预估数量与同条件 CSV 导出的记录条数一致。
- 时间范围切换后，预估数量同步更新。
- 平台分布下钻填入平台筛选后，预估数量同步更新。
- 请求失败时显示 `预计数量暂不可用`，且不影响导出按钮。
- CSV 导出接口行为保持不变。
- README 说明预估数量的真实导出口径。
- 全量测试通过。

## 后续可扩展

- 在预估数量较大时提示“建议先筛选后导出”。
- 在导出完成后显示最近一次导出条件和记录数。
- 为预估请求增加短时间防抖，进一步减少快速输入时的请求数。
- 将预估数量与条件提示合并成更紧凑的可视化标签组。
