# 受控 Git 提交设计规格

## 背景

研发助手已经支持从 fake、plan-file 或单次 OpenAI-compatible `/v1/chat/completions` 请求取得严格执行计划，先生成零副作用预览与 Diff，确认后应用目标文件，并按项目配置执行验证。当前流程在验证结束后停止，用户仍需自行检查 Git 状态、暂存文件和创建提交。

本阶段新增可选的受控 Git 提交能力。只有用户显式同时启用 apply、verify 和 commit，并提供提交信息时，系统才会在验证全部通过后进行第二次确认，仅提交本次已审批执行计划实际修改的目标文件。该能力不自动 push、merge 或 amend，不增加模型请求，也不向 Web 开放 Git 写入口。

## 目标

- CLI 提供显式 `--commit` 与 `--commit-message`，默认行为完全不变。
- 提交只包含本次已审批执行计划实际修改的目标路径。
- 仓库可以存在无关旧改动，但目标路径在 apply 前必须干净。
- commit 模式必须执行至少一条验证命令，且所有验证通过。
- apply 后重新检查 HEAD、分支和完整工作区状态，发现目标外新变化时拒绝提交。
- 验证通过后单独确认 commit；`--yes` 可以预授权 apply 与 commit 两次确认。
- commit 或 hook 失败时只取消目标路径的新增暂存，保留目标正文和无关暂存。
- JSON 和任务历史记录成功、拒绝或失败结果，但不泄露绝对路径、密钥或过长 hook 输出。
- fake、plan-file 和真实 Provider 均复用相同提交边界；真实 Provider 请求数仍为 1。

## 非目标

- 自动 push、创建 PR、merge、rebase、cherry-pick、amend、tag 或发布。
- 自动生成或改写 commit message。
- 自动选择提交文件、提交执行计划之外的文件或提交空变更。
- 要求整个仓库在运行前干净。
- 使用临时 index、`git commit-tree` 或其他 plumbing 命令绕过普通 Git/hook 流程。
- 自动 stash、回滚工作区正文、清理验证产物或修复 hook 失败。
- Web Git 写接口或浏览器中的提交按钮。
- OpenAI Responses API、重试、并发、模型探测或供应商故障转移。

## 用户流程

用户显式请求应用、验证和提交：

```powershell
dev-agent run "修复参数校验" `
  --provider openai-compatible `
  --context-file src/dev_agent/cli.py `
  --apply --verify --commit `
  --commit-message "fix: validate run arguments"
```

流程固定为：

1. 取得并解析执行计划，生成预览与 Diff。
2. 根据计划目标执行 Git commit 预检并保存初始快照。
3. 确认 apply 后应用执行计划。
4. 执行至少一条验证命令。
5. 验证通过后比较 Git 快照，只允许目标路径产生本次变化。
6. 显示待提交 message 和实际变化路径，第二次确认 commit。
7. 只暂存并提交这些实际变化路径。
8. 校验新提交的父提交和文件集合，输出结果并写入历史。

未传 `--commit` 时，原有 preview、apply 和 verify 流程保持不变。

## CLI 契约

### 新增参数

- `--commit`：在 apply 和 verify 成功后创建受控提交。
- `--commit-message MESSAGE`：提供显式提交信息。

`--commit` 必须同时满足：

- 已传 `--apply`。
- 已传 `--verify`。
- 已传 `--commit-message`。
- 最终验证计划至少包含一条命令。

`--commit-message` 规则：

- 必须是字符串长度 1 至 200 个字符。
- 不自动 trim 后替用户接受空白消息；纯空白消息拒绝。
- 必须是单行，拒绝 `\r`、`\n` 和 NUL。
- 只作为参数数组中的独立值传给 Git，不经过 shell 拼接。
- 不从用户请求、Provider summary 或执行计划自动生成。

未传 `--commit` 时单独传 `--commit-message` 视为参数错误，避免用户误以为已经提交。

参数组合错误、空验证计划和 apply 前 Git 预检失败均在目标写入前返回退出码 `2`。验证失败、apply 后 Git 安全检查失败或 commit 执行失败返回退出码 `1`。用户拒绝 apply 或第二次 commit 确认返回退出码 `2`。

### 两次确认

未传 `--yes` 时：

- 第一次确认沿用现有 apply 确认，在任何写入前发生。
- 第二次确认必须在 apply 完成、验证全部通过且 commit readiness 检查通过后发生。
- 第二次提示显示提交信息和仓库相对目标路径，不显示绝对路径。
- 非交互终端无法确认时安全拒绝。

传入 `--yes` 表示用户在命令开始时同时预授权这两次确认，不再读取 stdin，但不能绕过预检、验证、快照比较或提交后校验。

## JSON 输出

所有现有 payload 增加稳定字段：

```json
{
  "git_commit": null,
  "commit_error": null
}
```

成功提交时：

```json
{
  "git_commit": {
    "sha": "完整小写 Git SHA",
    "message": "fix: validate run arguments",
    "paths": ["src/dev_agent/cli.py"]
  },
  "commit_error": null
}
```

规则如下：

- `paths` 是去重、按 POSIX 仓库相对路径排序的实际提交文件。
- preview、未启用 commit、Web 请求、验证失败和用户拒绝时 `git_commit` 为 `null`。
- apply 后安全检查失败或 Git commit/hook 失败时 `commit_error` 为脱敏中文错误。
- 参数错误和 apply 前预检错误延续现有 stderr 错误形式，不构造任务结果 JSON。
- 验证失败由现有 `verification_passed: false` 表达，`commit_error` 保持 `null`，避免把测试失败误称为 Git 错误。
- 第二次确认被拒绝不是 commit 执行故障，`commit_error` 保持 `null`。

Web payload 同样包含两个空字段，以稳定结果 schema，但 Web API 不接受 commit 参数，也不调用 Git 写能力。

## 架构

### `GitCommitGuard`

新增独立的 `GitCommitGuard`，集中承担 Git 写入安全策略。CLI 和 runner 不自行拼装 Git 命令或解释 porcelain 输出。

主要数据类型：

```text
GitCommitSnapshot
  head_sha: str
  branch: str
  status_entries: tuple[GitStatusEntry, ...]
  target_paths: tuple[str, ...]

GitCommitRequest
  message: str
  target_paths: tuple[str, ...]

GitCommitResult
  sha: str
  message: str
  paths: tuple[str, ...]
```

主要阶段：

```text
preflight(request, verification_plan) -> GitCommitSnapshot
prepare_commit(snapshot) -> tuple[str, ...]
commit(snapshot, message, changed_paths) -> GitCommitResult
```

- `preflight()` 在 apply 前运行，验证仓库、分支、操作状态、验证计划和目标初始状态。
- `prepare_commit()` 在验证通过后运行，比较快照并返回实际变化目标；它不暂存、不提交。
- `commit()` 只处理已通过 readiness 检查的路径，并执行提交后校验。

所有 Git 子进程均通过参数数组执行，禁用 shell 字符串插值。Git 命令 stdout/stderr 设置有界采集，供错误脱敏和历史审计。

### runner 集成

`TaskRunOptions` 增加可选的 commit request 和提交确认回调。只有 CLI commit 模式提供它们；Web 和原有调用方保持 `None`。

`LocalTaskRunner` 的 commit 模式顺序为：

1. 使用已预览的执行计划和 `GitCommitGuard` 快照。
2. apply 并记录 `execution_completed`。
3. 运行非空验证计划。
4. 验证失败时直接结束，不调用确认回调或任何 Git 写命令。
5. 调用 `prepare_commit()` 完成第二次状态检查。
6. 无实际差异或发现状态漂移时拒绝提交。
7. 调用 CLI 注入的确认回调；拒绝时保留现场。
8. 调用 `commit()`，将结果放入 `TaskRunResult`。
9. 最终统一写任务状态和历史，确保 commit 事件与结果属于同一任务。

确认回调只负责取得用户选择，不执行 Git 命令。`--yes` 使用恒真回调；交互模式使用 CLI 的单次 stdin 确认。用户拒绝以独立控制结果传播到 CLI，使退出码为 `2`，而不是伪装成 Git 异常。

## Git 预检与快照

### 仓库与 HEAD

preflight 必须确认：

- 当前目录位于 Git worktree，仓库根目录与运行根目录一致。
- `HEAD` 可以解析为完整 commit SHA；不支持 unborn branch。
- 当前处于正常命名分支，拒绝 detached HEAD。
- 保存分支完整名称和初始 HEAD。

以下任一 Git 操作进行中时拒绝：

- merge
- rebase（apply 或 merge 后端）
- cherry-pick
- revert
- bisect

检测路径通过 `git rev-parse --git-path <marker>` 解析，不硬编码 `.git` 为目录，以兼容 worktree 的 gitfile 布局。

### 状态快照

状态快照固定使用机器可解析且不受本地化影响的命令：

```text
git status --porcelain=v1 -z --untracked-files=all
```

解析器必须正确处理空格、引号、中文和 rename/copy 的双路径记录。快照保存整个仓库每个路径的 index/worktree 状态，而不是保存人类可读文本后做字符串替换。

状态比较使用规范化仓库相对 POSIX 路径。所有来自执行计划的目标先经过现有 `ExecutionPlanValidator.resolve_target()`，再转换为相对路径；拒绝仓库外路径、目录目标和重复规范化冲突。

### 目标初始状态

每个执行计划目标在 apply 前必须满足：

- 没有 staged 或 unstaged 改动。
- 不是已存在的未跟踪文件。
- 对 create 操作，目标不存在且不能被 Git ignore 规则忽略。
- 对修改操作，目标是正常可解析路径；其存在性和编码继续由执行计划预览校验。

被忽略的新建目标不会出现在普通 porcelain 中，因此 create 目标额外使用参数数组执行 `git check-ignore -q -- <path>`。命中 ignore 规则即提前拒绝，避免 apply 后生成无法安全提交的文件。

仓库中的无关 staged、unstaged 和 untracked 旧状态允许存在，并完整保存在初始快照中。

## apply 后安全检查

验证全部通过后，`prepare_commit()` 重新读取 HEAD、分支和完整 porcelain 状态，并强制：

- HEAD 必须仍等于初始 HEAD。
- 分支必须仍等于初始分支，且仍不是 detached HEAD。
- 不能新进入 merge/rebase/cherry-pick/revert/bisect 状态。
- 所有目标外路径的状态记录必须与初始快照逐项相同。
- 所有初始无关 staged 改动仍保持相同 index/worktree 状态。
- 每个新增、删除或修改的状态路径都必须属于计划目标集合。

目标路径允许从干净状态变为本次 apply 的修改状态。实际提交路径取计划目标与当前差异的交集，并再次通过 `git diff`/状态信息确认。执行计划列出但最终内容与 HEAD 相同的目标不加入提交集合。

如果验证命令生成缓存、覆盖报告、快照或其他目标外文件，即使它们看似无害，也视为状态漂移并拒绝提交。系统保留这些文件供用户检查，不自动删除。

实际变化路径为空时拒绝创建空提交，返回明确错误并保留现场。

## 暂存与提交

只采用普通 Git porcelain 命令，不使用临时 index 或 tree plumbing。

执行顺序：

1. 记录目标暂存前状态。
2. 使用参数数组执行 `git add -- <changed_paths>`。
3. 再次检查 index，确保目标对应暂存差异存在，且无关 index 状态与初始快照一致。
4. 使用参数数组执行 `git commit --only -m <message> -- <changed_paths>`。
5. 读取新的 HEAD、父提交、提交 message 和 `git diff-tree` 文件集合。

`--only` 是提交隔离的最后一道边界：即使仓库运行前已有无关 staged 内容，也只能提交明确路径。不得使用 `git commit -a`、不带路径的 `git commit` 或 `--amend`。

提交成功必须同时满足：

- 新 HEAD 与初始 HEAD 不同。
- 新提交恰好有一个父提交，且父提交等于初始 HEAD。
- 当前分支仍等于初始分支。
- 新提交的文件集合与 `changed_paths` 完全相同。
- 新提交 message 与用户提供的 message 完全相同。
- 初始无关 staged/unstaged/untracked 状态仍保持原样。

任一提交后校验失败均报告严重的 commit 错误并保留现场，不自动 reset 已创建提交。历史必须明确记录校验失败，避免误报成功。

## 失败恢复

`git add`、hook 或 `git commit` 返回非零时：

- 使用参数数组执行 `git restore --staged -- <changed_paths>`，把目标 index 恢复到当前 HEAD。
- 本版要求 Git 支持 `git restore --staged`；命令不可用或执行失败时停止自动恢复并提示人工检查，不尝试其他 reset 或 checkout 命令。
- 只处理本次目标路径，不改变无关 staged 内容。
- 不删除、覆盖或回滚目标工作区正文。
- 恢复后重新检查无关 index 状态；如恢复本身失败，在错误中明确提示需要人工检查。

用户拒绝第二次确认、验证失败、状态漂移或空差异发生在暂存前，因此无需恢复 index，直接保留现场。

hook 可能修改工作区或 index。hook 失败后仍按上述规则只取消目标暂存；任何 hook 产生的目标外变化都保留并在错误中提示，不自动清理。

## 错误、脱敏与事件

新增事件：

- `commit_preflight_completed`
- `commit_completed`
- `commit_rejected`
- `commit_failed`

事件顺序与真实阶段一致。apply 前预检成功才记录 `commit_preflight_completed`；用户拒绝、状态漂移和空差异记录 `commit_rejected`；Git 命令或提交后校验失败记录 `commit_failed`。

错误和历史遵循以下规则：

- 路径只显示仓库相对 POSIX 路径，不显示绝对仓库路径。
- commit message 可以显示，因为它由用户显式提供。
- Git SHA 仅在成功结果中完整返回；错误中如需关联只使用短 SHA。
- Git/hook stdout 和 stderr 先移除绝对仓库路径、Authorization、API Key 等敏感模式，再截断到固定上限。
- 不把执行计划正文、源码正文或环境变量写入 commit 错误。
- hook 输出截断时明确标记已截断。

`TaskRunResult`、CLI payload 和历史记录增加 `git_commit` 与 `commit_error`。成功历史包含 SHA、message 和相对路径；失败历史包含阶段、脱敏错误和事件，不声称已提交。

## 模块变更

### 新建

`src/dev_agent/git/commit_guard.py`

- Git 状态结构化解析。
- 仓库操作状态检测。
- preflight、快照比较、目标路径隔离。
- 暂存、commit、失败恢复和提交后校验。
- Git 输出脱敏与有界错误。

`src/dev_agent/git/models.py`

- `GitStatusEntry`。
- `GitCommitSnapshot`。
- `GitCommitRequest`。
- `GitCommitResult`。
- commit 阶段错误类型。

### 修改

`src/dev_agent/runtime/models.py`

- `TaskRunOptions` 增加可选 commit request 与确认回调。
- `TaskRunResult` 增加 `git_commit`、`commit_error` 和确认拒绝状态。

`src/dev_agent/runtime/runner.py`

- 在 apply 前接收已完成的 commit preflight。
- 验证通过后执行 readiness、确认和 commit。
- 统一任务状态、事件与历史记录。

`src/dev_agent/cli.py`

- 注册和校验 `--commit`、`--commit-message`。
- 在 apply 前创建快照。
- 提供第二次确认回调。
- 输出新增 JSON 字段并映射退出码。

`src/dev_agent/web/api.py`

- 只补充稳定的空 `git_commit` 和 `commit_error` 字段，不解析或传递 Git 写参数。

现有 `src/dev_agent/tools/git.py` 保持只读运行时上下文职责，不向其中混入提交策略。

## 测试策略

所有 Git 测试使用独立临时本地仓库和本地身份配置，不访问网络。

### 参数与消息

- `--commit` 缺少 apply、verify 或 message 时拒绝。
- 未启用 commit 却传 message 时拒绝。
- message 接受 1 至 200 字符的单行中文或英文。
- 空、纯空白、超过 200 字符、CR、LF 或 NUL 消息拒绝。
- shell 元字符只作为 message 正文，不被执行。
- 空验证计划在 apply 前拒绝。

### preflight

- 正常分支和干净目标通过。
- 目标已有 unstaged、staged 或 untracked 改动时拒绝。
- 被 ignore 的 create 目标提前拒绝。
- detached HEAD 和 unborn branch 拒绝。
- merge、两类 rebase、cherry-pick、revert 和 bisect 状态拒绝。
- 无关 unstaged、staged 和 untracked 改动允许存在并进入快照。
- 中文、空格和 rename 路径的 porcelain 解析正确。

### apply 后隔离

- 仅目标发生变化时 readiness 通过。
- 无关原状态完全未变时保持通过。
- verifier 新建、修改、删除或暂存目标外路径时拒绝。
- HEAD 或分支在运行期间变化时拒绝。
- 运行期间进入 Git 操作状态时拒绝。
- 计划目标最终无差异时不创建空提交。
- 多个计划目标中只提交实际有差异的目标。

### 确认与失败恢复

- 交互模式在验证通过后才请求第二次确认。
- 用户拒绝后不暂存、不提交，退出码为 `2`。
- `--yes` 同时跳过 apply 和 commit 的 stdin 读取，但保留安全检查。
- `git add` 失败、commit hook 失败和 Git commit 失败返回退出码 `1`。
- 失败后目标正文保留，目标不再 staged。
- 无关 staged、unstaged 和 untracked 状态保持原样。
- hook 产生的额外文件保留并被报告。
- 恢复失败时给出明确、脱敏的人工检查提示。

### 成功提交

- 单目标和多目标提交成功。
- 新提交父提交严格等于初始 HEAD。
- 提交文件集合严格等于实际变化目标。
- 无关 staged 文件不进入提交且继续保持 staged。
- SHA、message、排序路径写入 JSON 和历史。
- 事件包含 preflight 与 completed，且顺序正确。
- 不创建 amend、merge commit 或空提交。

### 入口与供应商保护

- fake + provider-plan 的 commit 流程。
- plan-file 的 commit 流程。
- OpenAI-compatible 使用进程内 `127.0.0.1` HTTPServer 完成 preview/apply/verify/commit，请求数严格为 1。
- Provider 失败、安全拒绝和 commit 失败均不重试模型请求。
- Web payload 返回两个空 commit 字段，Web 请求不能触发 Git 写命令。
- 测试禁止访问真实模型供应商。

## 完整验证

- `python -m pytest -q`。
- `python -m dev_agent.cli serve --port 0 --check`。
- 本地 HTTPServer 的真实 Provider commit 回环测试 `request_count == 1`。
- `git diff --check`。
- 新增和修改文本严格按 UTF-8 解码，中文直接保存。
- 扫描生产代码中的测试密钥、绝对临时路径和未脱敏 hook 输出。
- 确认变更范围不包含 push、merge、amend、Web Git 写入口、Responses API、重试或并发。

## 供应商保护

本阶段只在已有单次 Provider 响应对应的本地 apply/verify 流程后增加 Git 操作，不增加任何模型请求。真实 Provider 继续受现有 `CircuitBreaker` 的单请求、单失败和输出预算限制。

自动化测试仅使用 fake、CountingProvider 或 `127.0.0.1` 回环 HTTPServer。禁止真实供应商请求、批量模型探测、循环健康检查、压力测试、并发后台智能体和失败批量重试。

## 验收标准

- 只有显式 `--apply --verify --commit --commit-message` 才能进入提交流程。
- 提交前至少一条验证命令全部通过，并在验证后完成第二次确认。
- `--yes` 仅预授权确认，不绕过任何安全校验。
- 目标路径 apply 前必须干净；无关旧改动允许存在且始终保持原样。
- 运行期间任何目标外状态漂移、HEAD/分支变化或 Git 操作状态都会阻断提交。
- 提交只包含执行计划实际修改的目标路径，不包含无关 staged 内容，不创建空提交。
- commit/hook 失败只取消目标暂存，保留正文和无关状态。
- 成功提交的父提交、message、文件集合和 SHA 全部经过校验。
- CLI JSON 与历史准确记录结果，Web 只返回空 commit 字段。
- fake、plan-file 和真实 Provider 行为兼容，真实 Provider 请求数保持为 1。
- 不新增第三方依赖，不访问真实供应商，完整自动化测试通过。
