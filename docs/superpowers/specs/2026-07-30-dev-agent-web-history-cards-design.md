# 研发助手型智能体：Web 历史可读卡片 v1 设计

## 背景

当前 Web 控制台已经能展示环境、上下文、历史、dry-run、provider plan 预览、确认执行、预览卡片和执行审计卡片。但“历史”区域仍然只把 `/api/history` 的 raw JSON 渲染到 `<pre id="history">` 中。这个信息机器可读，但人工复盘成本偏高：用户需要在 JSON 中寻找任务标题、状态、摘要、验证命令和经验。

本阶段目标是在不改变历史存储结构和后端接口的前提下，把历史任务渲染成“任务复盘卡片”，让用户能快速回看做过什么、结果如何、验证过什么，以及沉淀了哪些经验。

## 已选方案

用户已选择 **B：任务复盘卡片 + 可展开详情**。

该方案以任务为基本单位，每条历史记录显示一张卡片：

1. 默认展示任务标题、状态、摘要、验证数量、经验数量和最近事件摘要。
2. 详情区域展示完整 `events`、`verification` 和 `lessons`。
3. raw JSON 历史结果继续保留，便于调试和回归。

相比紧凑列表，任务复盘卡片更适合个人研发助手的“回忆和复盘”场景；相比经验优先看板，它不需要新增后端聚合逻辑，能用现有 `TaskRecord` 字段完成 v1。

## 目标

- 在 Web 历史区域新增人类可读的历史任务卡片列表。
- 复用现有 `/api/history` payload，不新增后端路由或 schema。
- 保留 raw JSON 历史输出。
- `loadHistory()` 每次刷新时同步更新卡片和 raw JSON。
- 空历史显示友好空态。
- 字段缺失或旧格式历史不让页面报错。
- 所有历史文本都用 `textContent` 渲染，避免把任务内容作为 HTML 注入。
- 移动端可读，不产生水平滚动。

## 非目标

- 不新增历史查询、筛选或排序功能。
- 不新增后端字段。
- 不聚合跨任务经验。
- 不实现任务详情路由。
- 不引入前端框架、构建工具或外部依赖。
- 不调用真实模型供应商。
- 不批量探测 provider，不做循环健康检查或压力测试。
- 不改变历史 JSONL 的持久化格式。

## 数据来源

历史接口保持不变：

```text
GET /api/history
```

payload 结构：

```json
{
  "tasks": [
    {
      "task_id": "task-1",
      "title": "修复中文乱码",
      "status": "passed",
      "summary": "UTF-8 修复",
      "events": [],
      "verification": [],
      "lessons": []
    }
  ]
}
```

字段来源是 `TaskRecord`：

- `task_id`
- `title`
- `status`
- `summary`
- `events`
- `verification`
- `lessons`

v1 不要求后端返回创建时间，因为当前 `TaskRecord` 没有时间字段。

## UI 结构

当前历史 panel 从单一 raw JSON 升级为：

```text
历史
历史任务卡片列表
原始 JSON
```

新增 DOM 容器：

```html
<div id="history-cards" class="history-card-list" aria-live="polite"></div>
```

该容器放在 `<pre id="history">` 之前，让用户先看到可读卡片，再查看 raw JSON。

raw JSON 前新增小标题：

```html
<h3 class="result-heading">原始 JSON</h3>
```

## 卡片内容

每个任务卡片展示：

- `title`：主标题，缺失时显示“未命名任务”。
- `status`：状态标签，显示中文文案。
- `summary`：任务摘要，缺失时显示“暂无摘要”。
- `verification.length`：显示为“验证 N 项”。
- `lessons.length`：显示为“经验 N 条”。
- 最近事件摘要：优先显示 `events` 最后一项，缺失时显示“暂无事件记录”。
- `task_id`：小号辅助信息，便于调试和追踪。

详情区域展示：

- `verification`：完整验证命令列表。
- `lessons`：完整经验列表。
- `events`：完整事件列表。

详情默认使用原生 `<details>` / `<summary>`：

- 无需自写展开状态逻辑。
- 键盘和屏幕阅读器语义更好。
- 不引入额外 JavaScript 状态。

## 状态映射

状态文案：

```text
passed -> 通过
failed -> 失败
running -> 运行中
planned -> 已计划
其他 -> 原始 status 字符串，缺失时显示“未知状态”
```

状态 class：

```text
history-status-passed
history-status-failed
history-status-running
history-status-planned
history-status-unknown
```

展示规则：

- `passed`：苔藓绿色系。
- `failed`：陶土红棕色系。
- `running`：蓝绿色或中性色。
- `planned`：中性纸张色。
- 未知状态：中性边框，并显示原始状态文本。

状态必须显示文本标签，不能只依赖颜色。

## 交互状态

页面首次加载：

- `loadHistory()` 获取 `/api/history`。
- 渲染 history cards。
- raw JSON 继续写入 `history` `<pre>`。

dry-run 提交后：

- 现有 `submitRun()` 会调用 `loadHistory()`。
- 历史卡片同步刷新。

provider apply 成功后：

- 现有 `submitProviderApply()` 会调用 `loadHistory()`。
- 历史卡片同步刷新。

历史为空：

- `history-cards` 显示“暂无历史任务。完成 dry-run 或确认执行后会出现在这里。”。
- raw JSON 继续显示 `{ "tasks": [] }`。

历史加载失败：

- v1 不新增全局错误框。
- 如果未来 `loadHistory()` 捕获错误，可以在 `history-cards` 显示“历史加载失败，请检查本地服务。”。
- 当前阶段以现有 fetch 行为为准，不扩大错误处理范围。

## 前端架构

`src/dev_agent/web/static/app.js`：

- 新增 `historyCards()` DOM getter。
- 新增 `historyStatusLabel(status)`。
- 新增 `historyStatusClass(status)`。
- 新增 `clearHistoryCards()`。
- 新增 `renderHistoryCards(payload)`。
- 新增小 helper `appendHistoryList(parent, title, items, emptyText)`。
- 修改 `loadHistory()`：先获取 payload，再调用 `renderHistoryCards(payload)`，最后 `renderJson("history", payload)`。

`src/dev_agent/web/static/index.html`：

- 在 `<pre id="history">` 前新增 `history-cards` 容器。
- 给 raw JSON 历史区域加“原始 JSON”标题。

`src/dev_agent/web/static/styles.css`：

- 新增 `.history-card-list`、`.history-card`、`.history-card-header`、`.history-status-badge`、`.history-meta`、`.history-summary`、`.history-detail`、`.history-list`、`.history-empty-state`。
- 复用现有纸张、苔藓、陶土色系统。
- 长任务标题、摘要、命令和经验使用 `overflow-wrap: anywhere`。

## 可访问性与响应式

- `history-cards` 使用 `aria-live="polite"`。
- 状态以文本标签展示。
- 详情使用原生 `<details>` 和 `<summary>`。
- 长文本允许换行，不横向溢出。
- 移动端卡片单列展示，卡片 header 可换行。
- 不新增强制动画，尊重现有 `prefers-reduced-motion`。

## 错误处理与兼容性

- `tasks` 缺失或不是数组时显示空态。
- 单个任务字段缺失时使用 fallback 文案。
- `events`、`verification`、`lessons` 缺失或不是数组时按空列表处理。
- 所有历史文本都通过 `textContent` 写入 DOM。
- raw JSON 保留，旧消费者不受影响。
- 后端 payload 不变，因此现有 API 测试应继续通过。

## 测试策略

静态资源测试：

- `tests/test_web_server.py::test_static_assets_include_console_interactions` 断言 HTML 包含 `history-cards` 和历史 raw JSON 标题。
- 断言 JS 包含 `renderHistoryCards`、`historyStatusLabel`、`historyStatusClass`、`clearHistoryCards`。
- 断言 CSS 包含 `.history-card-list`、`.history-card`、`.history-status-badge`、`.history-status-passed`、`.history-status-failed`。
- 断言 JS 继续使用 `textContent`。

Web route/API 测试：

- 扩展 `tests/test_web_server.py::test_history_route_returns_json` 或 `tests/test_web_api.py::test_build_history_payload_lists_tasks`，确认历史 payload 仍保留 `title`、`status`、`summary`、`events`、`verification`、`lessons`。
- 不新增后端业务逻辑测试，除非实现中发现 payload 契约不足。

人工验收：

- 打开 Web 控制台。
- 空历史时看到友好空态。
- 完成 dry-run 或 provider apply 后，历史卡片刷新。
- 卡片能显示中文标题、摘要、验证命令和经验。
- 展开详情能看到 events、verification、lessons。
- raw JSON 仍保留。

验证命令：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py -v
python -m pytest -v
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m dev_agent.cli serve --port 0 --check
```

## 安全与熔断保护

本阶段只修改本地 Web 静态展示和本地测试，不调用真实模型供应商，不批量探测 provider，不启动并发智能体，不做压力测试，不批量重试失败请求。

## 验收标准

- Web 历史区域显示任务复盘卡片。
- 空历史有友好空态。
- 每张卡显示任务标题、状态、摘要、验证数量、经验数量和最近事件。
- 详情区域能查看完整 events、verification 和 lessons。
- raw JSON 历史仍保留。
- 历史文本直接显示中文，且通过 `textContent` 渲染。
- 移动端布局不横向溢出。
- 全量测试通过。
