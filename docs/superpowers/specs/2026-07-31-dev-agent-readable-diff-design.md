# 研发助手完整可读 Diff 预览设计

日期：2026-07-31

## 背景

当前执行计划支持 `create_text`、`overwrite_text` 和 `append_text`，CLI 与 Web 在执行前可以展示目标路径、风险、内容片段和字节数，执行后可以展示变更摘要与 Git diff stat。现有信息能够说明“准备操作什么”，但不能准确展示文件执行前与全部计划执行后的逐行净变更。

本阶段增加完整语义、受限输出的 unified diff。用户在批准前能够逐文件复核净变更，执行后能够复用同一份计划 Diff 进行审计。实现保持零副作用预览，不接真实模型供应商，不读取整个仓库 Diff，也不混入计划外的未提交改动。

## 目标

- 按文件展示计划执行前与全部操作执行后的最终净变更。
- 同一文件的多个操作按计划顺序模拟，并合并为一份 Diff。
- CLI、Web 预览和 Web 执行审计共享同一数据结构。
- Web 使用“文件导航 + 单一 Diff 预览”布局。
- 通过预览指纹阻止文件状态变化后继续执行旧审批。
- 对大 Diff 设置明确上限，同时保留完整统计和截断标记。
- 非 UTF-8 文件、路径错误和操作冲突均在写入前安全失败。

## 非目标

- 不接入真实 Provider，不增加模型请求、重试、探测或并发智能体。
- 不增加第三方依赖。
- 不展示整个仓库的 Git Diff，也不包含计划外改动。
- 不实现一次性授权 token、跨浏览器审批状态或 token 过期机制。
- 不新增删除、重命名、二进制写入或补丁应用动作。
- 不改变现有执行计划 JSON 格式。
- 不增加 CLI ANSI 彩色输出或新的 CLI 参数。

## 已确认决策

- 使用 Python 标准库 `difflib` 在内存中生成 unified diff。
- 每个文件只展示最终净变更，不按操作重复展示。
- 每文件最多返回 200 行或 20,000 字符，任一上限先到即截断。
- 预览和执行结果都返回计划 Diff。
- 现有文件不是有效 UTF-8 时安全失败并禁止执行。
- Web 采用文件导航加单一 Diff 预览；桌面端左右排列，移动端上下排列。

## 架构

新增 `src/dev_agent/execution/diff.py`，将 Diff 计算与文件写入、CLI、Web API 和页面渲染分离。该模块只负责：

1. 接收已解析的 `ExecutionPlan` 和仓库根目录。
2. 复用执行层的路径与操作校验。
3. 读取计划涉及文件的初始 UTF-8 内容。
4. 按操作顺序在内存中模拟最终内容。
5. 为每个文件生成 unified diff、统计、截断结果和状态摘要。
6. 根据计划和完整文件状态生成稳定预览指纹。

Diff 计算器不得调用 Git、创建临时文件或写入目标文件。`ExecutionPlanApplier.preview()` 调用计算器并把结果放入 `ExecutionResult`。`ExecutionPlanApplier.apply()` 在写入前重新计算并校验预期指纹，校验成功后才执行现有写入流程。

路径解析与操作校验仍以 `ExecutionPlanApplier` 的现有规则为唯一安全来源。为避免 Diff 模块复制私有安全逻辑，实施时应将可复用的路径解析和计划校验提取为执行层内部协作接口，而不是在两个模块维护不同规则。

## 数据模型

新增不可变数据模型 `ExecutionFileDiff`：

```python
@dataclass(frozen=True)
class ExecutionFileDiff:
    path: str
    status: str
    diff_text: str
    additions: int
    deletions: int
    diff_line_count: int
    diff_char_count: int
    displayed_line_count: int
    displayed_char_count: int
    truncated: bool
    before_line_ending: str
    after_line_ending: str
```

字段语义：

- `path`：仓库相对路径，保持执行计划中首次出现的顺序。
- `status`：`added`、`modified` 或 `unchanged`。
- `diff_text`：用于 CLI 和 Web 展示的 unified diff；可能被截断。
- `additions`、`deletions`：完整 Diff 中的正文增删行数，不统计文件头和 hunk 头。
- `diff_line_count`、`diff_char_count`：截断前完整 Diff 的总行数和总字符数。
- `displayed_line_count`、`displayed_char_count`：实际返回的展示内容大小。
- `truncated`：是否因为任一上限而截断。
- `before_line_ending`、`after_line_ending`：`lf`、`crlf`、`mixed` 或 `none`，用于显式提示换行差异。

`ExecutionResult` 增加：

```python
file_diffs: list[ExecutionFileDiff]
preview_fingerprint: str
```

预览与执行 payload 均使用字段名 `file_diffs` 和 `preview_fingerprint`。无执行计划的普通 dry-run 保持 `file_diffs: []`、`preview_fingerprint: ""`，让响应结构稳定。

## 内存模拟规则

计划先整体校验，再读取或模拟任何内容。每个目标路径记录：初始是否存在、初始文本、当前模拟文本和操作序列。

- `create_text`：目标必须不存在，模拟内容设为操作内容。
- `overwrite_text`：无论目标是否存在，模拟内容替换为操作内容。
- `append_text`：在当前模拟内容后追加操作内容；目标不存在时从空文本开始。
- 同一路径后续操作读取前一步的模拟结果，不重新读取磁盘。
- 文件初始存在但不是普通文件，沿用现有执行校验并失败。
- 初始文件读取严格使用 UTF-8；解码失败转为中文 `ExecutionPlanError`，不使用替换字符。

状态由初始和最终结果决定：初始不存在且最终存在为 `added`；初始存在且内容变化为 `modified`；初始存在且最终内容相同为 `unchanged`。`unchanged` 仍返回文件记录，Diff 文本为空，便于用户理解计划包含该文件但没有净变更。

## Unified Diff 规则

- 新文件使用 `/dev/null` 作为旧文件标签，`b/<path>` 作为新文件标签。
- 已有文件使用 `a/<path>` 和 `b/<path>`。
- hunk 使用 `difflib.unified_diff` 的默认三行上下文。
- 内容比较保留原始文本语义；展示统一使用 LF 分隔，避免 API 中混合换行破坏 JSON 和页面布局。
- 末尾无换行时增加 `\ No newline at end of file` 提示。
- 仅换行风格变化也必须通过 `before_line_ending` 和 `after_line_ending` 明确呈现，不能被当作无变化隐藏。
- 动态路径和内容不进入 HTML 字符串，前端只通过 `textContent` 渲染。

增删统计基于完整 Diff 计算。以 `+++`、`---` 开头的文件头和以 `@@` 开头的 hunk 头不计入增删行。

## 截断规则

先生成完整 Diff 和完整统计，再生成展示内容：

1. 先保留最多 200 行。
2. 再把结果限制到最多 20,000 字符。
3. 任一步减少内容时设置 `truncated=true`。
4. `diff_text` 不内嵌截断提示，避免提示文字被误认为 Diff 正文。
5. Web 在 Diff 面板顶部独立展示“已显示 X/Y 行，内容已截断”。
6. CLI 使用结构化统计表达截断，不额外输出非 JSON 文本。

超长单行允许在 20,000 字符处截断，以保证硬上限。所有显示数量按实际返回字符串计算。

## 预览指纹与过期保护

`preview_fingerprint` 使用 SHA-256，格式为 `sha256:<hex>`。哈希输入为确定性 UTF-8 JSON，包含：

- 执行计划摘要和完整操作序列。
- 每个目标文件的规范化仓库相对路径。
- 初始存在状态。
- 初始完整内容的 SHA-256。
- 最终模拟内容的 SHA-256。

记录顺序采用执行计划中路径首次出现的顺序，JSON 使用固定字段顺序、紧凑分隔符和 `ensure_ascii=False`。指纹基于未截断的状态，因此不可见区域发生变化也会使指纹失效。

Web 预览响应返回指纹。确认执行请求必须回传 `preview_fingerprint`；后端重新校验计划、读取当前文件并计算指纹：

- 指纹一致：继续执行，并在结果中返回同一指纹和同一份计划 Diff。
- 指纹不同：抛出专用过期错误，HTTP 返回 `409 Conflict`，不写入文件。
- 指纹缺失或格式无效：返回 `400 Bad Request`，不写入文件。

指纹仅证明当前文件状态与已预览状态一致，不承担身份认证或一次性授权功能。

CLI 在交互确认前保存预览指纹。用户确认后，执行层在写入前重新计算；如果等待期间文件发生变化，CLI 返回非零退出码和中文错误，不写入文件。`--yes` 也不能绕过该检查。

## CLI 与 API

CLI 继续输出单个机器可读 JSON 文档。现有预览和执行响应增加：

```json
{
  "file_diffs": [
    {
      "path": "src/example.py",
      "status": "modified",
      "diff_text": "--- a/src/example.py\n+++ b/src/example.py\n...",
      "additions": 3,
      "deletions": 1,
      "diff_line_count": 12,
      "diff_char_count": 286,
      "displayed_line_count": 12,
      "displayed_char_count": 286,
      "truncated": false,
      "before_line_ending": "crlf",
      "after_line_ending": "lf"
    }
  ],
  "preview_fingerprint": "sha256:..."
}
```

`POST /api/provider-plan/preview` 返回相同字段。`POST /api/provider-plan/apply` 请求增加：

```json
{
  "request": "任务说明",
  "fake_response": "严格 JSON provider plan",
  "preview_fingerprint": "sha256:..."
}
```

apply 响应返回重新校验后的 `file_diffs` 和 `preview_fingerprint`。现有 `planned_changes`、`preview_changes`、`applied_changes`、`diff_stat` 和原始 JSON 均继续保留，避免破坏已有消费者。

## Web 交互

采用“文件导航 + 单一 Diff 预览”布局。

### 桌面端

- 左侧为文件导航，右侧为当前文件 Diff。
- 文件项显示路径、状态、增删行统计和截断标记。
- 默认选中第一个 `added` 或 `modified` 文件；全部无净变更时选中第一项。
- 当前文件 Diff 顶部显示路径、状态、换行风格变化和完整/显示统计。
- 截断警告固定放在 Diff 正文上方。

### 移动端

- 375px 宽度下改为上下布局。
- 文件导航变为 Diff 上方可横向滚动的文件按钮，不产生页面级横向溢出。
- 文件按钮保持至少 44px 触控高度。
- Diff 正文自身允许横向滚动，以保留代码缩进和行内容。

### 可访问性与状态

- 文件导航使用按钮语义和 `aria-selected`，支持键盘聚焦与切换。
- Diff 正文使用 `<pre>`，动态内容全部通过 `textContent` 写入。
- 预览成功后启用确认按钮。
- 表单输入变化沿用现有逻辑，使旧预览失效。
- apply 返回 `409` 时清空可执行状态、禁用确认按钮，并显示“文件状态已变化，请重新预览”。
- 执行成功后，审计区域复用文件导航和 Diff 组件展示实际批准的计划 Diff。
- 原始 JSON 继续保留在可读视图之后。

## 错误处理

- 非 UTF-8 文件：返回中文预览错误，不产生部分 Diff，不写文件。
- 非法路径、禁止目录、目录目标或父路径冲突：沿用现有 `ExecutionPlanError` 语义。
- 不支持的动作或无效计划：解析或校验阶段失败。
- 指纹缺失或格式无效：Web 返回 400；CLI 内部状态异常返回非零退出码。
- 指纹过期：Web 返回 409；CLI 返回非零退出码。
- Diff 计算异常：不降级为允许执行；预览失败即禁止写入。
- 页面收到缺失或畸形 `file_diffs` 时显示空状态，不通过 `innerHTML` 拼接回退内容。

## 测试策略

本阶段采用 TDD。

### Python 单元测试

- `create_text` 生成 `/dev/null` 到新文件的 Diff。
- `overwrite_text` 与 `append_text` 生成已有文件净变更。
- 对同一路径连续覆盖、追加时只产生一条最终文件 Diff。
- 追加到不存在文件时状态为 `added`。
- 最终内容与初始内容相同时状态为 `unchanged`，Diff 为空。
- 中文 UTF-8 内容直接出现在 Diff 中，不使用 `\uXXXX`。
- CRLF、LF、混合换行和末尾无换行有明确结果。
- 非 UTF-8 文件在预览和 apply 前失败，文件字节不变。
- 200 行和 20,000 字符边界分别覆盖刚好等于、超过一单位和超长单行。
- 完整统计在截断后仍正确。
- 文件顺序按路径首次出现顺序稳定。
- 相同计划和文件状态生成相同指纹；计划或文件任一变化都会改变指纹。
- apply 指纹过期时不写任何文件。

### CLI 与 Web API 测试

- 预览和执行 payload 包含一致的 `file_diffs` 与指纹。
- 普通 dry-run 返回稳定的空字段。
- Web apply 缺失指纹返回 400。
- 文件变化后的 Web apply 返回 409，目标内容不变。
- 指纹一致时执行成功并返回审计 Diff。

### JavaScript 行为测试

- 文件导航默认选择与切换正确。
- 路径、Diff、错误文本和恶意内容仅通过 `textContent` 呈现。
- 增删统计、换行风格和截断提示正确显示。
- 空 Diff 和缺失字段有可读空状态。
- 409 响应禁用确认按钮并要求重新预览。
- 执行审计复用同一导航组件且不影响原始 JSON。

### 集成验收

- 全量 `python -m pytest`。
- Node 行为测试与 `node --check`。
- `python -m dev_agent.cli serve --port 0 --check`。
- `git diff --check`。
- 本地浏览器验证桌面布局与 375px 布局、键盘切换、44px 触控目标、Diff 内部横向滚动和页面无横向溢出。

## 供应商保护

本阶段只修改本地执行预览、CLI/Web payload 和静态页面，不调用真实模型供应商，不批量探测 Provider，不循环健康检查，不启动并发后台智能体，不做压力测试，也不批量重试失败请求。

## 验收标准

- 用户能在 CLI JSON 和 Web 审批页看到每个计划文件的最终净 Diff。
- 同一文件多个操作不会产生相互割裂或重复的审批块。
- 仓库已有未提交改动不会混入计划 Diff。
- 大 Diff 明确截断且完整统计仍可核对。
- 文件在预览后变化时，旧审批无法执行。
- 非 UTF-8 和所有预览错误均安全失败且无文件副作用。
- Web 桌面端和移动端均可高效切换文件并阅读 Diff。
- 所有现有测试与新增测试通过，且不增加第三方依赖。
