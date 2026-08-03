# Web 审批视图与执行确认 v1 设计

日期：2026-07-29

## 背景与目标

当前研发助手已经具备本地 Web 控制台、结构化执行计划、CLI 预览、显式确认和 provider 严格 JSON 计划解析。Web 控制台目前仍只支持 dry-run：用户可以提交任务并查看返回计划文本，但不能在浏览器里审阅结构化变更，也不能通过 Web 复用 CLI 已有的确认执行闭环。

本阶段目标是在不接真实云端模型、不增加供应商请求风险的前提下，为 Web 控制台增加两步式 provider plan 审批流：第一步只解析并预览 fake/provider 返回的严格 JSON 执行计划；第二步由用户显式点击确认后才应用计划。这样 Web 入口能和 CLI 共享同一套安全边界，并为后续更完整的审批页、diff 视图和真实 provider 接入打底。

## 范围

### 包含

- Web 新增 provider plan preview 能力，接受 `request` 和严格 JSON `fake_response`。
- Preview 阶段只返回 `planned_changes` 和 `preview_changes`，不写文件、不创建 `.agent` 任务历史。
- Web 新增 provider plan apply 能力，只在第二步确认请求中执行。
- Apply 阶段仍复用 `parse_provider_execution_plan()`、`ExecutionPlanApplier.preview()` 和 `LocalTaskRunner.run(... apply_changes=True)`。
- Apply 成功后返回 `task_id`、`applied_changes`、`diff_stat`、`execution_error`，并刷新历史。
- 解析失败、危险路径、create 冲突或未提供有效请求时返回中文错误，不写文件。
- 前端页面展示两步状态：输入、预览、确认执行、执行结果。
- 前端确认按钮只有 preview 成功后才可用。
- Web 能力标记从 `dry_run_only` 调整为更准确的 provider plan 审批能力描述。
- 所有 JSON 响应和页面文本保持 UTF-8 中文可读。

### 不包含

- 真实云端模型调用。
- 多 provider 尝试、批量重试、健康探测或循环请求。
- 自动从自然语言中提取 JSON。
- Markdown fenced JSON 解析。
- Web 直接编辑文件内容。
- 删除、移动、重命名、二进制写入或大规模目录操作。
- Git commit、push、merge、reset 或自动 PR 操作。
- 完整 unified diff 展示；本阶段继续使用结构化 preview 和 Git diff stat。
- 多用户权限系统、会话持久化审批队列或跨浏览器审批同步。

## 推荐方案

采用“两步式 Web 审批流”。

用户先在页面输入任务说明和 fake/provider 返回的严格 JSON plan，点击“生成预览”。后端只解析 provider plan 并运行 preview 预校验，返回计划摘要和每个文件操作的风险标签。前端展示预览结果后才启用“确认执行”按钮；用户点击确认后，前端再次发送同一份 `request` 和 `fake_response` 到 apply 接口，后端重新解析并重新 preview，再调用 runner 执行。

相比单表单勾选确认，两步式流程更不容易误触写入，也更符合已有 CLI 的“预览失败则绝不写入，未确认则绝不写入”原则。相比只做 Web 预览，本方案能完成浏览器端的第一条安全写入闭环，但仍通过严格 JSON、路径预校验和显式确认控制风险。

## API 设计

### `POST /api/run`

保持现有 dry-run 行为，继续用于普通 fake response 文本。

请求：

```json
{
  "request": "整理项目状态",
  "fake_response": "计划：读取上下文。"
}
```

行为：

- 不解析 provider plan。
- 不应用文件修改。
- 记录 dry-run 任务历史。
- 保持向后兼容，现有 Web 测试不需要改调用路径。

### `POST /api/provider-plan/preview`

请求：

```json
{
  "request": "创建说明",
  "fake_response": "{\"summary\":\"创建说明\",\"operations\":[{\"action\":\"create_text\",\"path\":\"docs/provider.md\",\"content\":\"来自 Web provider\\n\"}]}"
}
```

成功响应：

```json
{
  "ok": true,
  "task_id": null,
  "plan_text": "",
  "dry_run": true,
  "planned_changes": [
    {
      "action": "create_text",
      "path": "docs/provider.md",
      "content_bytes": 19
    }
  ],
  "preview_changes": [
    {
      "action": "create_text",
      "path": "docs/provider.md",
      "exists": false,
      "content_bytes": 19,
      "risk": "create"
    }
  ],
  "applied_changes": [],
  "diff_stat": "",
  "execution_error": null
}
```

失败响应：

```json
{
  "ok": false,
  "error": "无法解析 provider 执行计划：..."
}
```

状态码：

- `200`：preview 成功。
- `400`：请求缺少必填字段、provider plan 解析失败或 preview 预校验失败。

Preview 接口不调用 `LocalTaskRunner`，因此不会创建 `.agent` 任务历史，也不会写文件。

### `POST /api/provider-plan/apply`

请求与 preview 相同。确认动作由调用这个 endpoint 表达；本阶段不再增加额外的确认 token，避免把状态持久化、token 过期和跨浏览器同步拉进范围。

成功响应：

```json
{
  "ok": true,
  "task_id": "task-...",
  "plan_text": "{\"summary\":\"创建说明\",...}",
  "dry_run": false,
  "planned_changes": [
    {
      "action": "create_text",
      "path": "docs/provider.md",
      "content_bytes": 19
    }
  ],
  "preview_changes": [
    {
      "action": "create_text",
      "path": "docs/provider.md",
      "exists": false,
      "content_bytes": 19,
      "risk": "create"
    }
  ],
  "applied_changes": [
    {
      "action": "create_text",
      "path": "docs/provider.md",
      "content_bytes": 19
    }
  ],
  "diff_stat": " docs/provider.md | 1 +",
  "execution_error": null
}
```

失败响应：

```json
{
  "ok": false,
  "error": "执行计划预览失败：..."
}
```

状态码：

- `200`：apply 流程完成。若 runner 返回 `execution_error`，响应仍包含 `ok: true` 和错误字段，由调用方展示执行失败详情。
- `400`：请求参数错误、provider plan 解析失败或 preview 阶段安全校验失败，此时绝不写文件。

Apply 接口必须在调用 runner 前重新解析并重新 preview，不能信任前端上一次 preview 的结果。这样即使文件系统在 preview 和 apply 之间变化，也会被最新预校验拦住。

## 后端数据流

1. `DevAgentHttpHandler` 接收 `/api/provider-plan/preview` 或 `/api/provider-plan/apply`。
2. `_read_json_body()` 按 UTF-8 解码请求体，并要求请求体是 JSON 对象。
3. Web API helper 校验 `request_text.strip()` 和 `fake_response.strip()`。
4. `parse_provider_execution_plan(fake_response)` 解析严格 JSON。
5. `ExecutionPlanApplier(repo_root).preview(execution_plan)` 运行路径安全、action 白名单、create 冲突和目标状态检查。
6. Preview endpoint 返回计划和预览摘要，不创建 runner。
7. Apply endpoint 在 preview 通过后创建 `LocalTaskRunner`，使用 `FakeProvider(name="fake-web-provider-plan", responses=[fake_response])`。
8. Apply endpoint 调用 `runner.run(request_text, TaskRunOptions(dry_run=False, run_verification=False, apply_changes=True, execution_plan=execution_plan))`。
9. Apply endpoint 组合 runner 结果、preview 结果和 `ok` 字段返回给前端。

## 前端交互设计

页面保留当前自然质感视觉方向，不引入前端框架或新增运行时依赖。新增一个“Provider plan 审批”区域，与现有 dry-run 表单并列或放在同一 run panel 内分区展示。

交互状态：

1. `idle`：显示任务 textarea、provider JSON textarea 和“生成预览”按钮；确认执行按钮禁用。
2. `preview_loading`：禁用两个提交按钮，按钮文案显示正在生成预览。
3. `preview_ready`：展示 `planned_changes` 和 `preview_changes`，启用“确认执行”按钮。
4. `apply_loading`：禁用按钮，展示正在执行。
5. `applied`：展示 `applied_changes`、`diff_stat`、`task_id`，并刷新历史。
6. `error`：展示中文错误，保留输入内容，允许修改后重新预览。

可访问性与交互要求：

- 所有 textarea 使用显式 `<label>`。
- 结果区域使用 `aria-live="polite"`。
- 错误区域使用 `role="alert"`。
- 预览风险不能只用颜色表达，必须包含 `create`、`overwrite`、`append` 或 `append_create` 文本。
- 按钮禁用时使用 `disabled` 属性，而不是只改样式。
- 键盘用户可以按 Tab 顺序完成输入、预览和确认。
- 保持移动端单列布局，无横向滚动。

## 安全边界

Web apply 不是自动执行授权。它只代表用户在页面上完成第二步确认。后端仍必须执行全部安全检查：

1. 严格 JSON provider plan 解析。
2. action 白名单。
3. 仓库内路径限制。
4. 禁止 `.git`、`.worktrees`、`.superpowers` 路径。
5. create 冲突检查。
6. apply 前重新 preview。

本阶段不发起真实模型请求，不做并发 agent，不做 provider 探测，不重试失败请求，不执行 Git 写操作，符合供应商熔断保护和破坏性操作拦截要求。

## 错误处理

- 请求体不是 JSON 对象：HTTP 400，`JSON body must be an object`。
- `request` 为空：HTTP 400，`request_text is required`。
- `fake_response` 为空：HTTP 400，`fake_response is required for provider plan preview` 或 `fake_response is required for provider plan apply`。
- provider plan 解析失败：HTTP 400，错误包含“无法解析 provider 执行计划”。
- preview 安全校验失败：HTTP 400，错误包含“执行计划预览失败”。
- runner apply 后返回 `execution_error`：HTTP 200，前端在结果区展示 `execution_error`，历史中保留失败记录。
- 前端 fetch 失败或服务不可用：结果区展示“请求失败，请检查本地服务是否仍在运行”。

## 验证策略

本阶段必须 TDD：

- Web API preview 成功返回 `ok: true`、`planned_changes` 和 `preview_changes`，且不创建 `.agent`、不写文件。
- Web API preview 拒绝 malformed provider JSON，且不写文件。
- Web API preview 拒绝危险路径，且不写文件。
- Web API apply 成功写入文件、返回 `applied_changes`、刷新历史可见任务记录。
- Web API apply 在 preview 安全校验失败时返回 400，且不写文件。
- Web server 路由覆盖 `/api/provider-plan/preview` 和 `/api/provider-plan/apply`。
- 前端表单调用 preview endpoint，preview 成功后显示确认按钮和结果区域。
- 前端 apply 成功后展示执行结果并刷新历史。
- 现有 `/api/run` dry-run 行为保持不变，普通 fake response 不被当 provider plan 解析。

最终验收命令：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
$env:PYTHONPATH=(Resolve-Path 'src').Path
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

临时仓库 smoke：

- `POST /api/provider-plan/preview` 返回 200，包含 `preview_changes`，不创建 `.agent`，不写目标文件。
- `POST /api/provider-plan/apply` 返回 200，写入目标文件，返回 `applied_changes`，并能在 `/api/history` 中看到任务。
- malformed JSON 和危险路径均返回 400，目标文件不存在。

## 后续扩展

本阶段完成后，可以继续拆分：

- 完整人类可读 diff 展示。
- Web 审批记录和一次性确认 token。
- Markdown fenced JSON 解析。
- 真实 provider 输出契约提示词。
- 真实 provider 单请求接入与冷却/熔断 UI 展示。
- Git commit/push 的 Web 审批节点。
