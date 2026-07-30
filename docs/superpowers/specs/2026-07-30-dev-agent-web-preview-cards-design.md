# 研发助手型智能体：Web 可读预览卡片 v1 设计

## 背景

当前 Web 审批流已经具备两步式安全流程：先调用 `/api/provider-plan/preview` 生成无副作用预览，再由用户点击“确认执行”调用 `/api/provider-plan/apply`。上一阶段的 execution preview payload 已新增 `content_preview`、`content_preview_truncated`、`content_preview_line_count` 和 `content_preview_char_count`，但 Web 页面仍主要把 preview payload 原样渲染成 JSON。

本阶段目标是把这些结构化字段转成风险优先的审批卡片，让用户在确认执行前更快看懂“将改哪个文件、风险是什么、会写入什么内容”。

## 已选方案

用户已选择 **B：风险优先卡片**。

该方案把每个 `preview_changes` 项渲染成一张卡片，并按审批场景组织视觉层级：

1. 文件路径。
2. 风险标签。
3. 目标状态和写入摘要。
4. 内容片段。
5. 截断提示。

## 目标

- 在 Provider plan 审批区域新增人类可读的 preview card list。
- 复用现有 Web API，不新增后端字段或路由。
- 保留 raw JSON preview，作为调试详情和回归辅助。
- 输入变化、preview 失败、apply 成功或失败后，卡片与 preview 状态同步清空。
- 移动端可读，不产生水平滚动。
- 使用文本标签配合颜色表达风险，不只依赖颜色。

## 非目标

- 不实现完整 unified diff。
- 不读取已有文件内容。
- 不新增 Web apply 的二次确认弹窗。
- 不引入前端框架、构建工具或外部依赖。
- 不重做整个控制台视觉系统。
- 不改变 provider plan preview/apply 的安全闸门。

## UI 结构

Provider plan 审批右侧区域从纯 JSON 展示升级为：

```text
审批状态
状态 pill
可读预览卡片列表
Raw preview JSON
Apply result JSON
错误提示
```

新增 DOM 容器：

```html
<div id="provider-preview-cards" class="preview-card-list" aria-live="polite"></div>
```

该容器放在 `provider-preview-result` 之前，让用户先看到可读卡片，再向下查看 raw JSON。

## 卡片内容

每个卡片展示一个 preview change：

- `path`：主标题，允许换行，长路径不断开布局。
- `risk`：风险标签，取值来自现有 execution preview。
- `exists`：显示为“目标已存在”或“目标不存在”。
- `content_bytes`：显示为“将写入 N bytes”。
- `content_preview_line_count`：显示为“原始内容 N 行”。
- `content_preview`：使用 `<pre>` 展示，保留换行和中文。
- `content_preview_truncated`：为 `true` 时显示“内容已截断，请查看 JSON 或缩小计划内容后重新预览”。

空内容：

- `content_preview` 为空字符串时，卡片展示“内容为空”。
- 仍显示 bytes 和行数，避免用户误以为空区域是渲染失败。

缺少新字段：

- 若某个 payload 只含旧字段，卡片仍可渲染路径、风险、目标状态和 bytes。
- 内容区域显示“此预览没有内容片段字段，请重新生成预览或检查服务版本”。
- 这样保持向后兼容，避免旧 payload 让页面报错。

## 风险视觉映射

使用语义 class，而不是在 JavaScript 中写散落样式：

```text
risk-create
risk-overwrite
risk-append
risk-append-create
risk-unknown
```

展示规则：

- `create`：绿色/苔藓色，表示新建文件。
- `overwrite`：暖橙色，表示覆盖已有内容，视觉权重最高。
- `append`：蓝绿色或中性色，表示追加到已有文件。
- `append_create`：介于 create 与 append 之间，文案显示“追加并创建文件”。
- 未知风险：中性边框，文案显示原始风险值。

风险文案：

```text
create -> 新建
overwrite -> 覆盖
append -> 追加
append_create -> 追加并创建
其他 -> 原始 risk 字符串
```

## 交互状态

Preview 成功：

- `lastProviderPreview = payload`。
- 渲染 preview cards。
- raw JSON 继续写入 `provider-preview-result`。
- 状态文案为“预览通过，可以确认执行”。
- “确认执行”按钮启用。

Preview 失败：

- 清空 preview cards。
- raw JSON 区域显示“预览失败。”。
- 状态文案为“预览失败”。
- 显示错误提示。
- “确认执行”按钮保持禁用。

输入变化：

- 若已有 preview，清空 preview cards。
- 清空 `lastProviderPreview`。
- 状态文案为“内容已变化，需要重新预览”。
- 禁用“确认执行”按钮。

Apply 成功：

- 渲染 apply result JSON。
- 清空 preview cards 和 `lastProviderPreview`。
- 状态文案为“执行完成”或按 `execution_error` 显示“执行失败”。
- 重新加载 history。

Apply 失败：

- 渲染“执行失败。”。
- 清空 preview cards 和 `lastProviderPreview`。
- 显示错误提示。
- 禁用“确认执行”按钮。

## 前端架构

`src/dev_agent/web/static/app.js`：

- 新增 `providerPreviewCards()` DOM getter。
- 新增 `clearProviderPreviewCards()`。
- 新增 `renderProviderPreviewCards(payload)`。
- 新增 `providerRiskLabel(risk)`。
- 新增 `providerRiskClass(risk)`。
- 在 `submitProviderPreview()` 成功后调用 `renderProviderPreviewCards(payload)`。
- 在 preview 失败、输入变化、apply 成功和 apply 失败时调用 `clearProviderPreviewCards()`。

`src/dev_agent/web/static/index.html`：

- 在 preview JSON `<pre>` 前新增 `provider-preview-cards` 容器。
- 给 raw JSON 区域加一个小标题或 helper 文案，例如“原始 JSON”。

`src/dev_agent/web/static/styles.css`：

- 新增 `.preview-card-list`、`.preview-card`、`.preview-card-header`、`.risk-badge`、`.preview-meta`、`.content-preview`、`.truncation-note` 等样式。
- 延续当前控制台的纸张、苔藓、陶土色系统，不引入新的视觉语言。
- 保持 `pre` 内容可换行，不在移动端产生水平滚动。

## 可访问性与响应式

- 风险必须有文本标签，不能只靠颜色。
- 卡片列表使用 `aria-live="polite"`，preview 完成后屏幕阅读器可感知区域变化。
- 路径和内容片段允许换行，长路径使用 `overflow-wrap: anywhere`。
- 内容片段使用足够对比度的背景和边框。
- 按钮 busy/disabled 逻辑沿用现有语义。
- 移动端单列展示；卡片内 header 在窄屏允许换行。
- 尊重现有 `prefers-reduced-motion` 规则，不新增强制动画。

## 错误处理

- `preview_changes` 缺失或不是数组时，卡片区域显示空状态：“没有可显示的预览变更”。
- 单个 change 字段缺失时，用安全 fallback 文案，不让页面抛异常。
- 渲染内容使用 `textContent`，不把 provider 内容作为 HTML 注入。
- 路径、风险和内容都按文本处理，避免脚本注入。

## 测试策略

静态资源测试：

- `tests/test_web_server.py::test_static_assets_include_console_interactions` 断言 HTML/JS/CSS 中包含 preview card 容器、渲染函数和样式 class。

Web API 测试：

- 不需要新增后端测试；API payload 已在上一阶段覆盖 `content_preview` 透传。

可选 smoke：

- 启动 `python -m dev_agent.cli serve --port 0 --check` 确认可服务启动。
- 用本地 HTTP server 路由测试或静态文件检查确认 `/static/app.js` 和 `/static/styles.css` 可访问。

人工验收：

- 在 Web 页面输入 provider plan 并点击“生成预览”。
- 能看到风险优先卡片，包含路径、风险、目标状态、bytes、行数和内容片段。
- 修改输入后卡片消失，“确认执行”禁用。
- preview 失败时卡片消失并显示错误。

## 安全与熔断保护

本阶段只修改本地 Web 静态展示和本地测试，不调用真实模型供应商，不批量探测 provider，不启动并发智能体，不做压力测试。

## 验收标准

- Web preview 成功后显示风险优先卡片列表。
- Raw JSON preview 仍保留。
- 输入变化、preview 失败、apply 成功和 apply 失败时不会留下过期卡片。
- 内容片段直接显示中文，且通过 `textContent` 渲染。
- 移动端布局不横向溢出。
- 全量测试通过。
