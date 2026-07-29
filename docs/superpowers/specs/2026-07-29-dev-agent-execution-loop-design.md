# 本地执行闭环 v1 设计

日期：2026-07-29

## 背景与目标

当前项目已经具备 CLI 基础、项目扫描、provider 保护、命令执行器、Git 只读能力、验证规划、历史记忆、本地 dry-run 运行时和 Web 控制台。下一阶段目标是把 dry-run 从“只生成计划”推进到“可以安全应用小型本地文件修改、运行验证、记录结果”的第一条闭环。

本阶段仍然坚持安全优先：不接真实云端模型，不做批量模型请求，不自动推送，不做破坏性 Git 操作。智能体只执行显式传入的结构化本地文件操作计划，用于验证文件写入、diff 摘要、验证命令和历史记录能串成端到端链路。

## 范围

### 包含

- 定义结构化执行计划，支持创建文本文件、覆盖文本文件和追加文本文件。
- 所有文件写入限制在仓库根目录内。
- 拒绝绝对路径、父目录逃逸路径、`.git` 内路径、`.worktrees` 内路径和空路径。
- 写入前后使用 UTF-8 读写工具，中文内容保持可读，不使用 `\uXXXX` 转义。
- 支持 `LocalTaskRunner` 在显式 `apply_changes=True` 时应用结构化计划。
- 应用改动后生成 Git diff 摘要。
- 应用改动后可运行现有验证计划，并把验证结果写入任务历史。
- 新增 CLI 能力：通过本地 JSON 文件传入执行计划，例如 `run "任务" --plan-file plan.json --apply --verify`。
- Web `/api/run` 继续保持 dry-run，不在本阶段开放真实文件修改。

### 不包含

- 真实模型输出解析。
- 自动生成代码补丁。
- 删除文件、重命名文件、二进制文件写入或大规模目录操作。
- Git commit、push、merge 或 reset。
- 自动修复验证失败。
- 并发执行多个文件计划。
- Web 页面审批和远程操作。

## 推荐方案

采用“结构化计划 + 安全执行器 + 运行时集成”的方案。

结构化计划使用 JSON 表示，包含 `summary` 和 `operations`。每个 operation 声明 `action`、`path` 和 `content`。执行器只理解少量白名单动作，先校验路径和文本，再调用现有 UTF-8 写入能力落盘。运行时不负责解释自然语言补丁，也不信任 provider 原始文本；本阶段的 `plan_file` 是显式测试入口，为后续真实 provider 输出解析留下接口边界。

相比直接让 fake provider 返回自由文本补丁，这个方案更可测试、更安全，也能自然接入后续审批流。相比引入完整 patch 格式，本阶段实现更小，足够验证端到端闭环。

## 核心数据模型

新增 `execution` 包：

- `ExecutionOperation`：单个文件操作。
- `ExecutionPlan`：结构化执行计划。
- `ExecutionChange`：实际写入后的变更摘要。
- `ExecutionResult`：执行结果、变更列表和 diff 摘要。

支持动作：

- `create_text`：目标文件必须不存在，创建 UTF-8 文本文件。
- `overwrite_text`：目标文件可存在，使用 UTF-8 内容覆盖。
- `append_text`：目标文件可存在，不存在时创建，向末尾追加 UTF-8 内容。

第一版不支持删除、移动和 chmod。拒绝未知 action，避免未来扩展被静默当成成功。

## 路径与编码安全

路径校验优先级高于写入：

1. `path` 必须是相对路径。
2. 解析后的绝对路径必须仍位于 `repo_root` 内。
3. 路径不能指向 `.git`、`.worktrees`、`.superpowers` 内部。
4. 路径不能为空，不能只包含空白。
5. 操作目标必须按文本处理，内容类型为字符串。

所有实际写入使用项目已有 UTF-8 工具。遇到中文内容时直接写中文字符，测试中显式断言中文在文件和历史记录中可读。

## 运行时集成

`TaskRunOptions` 增加：

- `apply_changes: bool = False`
- `execution_plan: ExecutionPlan | None = None`

`LocalTaskRunner.run()` 行为：

1. 创建任务状态。
2. 解析上下文。
3. 使用 fake provider 生成计划文本。
4. 如果 `apply_changes=False`，保持当前 dry-run 行为，不写文件。
5. 如果 `apply_changes=True`，必须提供 `execution_plan`。
6. 调用 `ExecutionPlanApplier` 应用结构化文件操作。
7. 读取 Git diff stat，写入结果摘要。
8. 若 `run_verification=True`，运行验证计划。
9. 将 provider 计划、执行变更、验证结果和事件写入历史。

如果执行计划校验失败，任务状态为 `failed`，历史记录保留错误摘要，且不会执行后续文件操作。多个操作按顺序执行；任一操作失败时停止后续操作。本阶段不实现事务回滚，因为所有操作都限定为小范围文本修改，并且 Git diff 可展示实际结果。

## CLI 设计

新增 `run` 参数：

```powershell
python -m dev_agent.cli run "创建说明文件" --fake-response "计划：创建 README 片段。" --plan-file plan.json --apply --verify
```

计划文件示例：

```json
{
  "summary": "创建本地执行闭环说明",
  "operations": [
    {
      "action": "create_text",
      "path": "docs/local-execution.md",
      "content": "# 本地执行闭环\n\n所有文本使用 UTF-8。\n"
    }
  ]
}
```

规则：

- `--apply` 未传入时，`--plan-file` 只解析并在输出中报告 `planned_changes`，不写文件。
- `--apply` 传入时必须有 `--plan-file`。
- `--apply` 和 `--dry-run` 可以同时存在；含义是“应用本地结构化计划，但不接真实模型、不自动 Git 提交或推送”。
- CLI JSON 输出增加 `applied_changes`、`diff_stat`、`execution_error`。

## Web 控制台策略

本阶段不让 Web `/api/run` 写文件。Web 仍然只能提交 fake-provider dry-run，这是故意保守的边界。

后续若要开放 Web 写入，必须先增加审批视图、diff 预览和显式确认。这样可以避免浏览器表单误触直接修改仓库文件。

## 错误处理

错误分为：

- 计划解析错误：JSON 不合法、缺少 operations、字段类型错误。
- 路径安全错误：绝对路径、父目录逃逸、禁止目录、空路径。
- 操作冲突错误：`create_text` 目标已存在、未知 action。
- 写入错误：权限不足、目录不可创建、文件被占用。
- 验证失败：执行成功但测试、lint、类型检查或构建失败。

CLI 对计划和路径错误返回非零退出码，并输出中文可读错误。运行时历史记录需要包含失败摘要，便于后续记忆召回。

## 验证策略

本阶段必须 TDD：

- 执行器路径安全测试。
- `create_text`、`overwrite_text`、`append_text` 行为测试。
- UTF-8 中文写入测试。
- 运行时 apply 成功后写历史和 diff stat 测试。
- 运行时计划错误失败并写历史测试。
- CLI `--plan-file --apply --verify` 测试。
- Web dry-run 不会应用文件修改的回归测试。

最终验收命令：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
$env:PYTHONPATH=(Resolve-Path 'src').Path
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli run "验证执行闭环" --fake-response "计划：应用结构化文件操作。" --plan-file <temp-plan.json> --apply --verify
git status --short
```

验收时 smoke 文件应在临时仓库中运行，避免污染研发助手自身 worktree。

## Git 与安全边界

本阶段允许读取 Git diff stat，用于交付摘要和历史记录。禁止任何 Git 写操作，包括 commit、push、merge、reset、checkout 覆盖、clean。

远程 push 仍属于人工确认节点，由当前开发协作流程在 PR 阶段处理，不由研发助手运行时自动触发。

## 后续扩展

本阶段完成后，后续可以继续拆分：

- provider 输出到结构化执行计划的安全解析。
- CLI diff 预览和用户确认。
- Web 审批视图与 diff 预览。
- 更接近真实研发任务的端到端样例。
- 可回滚的事务式文件操作。

这些都不进入本阶段，以保持闭环小、可测、可审。
