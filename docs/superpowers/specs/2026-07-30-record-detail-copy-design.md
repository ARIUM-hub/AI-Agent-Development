# 最近记录详情复制设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话分析、批量上传、人工复核、最近记录筛选、记录详情展开、筛选导出 CSV、运营概览和平台下钻筛选。当前每条最近记录可以点击 `查看详情` 展开结构化信息，包括客户问题、问题类型、业务原因、责任方、证据强度、下一步建议、需要补充信息、人工复核和人工备注。

运营人员在处理客服工单、协作文档或复盘群消息时，经常需要把这段结构化详情复制出去。现在只能手动选中页面内容，容易漏字段，也不够快。本轮目标是在不改变后端和存储的前提下，补一个轻量的一键复制能力。

## 目标

- 在每条最近记录的详情区域增加 `复制详情` 按钮。
- 点击按钮后生成纯文本摘要，便于粘贴到客服工单、协作文档或复盘群。
- 复制内容包含平台、记录 ID、客户问题、问题类型、业务原因、优先责任方、证据强度、下一步建议、需要补充信息、人工复核和人工备注。
- 复制逻辑优先使用 `navigator.clipboard.writeText()`。
- 复制成功后在当前记录内显示短状态提示。
- 浏览器不支持 Clipboard API 或复制失败时显示失败提示，提示用户手动选择详情文本。
- 新生成的分析记录和服务端渲染的历史记录都具备复制按钮。
- README 补充说明记录详情支持复制。

## 非目标

- 不新增后端接口。
- 不修改 JSONL 存储结构。
- 不修改分析、批量分析或人工反馈接口。
- 不改变 CSV 导出逻辑。
- 不生成富文本、Markdown 表格或 HTML。
- 不复制原始客服会话全文。
- 不调用模型，不增加供应商请求。

## 推荐方案

扩展现有 `recordDetailHtml(recordId, analysis, feedback = null)`，在详情区域的结构化明细前增加复制按钮和状态文本：

```html
<button class="record-copy-action secondary-action" type="button" data-record-copy>复制详情</button>
<p class="record-copy-status" data-record-copy-status aria-live="polite"></p>
```

按钮挂在每条 `.record` 内，由 `bindRecordCopyActions(root = document)` 统一绑定。点击时通过当前记录已有 DOM 与 `data-*` 属性生成文本：记录 ID 使用 `article.dataset.recordId`，平台使用 `article.dataset.platform`，详情字段从 `.record-detail-grid` 的 `dt` / `dd` 读取。

复制文本格式使用简单的多行键值对：

```text
平台：Amazon
记录 ID：abc123
客户问题：...
问题类型：...
业务原因：...
优先责任方：...
证据强度：...
下一步建议：...
需要补充信息：...
人工复核：未复核
人工备注：暂无信息
```

这种方式复用已经渲染和格式化好的页面文案，不需要重新维护一套前端字段映射，也能同时覆盖服务端渲染记录和新追加记录。

## 备选方案

方案 A：复制 JSON。结构完整，但不适合直接贴到工单或复盘群，运营同学阅读成本高，因此不采用。

方案 B：新增服务端复制文本接口。可以保证文本由后端生成，但会增加 API 和记录读取逻辑；当前页面已经拥有全部详情字段，本轮不需要新增接口，因此不采用。

方案 C：复制详情区的 `innerText`。实现最快，但会混入按钮文案和状态提示，格式也不稳定，因此不采用。

## 数据流

1. 页面渲染最近记录，每条记录包含详情区域。
2. 详情区域包含 `复制详情` 按钮和复制状态提示。
3. DOMContentLoaded 后调用 `bindRecordCopyActions(document)` 绑定已有记录。
4. 新分析记录通过 `prependRecentRecord()` 插入页面后，对新节点调用 `bindRecordCopyActions(article)`。
5. 用户点击复制按钮。
6. 前端从当前 `.record` 的 `data-record-id`、`data-platform` 和 `.record-detail-grid` 读取字段。
7. 前端生成纯文本摘要并调用 `navigator.clipboard.writeText(text)`。
8. 成功时显示 `已复制详情`；失败或不支持时显示 `复制失败，请手动选择详情文本`。

## 错误处理

- 当前按钮不在 `.record` 内：不抛错，显示失败提示或直接返回。
- 当前记录没有详情区域：不抛错，显示失败提示。
- `navigator.clipboard.writeText` 不存在：显示失败提示。
- Clipboard API 被浏览器权限阻止：捕获异常并显示失败提示。
- 某个详情字段为空：使用页面已有的 `暂无信息` 文案。
- 复制状态提示使用当前记录内的状态区域，不影响其他记录。

## 测试策略

- `tests/test_app.py` 更新最近记录详情 HTML 测试，确认服务端渲染记录包含 `data-record-copy` 和 `data-record-copy-status`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认包含 `bindRecordCopyActions`、`copyRecordDetails`、`buildRecordDetailCopyText` 和 `navigator.clipboard.writeText`。
- `tests/test_app.py` 更新静态 JS hook 测试，确认新追加记录会调用复制绑定。
- `tests/test_app.py` 更新样式 hook 测试，确认包含 `.record-copy-action` 和 `.record-copy-status`。
- 全量测试确认现有分析、上传、批量、反馈、详情展开、最近记录筛选、平台下钻、导出和概览不受影响。

## 验收标准

- 每条最近记录详情区域显示 `复制详情` 按钮。
- 服务端渲染的历史记录和新分析追加的记录都包含复制按钮。
- 点击复制按钮会生成包含关键结构化字段的纯文本摘要。
- Clipboard API 可用时复制成功并显示成功提示。
- Clipboard API 不可用或失败时显示失败提示，不导致页面报错。
- 复制按钮不会影响详情展开/收起、筛选、导出和概览下钻。
- README 说明记录详情支持复制。
- 全量测试通过。

## 后续可扩展

- 支持复制 Markdown 模板。
- 支持复制原始客服会话。
- 支持团队自定义复制字段顺序。
- 在复制成功后提供“打开导出 CSV”的后续动作。
