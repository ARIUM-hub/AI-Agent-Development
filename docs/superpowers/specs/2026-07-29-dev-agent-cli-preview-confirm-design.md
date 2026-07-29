# CLI 执行预览与确认 v1 设计

日期：2026-07-29

## 背景与目标

本地执行闭环 v1 已经支持通过结构化 JSON 计划执行小型 UTF-8 文本写入，并具备仓库内路径保护、禁止目录保护、预校验和运行时历史记录。下一阶段目标是在 CLI 层补上“执行前可审阅、执行需确认”的安全闸门。

本阶段仍不接真实模型、不解析 provider 自由文本、不开放 Web 写文件、不自动 Git commit 或 push。它只改进本地 `run --plan-file` 的用户体验和安全边界，让后续真实 provider 输出解析与 Web 审批视图可以复用同一套预览语义。

## 范围

### 包含

- 新增执行计划预览摘要，展示每个操作的 action、path、内容字节数和目标文件当前状态。
- CLI 支持 `--preview`，只输出预览，不写文件。
- CLI `--apply` 默认需要确认；未确认时拒绝写入并返回 CLI 错误。
- CLI 支持 `--yes`，表示用户已经明确授权本次 apply，适合自动化测试和脚本场景。
- 交互式终端中允许输入确认词继续执行；非交互场景必须使用 `--yes`。
- 预览与确认逻辑复用现有 `ExecutionPlanApplier` 的路径安全和预校验能力。
- 所有错误信息保持中文可读，文件读写继续使用 UTF-8。

### 不包含

- 真实云端模型请求。
- provider 输出到结构化计划的自动解析。
- Web 审批页面、浏览器 diff 预览或 Web 写文件。
- 删除、移动、重命名、二进制写入或大规模目录操作。
- Git commit、push、merge、reset 或自动 PR 操作。
- 复杂 unified diff 生成。本阶段只做结构化摘要，不展示完整内容 diff。

## 推荐方案

采用“结构化预览 + 显式授权 apply”的方案。

`ExecutionPlanApplier` 增加可复用的 `describe()` 或增强 `preview()` 能力，用于在不写文件的情况下返回每个目标的状态：文件是否已存在、该动作是否可能覆盖内容、写入内容 UTF-8 字节数，以及路径安全校验后的 planned changes。CLI 根据这份结果输出 JSON 字段，保持机器可读；人类可读的摘要可以作为后续增强。

相比直接在 CLI 里重复检查文件状态，这个方案把安全判断集中在 execution 层，避免 Web 或 runtime 后续各写一套不同逻辑。相比引入完整 patch/diff，本阶段实现更小，能先把确认闸门固定下来。

## CLI 行为

### 只解析计划

```powershell
python -m dev_agent.cli run "预览计划" --fake-response "计划：只预览。" --plan-file plan.json
```

行为：

- 解析 `plan.json`。
- 输出 `planned_changes`。
- 输出 `preview_changes`。
- 不写文件。
- 返回码为 0。

### 显式预览

```powershell
python -m dev_agent.cli run "预览计划" --fake-response "计划：只预览。" --plan-file plan.json --preview
```

行为：

- 与只解析计划一样不写文件。
- 明确输出预览字段，便于用户或脚本在 apply 前检查。
- 如果计划包含危险路径或 create 冲突，返回 CLI 错误，不写文件。

### 未确认 apply

```powershell
python -m dev_agent.cli run "应用计划" --fake-response "计划：写文件。" --plan-file plan.json --apply
```

行为：

- 先解析并预校验计划。
- 如果当前 stdin 不是交互式终端，拒绝执行并提示需要 `--yes`。
- 如果当前 stdin 是交互式终端，提示用户输入确认词。
- 用户未输入确认词时返回 2，不写文件。

确认词第一版使用 `yes`。后续如需中文确认词，可以扩展为 `yes` 或 `确认`，但本阶段保持单一确认词，便于测试和脚本化。

### 已确认 apply

```powershell
python -m dev_agent.cli run "应用计划" --fake-response "计划：写文件。" --plan-file plan.json --apply --yes
```

行为：

- 解析并预校验计划。
- 应用结构化文件操作。
- 输出 `applied_changes`、`diff_stat` 和 `execution_error`。
- 返回码沿用当前规则：执行成功为 0，执行失败为 1，CLI 参数或计划读取错误为 2。

## 预览数据模型

新增 `ExecutionPreviewChange`：

- `action: str`
- `path: str`
- `exists: bool`
- `content_bytes: int`
- `risk: str`

`risk` 第一版取值：

- `create`：目标不存在，将创建新文件。
- `overwrite`：目标存在，`overwrite_text` 会覆盖文件。
- `append`：目标存在，`append_text` 会追加内容。
- `append_create`：目标不存在，`append_text` 会创建文件并写入内容。

如果 `create_text` 目标已存在，预览阶段直接抛出 `ExecutionPlanError`，不返回 `risk`。

## 数据流

1. CLI 读取 `--plan-file`，兼容 UTF-8 BOM。
2. `parse_execution_plan()` 校验 JSON 结构和 action 白名单。
3. `ExecutionPlanApplier.preview()` 执行路径安全、操作冲突和目标状态检查。
4. CLI 输出 `planned_changes` 与 `preview_changes`。
5. 如果未传 `--apply`，流程结束。
6. 如果传了 `--apply`，CLI 检查 `--yes` 或交互式确认。
7. 未确认时返回 2，不调用 `LocalTaskRunner.run(... apply_changes=True)`。
8. 已确认时调用 runner 执行现有 apply 流程。
9. runner 写入历史并输出执行结果。

## 错误处理

- 缺少 `--plan-file` 但传入 `--apply`：返回 2。
- 计划文件不存在、JSON 错误或 BOM 后仍无法解析：返回 2，并输出中文“无法读取执行计划”。
- 路径逃逸、禁用目录、create 冲突或未知 action：返回 2，并输出中文“执行计划预览失败”。
- `--apply` 未确认：返回 2，并输出中文“应用执行计划需要确认”。
- 已确认 apply 后发生写入错误：沿用 runner 的 `execution_error`，返回 1。

## 安全边界

本阶段的安全原则是“预览失败则绝不写入，未确认则绝不写入”。所有 apply 前必须先通过同一套预校验。`--yes` 不是绕过安全校验，只是绕过交互式确认。

Web `/api/run` 继续保持 dry-run。即使请求体包含执行计划，也不写文件。

## 验证策略

本阶段必须 TDD：

- 执行器 preview 返回目标存在状态、字节数和风险标签。
- 执行器 preview 对危险路径和 create 冲突失败且不写文件。
- CLI `--preview` 输出 `preview_changes` 且不写文件。
- CLI `--apply` 在非交互环境未传 `--yes` 时拒绝写入。
- CLI `--apply --yes` 执行写入。
- CLI 计划预览失败时返回 2，并保持文件不变。
- 全量测试继续通过。

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

再用临时仓库 smoke 覆盖：

- `run --plan-file plan.json --preview`
- `run --plan-file plan.json --apply`，期望未确认失败且不写文件。
- `run --plan-file plan.json --apply --yes`，期望写入成功。

## 后续扩展

本阶段完成后，可以继续拆分：

- provider 输出到结构化执行计划的安全解析。
- Web 审批视图与 diff 预览。
- 更完整的人类可读 diff 展示。
- 交互式确认词本地化和配置化。
- 可回滚的事务式文件操作。
