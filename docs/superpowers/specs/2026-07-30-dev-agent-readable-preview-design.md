# 研发助手型智能体：人类可读预览 v1 设计

## 背景

当前执行预览已经能在 CLI 和 Web 中返回结构化 `preview_changes`，包括动作、路径、目标是否存在、内容字节数和风险等级。这个信息足够机器判断，但对人工审批仍不够直观：用户只能看到“将写入某个文件”和“写入多少字节”，无法快速判断内容是否符合预期。

本阶段目标是在保持安全边界不变的前提下，为每个预览变更增加有限文本片段，让用户在确认执行前能看到将写入或追加的关键内容。

## 目标

- 在 execution preview 层统一生成人类可读的内容片段。
- CLI `--preview`、Web `/api/provider-plan/preview` 和 Web 审批 UI 能通过现有 JSON 预览结果自动获得该片段。
- 预览仍然无副作用：不写文件、不创建 `.agent` 任务历史、不触发真实模型请求。
- v1 只展示新内容片段，不实现完整 unified diff。
- 对长内容进行确定性截断，并在 payload 中显式标记。

## 非目标

- 不读取已有文件内容来生成 before/after diff。
- 不支持删除、重命名、二进制文件或非文本操作。
- 不在本阶段重做 Web 视觉展示组件；Web 可以继续先展示 JSON payload。
- 不改变 apply 的确认闸门和风险判断规则。

## 推荐方案

在 `ExecutionPreviewChange` 中新增内容预览字段，由 `ExecutionPlanApplier._preview_changes()` 在生成 preview 时统一填充。

新增字段：

```text
content_preview: str
content_preview_truncated: bool
content_preview_line_count: int
content_preview_char_count: int
```

字段含义：

- `content_preview`：将要写入、覆盖或追加的新内容片段。
- `content_preview_truncated`：当原始内容超过限制并被截断时为 `true`。
- `content_preview_line_count`：原始内容的行数统计。
- `content_preview_char_count`：原始内容的字符数统计。

默认限制：

- 最多展示前 6 行。
- 最多展示前 600 个字符。
- 任一限制触发时都截断，并设置 `content_preview_truncated: true`。
- 截断结果不额外拼接省略号，避免省略号被误认为真实写入内容；调用方通过布尔字段展示“已截断”提示。

## 操作语义

`create_text`：

- `content_preview` 展示将创建的新文件内容片段。
- `risk` 仍为 `create`。
- 如果目标已存在，仍按现有逻辑拒绝 preview。

`overwrite_text`：

- `content_preview` 展示将覆盖写入的新内容片段。
- 不读取旧文件内容，也不生成 before/after diff。
- `risk` 仍为 `overwrite`。

`append_text`：

- `content_preview` 展示将追加的内容片段。
- 目标存在时 `risk` 为 `append`。
- 目标不存在时 `risk` 为 `append_create`。

## 架构与数据流

1. CLI 或 Web 解析 `ExecutionPlan`。
2. 调用 `ExecutionPlanApplier.preview(plan)`。
3. `_validate_operations()` 先完成现有安全校验。
4. `_preview_changes()` 为每个 `ExecutionOperation` 创建 `ExecutionPreviewChange`。
5. 新增 helper 根据 `operation.content` 生成有限 `content_preview` 和统计字段。
6. `ExecutionResult.preview_changes_as_dicts()` 继续调用 `to_dict()` 输出完整字段。
7. CLI/Web 不需要手写额外转换逻辑即可透传新字段。

## 组件边界

`src/dev_agent/execution/models.py`：

- 扩展 `ExecutionPreviewChange` dataclass。
- 继续使用 `to_dict()` 输出稳定 JSON 兼容结构。

`src/dev_agent/execution/applier.py`：

- 新增小型纯函数或私有 helper 生成内容预览。
- helper 只依赖字符串内容和固定限制，便于单元测试。

`src/dev_agent/cli.py`：

- 预期无需新增格式化逻辑。
- 现有 preview JSON 输出应自动包含新增字段。

`src/dev_agent/web/api.py` 与 `src/dev_agent/web/server.py`：

- 预期无需新增业务逻辑。
- `preview_changes` 与 apply 前重新 preview 结果应自动包含新增字段。

`src/dev_agent/web/static/*`：

- v1 不要求改 UI 结构。
- 若现有页面直接渲染 JSON，新字段会自然可见。

## 错误处理

- 预览截断 helper 不抛出业务异常。
- 空内容合法，`content_preview` 为空字符串；`content_preview_line_count` 按 `content.splitlines()` 统计，因此空字符串为 `0`。
- 安全校验失败仍使用现有 `ExecutionPlanError` 路径。
- 不因为内容过长拒绝 preview，只截断展示。

## 测试策略

单元测试：

- `ExecutionPlanApplier.preview()` 返回的每个 `preview_changes` 项包含新增字段。
- 短内容不截断，`content_preview_truncated` 为 `false`。
- 超过 6 行的内容按行截断，`content_preview_truncated` 为 `true`。
- 超过 600 字符的单行内容按字符截断，`content_preview_truncated` 为 `true`。
- 中文内容直接保留，不使用 Unicode 转义形式。

CLI 测试：

- `run --preview` 的 JSON payload 包含 `content_preview`。
- provider plan preview 模式同样包含 `content_preview`。
- preview 仍不写文件、不创建 `.agent` 副作用。

Web API 测试：

- `/api/provider-plan/preview` 返回的 `preview_changes` 包含内容片段字段。
- `/api/provider-plan/apply` 返回的 apply 前重新生成 `preview_changes` 包含内容片段字段，同时不破坏现有 `applied_changes` 行为。
- malformed JSON、危险路径和 create 冲突仍按现有测试失败路径处理。

验证命令：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

## 安全与熔断保护

本阶段只修改本地预览数据结构和本地 fake/provider plan 流程测试，不会调用真实模型供应商，不会批量探测 provider，不会启动并发智能体，也不会进行压力测试或批量重试。

## 兼容性

这是向后兼容的 payload 扩展：现有消费者仍可读取旧字段；新消费者可以使用 `content_preview` 和截断标记增强展示。由于 `ExecutionPreviewChange.to_dict()` 当前通过 dataclass 序列化，新增字段会自然进入 CLI/Web JSON 输出。

## 验收标准

- 用户在 CLI/Web preview JSON 中能看到每个变更的有限文本片段。
- 长内容被稳定截断，并有明确布尔标记。
- 预览无副作用性质保持不变。
- 所有现有测试继续通过。
- 新增测试覆盖短内容、按行截断、按字符截断、CLI 透传和 Web API 透传。
