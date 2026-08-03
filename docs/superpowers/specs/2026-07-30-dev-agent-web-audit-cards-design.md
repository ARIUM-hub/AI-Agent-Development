# 研发助手型智能体：Web 执行审计卡片 v1 设计

## 背景

当前 Web provider plan 审批链路已经支持无副作用预览、确认执行、风险优先预览卡片和原始 JSON 结果。用户在执行前已经能看懂“将改哪个文件、风险是什么、会写入什么内容”，但执行后的复盘仍主要依赖 raw JSON。

本阶段目标是在不改变后端执行语义的前提下，把 apply 返回结果渲染成人类可读的执行审计卡片，让用户能快速确认“执行是否成功、实际应用了哪些变更、Git diff 摘要是什么、失败时哪里出错”。

## 已选方案

用户已选择 **B：结果优先卡片**。

该方案优先展示执行结论，再展示实际变更和 Git 摘要：

1. 执行总览卡片。
2. 实际变更卡片列表。
3. Git diff 摘要卡片。
4. 原始 JSON 结果。

相比时间线布局，结果优先卡片更适合当前单次 apply 流程：用户执行后最想先知道成败，然后再复核每个文件。它也能与上一阶段的风险优先预览卡片形成“执行前看风险，执行后看结果”的闭环。

## 目标

- 在 Provider plan 审批区域新增执行后审计卡片列表。
- apply 成功返回后，将 `applied_changes`、`preview_changes`、`diff_stat` 和 `execution_error` 转成人类可读卡片。
- 保留 raw JSON apply result，继续作为调试和回归辅助。
- apply 请求失败、后端返回执行错误、输入变化和重新 preview 时，审计卡片状态保持一致，不展示过期结果。
- 移动端可读，不产生水平滚动。
- 成功、失败、风险状态都使用文本标签配合颜色，不只依赖颜色。

## 非目标

- 不新增后端路由。
- 不修改 provider plan apply 的安全闸门。
- 不接入真实模型 provider。
- 不实现完整 unified diff。
- 不读取旧文件内容。
- 不新增多步骤任务时间线。
- 不引入前端框架、构建工具或外部依赖。
- 不重做整个 Web 控制台视觉系统。

## UI 结构

Provider plan 审批右侧区域调整为：

```text
审批状态
状态 pill
预览卡片列表
原始 preview JSON
执行审计卡片列表
原始 apply JSON
错误提示
```

新增 DOM 容器：

```html
<div id="provider-audit-cards" class="audit-card-list" aria-live="polite"></div>
```

该容器放在 `provider-apply-result` 之前，让用户先看到可读审计结果，再向下查看 raw JSON。

## 卡片内容

### 执行总览卡片

总览卡片展示一次 apply 的最终状态：

- `执行完成`：当 HTTP 请求成功且 `execution_error` 为空。
- `执行失败`：当 HTTP 请求失败，或 payload 中 `execution_error` 不为空。
- `已应用 N 项变更`：来自 `applied_changes.length`。
- `计划 N 项预览变更`：来自 `preview_changes.length`，用于对照“预览过什么”。
- `历史已刷新`：apply 成功路径会调用 `loadHistory()`，卡片文案可提示历史区域已更新。

### 实际变更卡片

每个 `applied_changes` 项展示一张卡片：

- `path`：主标题，允许换行，长路径不断开布局。
- `action`：动作标签，复用 execution plan 动作语义。
- `content_bytes`：显示为“写入 N bytes”。
- `exists`：如果 payload 提供对应 preview change，则显示“执行前目标已存在”或“执行前目标不存在”。
- `risk`：如果 payload 提供对应 preview change，则显示预览风险标签。
- `content_preview`：如果 payload 提供对应 preview change，则展示执行前已审阅的内容片段。
- `content_preview_truncated`：为 `true` 时显示“内容片段已截断，请查看原始 JSON 或缩小计划后重新预览”。

`applied_changes` 与 `preview_changes` 的匹配规则：

- v1 使用同数组下标匹配。
- 若下标缺失或字段缺失，实际变更卡片仍展示 `applied_changes` 自身字段。
- 缺少内容片段时展示“此执行结果没有可读内容片段，请查看原始 JSON”。

### Git diff 摘要卡片

若 payload 包含 `diff_stat`：

- 有内容时展示 diff stat 文本。
- 为空字符串时展示“没有 Git diff 摘要”。

如果字段缺失：

- 展示“此执行结果没有 Git diff 摘要字段”。

### 错误审计卡片

当 `execution_error` 不为空或 apply 请求失败：

- 显示失败总览卡片。
- 展示错误摘要。
- 提示用户查看原始 JSON 或错误提示区域。
- 不显示“已应用成功”的语气，避免误导。

## 风险与状态视觉

沿用当前控制台的纸张、苔藓、陶土色系统，不引入新的视觉语言。

状态 class：

```text
audit-success
audit-failed
audit-partial
audit-neutral
```

动作与风险标签 class 可复用已有风险语义：

```text
risk-create
risk-overwrite
risk-append
risk-append-create
risk-unknown
```

展示规则：

- 成功：苔藓绿色系，文案为“成功”。
- 失败：陶土红棕色系，文案为“失败”。
- 覆盖风险：暖橙色，视觉权重仍高于普通追加。
- 未知状态：中性边框，文案保留原始值。

所有状态必须带文本标签，不只用颜色表达。

## 交互状态

Preview 成功：

- 渲染 preview cards。
- 清空过期 audit cards。
- raw preview JSON 继续显示。
- apply result 回到“确认执行后显示结果。”。

输入变化：

- 清空 preview cards 和 audit cards。
- 清空 `lastProviderPreview`。
- 状态文案为“内容已变化，需要重新预览”。
- 禁用“确认执行”按钮。

Apply 成功且无 `execution_error`：

- 渲染 audit cards。
- raw apply JSON 继续显示。
- 清空 preview cards 和 `lastProviderPreview`。
- 状态文案为“执行完成”。
- 重新加载 history。

Apply 成功但含 `execution_error`：

- 渲染失败审计卡片。
- raw apply JSON 继续显示。
- 清空 preview cards 和 `lastProviderPreview`。
- 状态文案为“执行失败”。
- 显示错误摘要。

Apply 请求失败：

- 渲染失败审计空态。
- raw apply JSON 显示“执行失败。”。
- 清空 preview cards 和 `lastProviderPreview`。
- 状态文案为“执行失败”。
- 显示错误提示。
- 禁用“确认执行”按钮。

## 前端架构

`src/dev_agent/web/static/app.js`：

- 新增 `providerAuditCards()` DOM getter。
- 新增 `clearProviderAuditCards()`。
- 新增 `renderProviderAuditCards(payload)`。
- 新增 `renderProviderAuditFailure(message)`。
- 新增小 helper 用于按下标查找 preview change。
- apply 成功后调用 `renderProviderAuditCards(payload)`。
- apply 请求失败时调用 `renderProviderAuditFailure(error.message)`。
- preview 成功、preview 失败和输入变化时调用 `clearProviderAuditCards()`。
- 渲染 provider 内容继续使用 `textContent`，不把模型输出或计划内容作为 HTML 注入。

`src/dev_agent/web/static/index.html`：

- 在 apply JSON `<pre>` 前新增 `provider-audit-cards` 容器。
- 给 apply JSON 区域加小标题，例如“执行结果 JSON”。

`src/dev_agent/web/static/styles.css`：

- 新增 `.audit-card-list`、`.audit-card`、`.audit-card-header`、`.audit-status-badge`、`.audit-meta`、`.audit-diff`、`.audit-error` 等样式。
- 复用或兼容 `.risk-badge`、`.content-preview`、`.truncation-note`。
- 保持长路径和长 diff 文本可换行，不在移动端产生水平滚动。

## 可访问性与响应式

- 审计卡片容器使用 `aria-live="polite"`。
- 成功、失败和风险必须显示文本标签。
- 长路径使用 `overflow-wrap: anywhere`。
- 内容片段和 diff 使用可换行文本块。
- 卡片列表移动端单列展示。
- 交互按钮沿用现有 `disabled` 语义。
- 不新增强制动画，尊重现有 `prefers-reduced-motion` 约束。

## 错误处理

- `applied_changes` 缺失或不是数组时，总览卡片显示“没有实际应用变更记录”。
- `preview_changes` 缺失或不是数组时，不阻止审计卡片渲染。
- `diff_stat` 缺失时显示字段缺失提示。
- `execution_error` 不为空时优先展示失败状态。
- 单个字段缺失时使用安全 fallback 文案，不让页面抛异常。
- 所有来自 payload 的文本字段都通过 `textContent` 渲染。

## 测试策略

静态资源测试：

- `tests/test_web_server.py::test_static_assets_include_console_interactions` 断言 HTML、JS、CSS 中包含审计卡片容器、渲染函数和关键样式 class。
- 断言页面仍包含 raw preview JSON 和 raw apply JSON 小标题。

Web API 测试：

- 不需要新增后端路由测试。
- 可扩展现有 apply route 测试，确认 apply payload 仍包含 `applied_changes`、`preview_changes`、`diff_stat` 和 `execution_error`，供前端审计卡片使用。

可选 smoke：

- 启动 `python -m dev_agent.cli serve --port 0 --check` 确认可服务启动。
- 静态检查 `/static/app.js` 和 `/static/styles.css` 可访问。

人工验收：

- 在 Web 页面输入 provider plan 并点击“生成预览”。
- 能看到预览卡片。
- 点击“确认执行”后，预览卡片清空，审计卡片出现。
- 审计卡片包含执行结论、实际变更、内容片段和 Git diff 摘要。
- 修改输入后审计卡片清空，“确认执行”禁用。
- apply 失败时展示失败审计状态和错误提示。

## 安全与熔断保护

本阶段只修改本地 Web 静态展示和本地测试，不调用真实模型供应商，不批量探测 provider，不启动并发智能体，不做压力测试，不批量重试失败请求。

## 兼容性

这是向后兼容的 Web 展示增强。后端 payload 结构不变，旧字段继续渲染 raw JSON；若某些字段缺失，审计卡片会展示 fallback 文案而不是抛出异常。

## 验收标准

- Web apply 成功后显示结果优先的执行审计卡片。
- 审计卡片展示执行结论、实际变更、内容片段和 Git diff 摘要。
- Raw JSON apply result 仍保留。
- preview 成功、preview 失败、输入变化、apply 成功和 apply 失败时不会留下过期审计卡片。
- 内容片段直接显示中文，且通过 `textContent` 渲染。
- 移动端布局不横向溢出。
- 全量测试通过。
