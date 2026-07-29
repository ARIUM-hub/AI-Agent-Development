# Provider 计划解析 v1 设计

日期：2026-07-29

## 背景与目标

当前研发助手已经具备结构化执行计划、仓库内安全写入、CLI 预览和显式确认闸门。现有执行入口仍主要依赖 `--plan-file` 从本地 JSON 文件传入计划，provider 返回文本只作为 `plan_text` 记录，尚未参与结构化执行。

本阶段目标是在不接真实云端模型、不增加供应商请求风险的前提下，让 fake/provider 返回的严格 JSON 文本可以被解析为 `ExecutionPlan`，并复用现有 preview 与 `--yes` 安全流程。这样后续接真实 provider 时，任务引擎已经有清晰边界：provider 只负责给出结构化计划，execution 层负责校验和执行。

## 范围

### 包含

- 新增 provider 文本到 `ExecutionPlan` 的解析入口。
- 第一版只接受严格 JSON 对象文本，不接受 Markdown fenced JSON、自然语言混排 JSON 或补丁格式。
- CLI 新增 `--use-provider-plan`，显式启用从 fake provider 响应解析结构化计划。
- `--use-provider-plan --preview` 只预览计划，不写文件，不创建 `.agent` task/history 状态。
- `--use-provider-plan --apply` 仍必须通过 `--yes` 或交互式确认，不能绕过现有安全闸门。
- 解析失败、非法 action、危险路径或预览失败时返回 CLI 错误，不写文件。
- `--plan-file` 保持更高优先级；同时传入 `--plan-file` 和 `--use-provider-plan` 时，第一版拒绝该组合，避免来源歧义。
- 所有中文错误和 JSON 输出保持 UTF-8 可读。

### 不包含

- 真实云端模型调用。
- 自动从自然语言中提取 JSON。
- Markdown 代码块解析。
- 自动修复 malformed JSON。
- 多 provider 尝试、批量重试或健康探测。
- Web 写文件或 Web 审批视图。
- 删除、移动、重命名、二进制写入、Git commit/push。

## 推荐方案

采用“显式 provider plan 模式 + 严格 JSON 解析”的方案。

CLI 默认行为不变：fake provider 响应仍作为普通计划文本。只有用户传入 `--use-provider-plan` 时，CLI 才把 fake provider 响应当作执行计划 JSON 解析。解析成功后，走与 `--plan-file` 完全相同的预览、确认和 apply 流程。

相比默认自动解析 provider 文本，这个方案避免把普通自然语言计划误判为可执行计划。相比支持 fenced JSON 或混排文本，本阶段的严格 JSON 更可测试，也更适合作为未来真实 provider 的输出契约。

## CLI 行为

### 普通 provider 文本

```powershell
python -m dev_agent.cli run "整理项目" --fake-response "计划：读取文件并总结。"
```

行为：

- 保持现状。
- 不解析 provider 文本。
- 不生成 `planned_changes` 或 `preview_changes`。
- 会进入 runner dry-run，并记录普通任务历史。

### Provider JSON 预览

```powershell
python -m dev_agent.cli run "创建说明" --fake-response '{"summary":"创建说明","operations":[{"action":"create_text","path":"docs/provider.md","content":"来自 provider\n"}]}' --use-provider-plan --preview
```

行为：

- 解析 `--fake-response` 为 `ExecutionPlan`。
- 调用 `ExecutionPlanApplier.preview()`。
- 输出 `planned_changes` 和 `preview_changes`。
- 不调用 runner，不创建 `.agent` task/history 状态，不写文件。

### Provider JSON 未确认 apply

```powershell
python -m dev_agent.cli run "创建说明" --fake-response '<json plan>' --use-provider-plan --apply
```

行为：

- 先解析并预览 provider plan。
- 未传 `--yes` 且非交互确认时返回 2。
- 不调用 runner，不写文件。

### Provider JSON 确认 apply

```powershell
python -m dev_agent.cli run "创建说明" --fake-response '<json plan>' --use-provider-plan --apply --yes
```

行为：

- 解析 provider plan。
- 通过 preview 安全校验。
- 调用 runner apply 流程。
- 写入文件、记录任务历史、输出 `applied_changes` 和 `diff_stat`。

### 歧义组合

```powershell
python -m dev_agent.cli run "创建说明" --fake-response '<json plan>' --plan-file plan.json --use-provider-plan
```

行为：

- 返回 2。
- 输出中文错误，说明 `--plan-file` 不能与 `--use-provider-plan` 同时使用。
- 不写文件。

## 解析模块

新增 `src/dev_agent/execution/provider_plan.py`：

- `parse_provider_execution_plan(text: str) -> ExecutionPlan`

规则：

1. `text.strip()` 必须是 JSON 对象。
2. 使用 `json.loads()` 解析。
3. 解析结果交给现有 `parse_execution_plan()`。
4. `json.JSONDecodeError` 和 `ExecutionPlanError` 都包装为 `ExecutionPlanError`，错误信息包含“无法解析 provider 执行计划”。
5. 空文本、JSON 数组、JSON 字符串、缺少 operations、未知 action 都失败。

该模块不读取文件、不写文件、不调用 provider，只负责纯函数解析。

## 数据流

1. CLI 接收 `request`、`--fake-response`、`--use-provider-plan`。
2. 如果同时存在 `--plan-file` 和 `--use-provider-plan`，立即返回 2。
3. 如果使用 `--plan-file`，沿用现有 plan-file 流程。
4. 如果使用 `--use-provider-plan`，解析 `args.fake_response` 为 `ExecutionPlan`。
5. 对解析出的计划执行 preview。
6. 如果未传 `--apply`，输出 preview payload 并结束。
7. 如果传了 `--apply`，执行确认闸门。
8. 确认后调用 runner，并把解析出的 `execution_plan` 放入 `TaskRunOptions`。

## 错误处理

- provider 响应不是合法 JSON：返回 2，输出“无法解析 provider 执行计划”。
- provider JSON 不是对象：返回 2。
- provider JSON 结构不符合执行计划：返回 2。
- provider JSON 中包含危险路径或 create 冲突：返回 2，输出“执行计划预览失败”。
- 未确认 apply：返回 2，输出“应用执行计划需要确认”。
- 已确认 apply 后写入失败：沿用 runner 的 `execution_error`。

## 安全边界

`--use-provider-plan` 不是自动执行授权。它只改变计划来源，从本地文件变为 provider 文本。所有文件写入仍必须经过：

1. 严格 JSON 结构解析。
2. action 白名单。
3. 路径安全和计划内冲突预校验。
4. CLI preview。
5. `--yes` 或交互式确认。

本阶段不增加任何真实模型请求，也不做多 provider 尝试、批量重试或健康检查，符合供应商熔断保护要求。

## 验证策略

本阶段必须 TDD：

- provider plan parser 接受严格 JSON 对象。
- provider plan parser 拒绝普通文本、数组 JSON、非法 action 和 malformed JSON。
- CLI 默认不解析普通 fake response，保持旧 dry-run 行为。
- CLI `--use-provider-plan --preview` 输出 preview 且无 `.agent` 副作用。
- CLI `--use-provider-plan --apply` 未确认时拒绝写入。
- CLI `--use-provider-plan --apply --yes` 写入成功。
- CLI 同时传 `--plan-file` 和 `--use-provider-plan` 返回 2。
- CLI provider plan 危险路径返回 2 且不写文件。

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

- `run --fake-response '<json plan>' --use-provider-plan --preview`
- `run --fake-response '<json plan>' --use-provider-plan --apply`，期望返回 2 且不写文件。
- `run --fake-response '<json plan>' --use-provider-plan --apply --yes`，期望写入成功。

## 后续扩展

本阶段完成后，可以继续拆分：

- 真实 provider 输出契约提示词。
- Markdown fenced JSON 解析。
- provider plan schema 版本字段。
- Web 审批视图复用 provider plan preview。
- 更完整的人类可读 diff 展示。
