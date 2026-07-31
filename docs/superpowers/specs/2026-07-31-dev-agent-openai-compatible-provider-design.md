# OpenAI-Compatible Provider 设计规格

## 背景

研发助手已经具备 Provider 协议、FakeProvider、请求预算与熔断保护、严格 JSON 执行计划解析、零副作用预览、可读 Diff、指纹审批和确认后执行能力。目前 CLI 仍只能消费人工传入的 fake 响应，尚不能通过用户配置调用真实模型。

本阶段增加单通道、单请求、同步的 OpenAI-compatible Provider，让 CLI 能自动完成“请求模型 -> 解析严格计划 -> 生成 Diff 预览 -> 确认后执行”。实现继续以安全边界为主，不探测模型、不重试、不并发、不自动切换供应商，也不开放 Web 真实模型请求。

## 目标

- 支持兼容性广的 `/v1/chat/completions` 协议。
- 只有显式选择 `--provider openai-compatible` 时才能联网。
- API Key 只从环境变量读取，绝不写入仓库或 YAML。
- 每次 CLI 运行最多发出一个模型请求。
- 模型必须返回严格 JSON 执行计划，不能返回自由文本补丁。
- 默认只生成安全预览；实际写文件继续要求 `--apply` 和现有确认流程。
- 确认执行时复用已经取得的响应和执行计划，不能再次请求模型。
- 保持现有 FakeProvider、计划文件、Web 控制台和执行审批行为兼容。

## 非目标

- OpenAI Responses API。
- 流式输出、多轮会话、内置工具调用和服务端会话状态。
- 多供应商 Profile、自动路由、自动故障转移或负载均衡。
- 模型列表探测、健康检查、压力测试、后台轮询或批量调用。
- 自动重试 429、5xx、超时或网络错误。
- Web 控制台发起真实模型请求。
- 自动读取或上传源码正文、完整仓库 Diff、任意目录内容。
- 自动 Git commit、push 或 merge。
- 保存 API Key、Authorization 请求头或完整认证错误信息。

## 用户流程

### 只生成预览

```powershell
dev-agent run "创建说明文件" --provider openai-compatible
```

CLI 加载用户配置和环境变量，发送一次请求，解析严格 JSON 计划，执行本地安全校验并输出 `preview_changes`、`file_diffs` 与 `preview_fingerprint`。此流程不写计划目标文件，也不创建 `.agent` 任务历史。

### 交互确认后执行

```powershell
dev-agent run "创建说明文件" --provider openai-compatible --apply
```

CLI 先完成同一份预览，再提示用户输入现有确认词。确认后复用已取得的模型响应、解析后的计划和预览指纹执行，不发出第二个模型请求。

### 明确授权的脚本化执行

```powershell
dev-agent run "创建说明文件" --provider openai-compatible --apply --yes
```

`--yes` 只跳过交互输入，不跳过配置校验、计划解析、路径校验、Diff 预览、指纹检查或执行安全规则。

## 配置设计

用户级配置固定为 `~/.dev-agent/provider.yaml`：

```yaml
openai_compatible:
  base_url: https://example.com/v1
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
  timeout_seconds: 60
```

### 配置字段

- `base_url`：必填，表示 API 根路径。Provider 去除末尾 `/` 后追加 `/chat/completions`。
- `model`：必填，原样放入请求体。
- `api_key_env`：必填，表示保存密钥的环境变量名称，不是密钥值。
- `timeout_seconds`：可选，默认 60，允许范围为 1 至 300 秒。

### 配置安全

- 配置文件不得接受 `api_key`、`token` 或其他明文密钥字段；出现这些字段时直接报错。
- `api_key_env` 对应的环境变量不存在或为空时，在联网前失败。
- `base_url` 默认必须使用 HTTPS。
- 为本地测试和本地转发服务保留 HTTP 例外，但主机只能是 `localhost`、`127.0.0.1` 或 `::1`。
- URL 不得包含用户名、密码、查询参数或片段。
- 配置对象的 `repr`、异常、CLI JSON、任务历史和日志均不得包含密钥。
- Provider 在内存中读取密钥并仅用于 `Authorization: Bearer <key>` 请求头。

## 模块边界

### `config/provider.py`

新增不可变 `OpenAICompatibleConfig` 和 `load_openai_compatible_config(home_dir)`。配置对象只包含 `base_url`、`model`、`api_key_env` 和 `timeout_seconds`，不包含密钥。另由 `resolve_openai_compatible_api_key(config, environ)` 返回仅在 Provider 构造期间使用的密钥字符串：

- 读取严格 UTF-8 YAML。
- 校验字段类型、未知敏感字段、URL、模型、环境变量名和超时范围。
- 从传入的环境映射解析密钥，便于测试且避免直接耦合全局环境。
- 密钥解析函数不得把环境映射或密钥附加到配置对象。
- 对外配置模型不提供会泄露敏感信息的自定义序列化方法。

### `providers/openai_compatible.py`

新增 `OpenAICompatibleProvider`，实现现有 `ModelProvider` 协议：

- 使用 Python 标准库 `urllib.request` 同步 POST。
- 固定请求 `/chat/completions`。
- 请求体仅包含 `model` 和 `messages`，不发送供应商兼容性不一致的可选参数。
- 请求头只包含 JSON 内容类型、Bearer 认证和稳定 User-Agent。
- 设置配置中的单次超时。
- 完整响应体设置 256 KiB 上限，防止异常大响应占用内存。
- 从 `choices[0].message.content` 读取非空字符串。
- 返回现有 `ModelResponse`；usage 继续使用确定性的请求次数和输入/输出字符数，不依赖供应商 token 字段。
- 任何网络、HTTP、解码或响应结构错误统一转为中文 `ProviderError`。
- 不在 Provider 内实现重试。

### `runtime/provider_plan.py`

新增准备阶段，用于把一次模型请求转成可审批计划：

```text
ProviderPlanPreparation
  provider_name: str
  model: str
  response: ModelResponse
  execution_plan: ExecutionPlan
  preview_result: ExecutionResult
```

准备流程：

1. 解析现有 `RuntimeContext`。
2. 使用独立严格计划提示词构造 `ModelRequest`。
3. 通过 `ProtectedProvider` 和单请求预算调用 Provider 一次。
4. 用 `parse_provider_execution_plan()` 解析响应文本。
5. 用 `ExecutionPlanApplier.preview()` 生成无文件副作用 Diff 与指纹。
6. 返回包含 Provider 名称、模型、响应、计划和预览的不可变准备结果。

准备结果只存在于当前进程内，不持久化为审批 token。确认前文件变化仍由现有预览指纹阻止。

### `runtime/prompts.py`

保留现有普通规划提示词，新增严格执行计划提示词。系统约束必须要求：

- 输出只能是一个 JSON 对象，不能包含 Markdown fence 或解释文字。
- 顶层字段为 `summary` 和 `operations`。
- 每个操作仅允许 `create_text`、`overwrite_text` 或 `append_text`。
- 每个操作包含相对路径和 UTF-8 文本内容。
- 不得生成 Git 写操作、命令执行、绝对路径、仓库外路径或禁止目录。

execution 层仍是最终安全边界，不能信任模型自我约束。

### `runtime/runner.py`

`LocalTaskRunner` 增加复用已准备 Provider 响应的内部入口或等价参数。复用路径必须：

- 不调用 `provider.complete()`。
- 继续创建任务状态、执行已审批计划、运行显式验证并记录历史。
- 在历史中记录 Provider 名称、计划摘要和执行结果，但不记录密钥或请求头。
- 保持现有直接 Provider 调用路径兼容 FakeProvider 测试与 Web fake 流程。

实现应以“网络调用次数可直接断言”为设计约束，不能通过再次构造 Provider 隐式请求。

### `cli.py`

`run` 子命令新增：

```text
--provider {fake,openai-compatible}
```

默认值为 `fake`，保持当前无网络行为。CLI 参数规则：

- `fake` 模式保持现有 `--fake-response`、`--use-provider-plan` 和 `--plan-file` 行为。
- `openai-compatible` 模式禁止 `--fake-response`、`--use-provider-plan` 和 `--plan-file`，避免来源歧义和无意义联网。
- 只有 `openai-compatible` 模式加载 Provider 配置和密钥。
- 未传 `--apply` 时输出准备阶段预览并返回 0。
- 传入 `--apply` 时先预览再执行现有确认。
- 配置或 Provider 错误输出中文 stderr 并返回 2。
- 计划执行失败沿用现有执行错误语义。

## 请求契约

请求示意：

```json
{
  "model": "model-name",
  "messages": [
    {
      "role": "system",
      "content": "严格执行计划输出约束"
    },
    {
      "role": "user",
      "content": "现有运行时上下文"
    }
  ]
}
```

为提高第三方兼容性，首版不发送 `response_format`、`temperature`、`stream`、tools 或供应商私有字段。严格 JSON 由提示词和本地解析双重约束。

响应必须满足：

```json
{
  "choices": [
    {
      "message": {
        "content": "{\"summary\":\"...\",\"operations\":[]}"
      }
    }
  ]
}
```

其他响应形状、空文本、非 UTF-8、无效 JSON 或非法执行计划全部安全失败。

## 数据外发边界

真实 Provider 只复用现有 `RuntimeContext`，发送：

- 用户显式输入的研发请求。
- 项目名称、技术栈和语言/标记扫描摘要。
- `.agent/rules.md` 项目规则。
- Git 工作区状态和近期提交摘要。
- 与请求相关的历史任务或经验摘要。
- 建议验证命令。

首版不读取或发送源码文件正文、完整 Diff、未跟踪文件内容、环境变量集合或本机其他目录内容。显式 `--provider openai-compatible` 是本次单请求的数据外发授权；默认 fake 模式始终离线。

## 请求预算与熔断

- 准备流程使用 `BudgetConfig(max_requests=1, max_failures=1, max_output_chars=20_000)`。
- 单次成功或失败后都不会再次调用 Provider。
- 429、5xx、连接失败和超时只返回错误，不排队、不延迟重试、不切换模型。
- 供应商响应文本超过字符预算时按现有 `BudgetExceeded` 失败。
- HTTP 响应超过 256 KiB 时在解析前失败。
- CLI 进程结束后不持久化冷却状态；本阶段没有后台请求能力。

## 错误处理

### 联网前错误

- 配置文件缺失或不是映射。
- 必填字段缺失或类型错误。
- 明文敏感字段存在。
- URL 不安全。
- API Key 环境变量缺失。

这些错误不得发出 HTTP 请求。

### 联网错误

- DNS、连接、TLS 或超时错误。
- HTTP 401、403、408、429 或 5xx。
- 非 UTF-8、非 JSON、响应过大或缺失 `choices[0].message.content`。

错误消息可以包含 HTTP 状态和经过长度限制的非敏感原因，但必须对 API Key、Authorization 值和 URL 用户信息执行脱敏。不得把完整响应头或完整错误响应写入历史。

### 模型计划错误

- content 不是严格 JSON 对象。
- JSON 包含额外包裹文本或 Markdown fence。
- operation 动作、路径或字段不合法。
- 预览遇到非 UTF-8 目标、禁止路径或创建冲突。

这些错误均发生在写文件前。默认预览不创建 `.agent` 历史；确认执行后的失败沿用现有任务失败历史。

## CLI 输出

在现有预览和执行 JSON 中增加稳定的非敏感字段：

```json
{
  "provider": "openai-compatible",
  "model": "model-name",
  "provider_usage": {
    "request_count": 1,
    "input_chars": 1234,
    "output_chars": 456
  }
}
```

FakeProvider 输出也应提供同形字段或稳定空值，避免调用方按模式猜测 JSON 结构。任何输出都不包含 API Key、Authorization 或完整用户配置。

## 测试策略

### 配置测试

- 正确加载用户级严格 UTF-8 YAML 和环境变量密钥。
- 缺失文件、必填字段、环境变量和非法超时安全失败。
- 拒绝明文 `api_key`、`token` 等敏感字段。
- HTTPS、回环 HTTP 和禁止 URL 规则正确。
- 配置及异常字符串不泄露密钥。

### Provider 单元与协议测试

使用进程内本地 `HTTPServer`，不请求真实供应商：

- 只收到一个 POST，请求路径为 `/v1/chat/completions`。
- Authorization、Content-Type、model 和 messages 正确。
- 中文提示和响应保持 UTF-8。
- 正确解析 content 并返回字符 usage。
- 401、429、5xx、超时、连接失败、响应过大、非 UTF-8、畸形 JSON和缺失字段均转为 `ProviderError`。
- 所有失败场景请求次数最多为 1，且密钥不出现在异常中。

### 准备与运行时测试

- 单次响应生成严格计划、Diff 和指纹，不写文件。
- 非法模型输出不写文件、不创建历史。
- 确认执行复用准备响应，请求计数仍为 1。
- 文件在预览后变化时沿用指纹保护并拒绝执行。
- 执行成功、执行失败和验证结果继续正确写历史。
- FakeProvider 和现有 Web fake 流程不回归。

### CLI 测试

- 默认 fake 模式不联网且保持现有行为。
- 真实模式显式选择后只请求一次并输出预览。
- `--apply` 仍要求 TTY 确认或 `--yes`。
- 真实模式与 fake/计划文件参数冲突时在联网前返回 2。
- 配置、认证、HTTP、响应和计划错误返回中文 stderr，且不泄露密钥。
- JSON 输出包含稳定 Provider 元数据和现有 Diff 字段。

### 完整验证

- `python -m pytest -q`。
- `python -m dev_agent.cli serve --port 0 --check`。
- 使用本地 HTTPServer 进行一次端到端 CLI 预览和一次确认执行验收。
- 验证每个命令的服务端请求计数为 1。
- `git diff --check` 和范围审查。

## 供应商保护

本阶段的测试与验收全部使用本地 HTTPServer，不调用真实模型。产品代码只允许用户通过显式 CLI 参数发出单次请求；没有循环、重试、并发、探测、后台任务或自动通道切换。任何未来增加重试、多 Profile、Web 请求或 Responses API 的工作都必须重新设计并单独审批。

## 验收标准

- 没有显式 Provider 参数时，研发助手保持完全离线。
- API Key 只能来自环境变量，任何文件、输出、异常和历史都不泄露密钥。
- 真实模式对 `/v1/chat/completions` 最多请求一次。
- 模型输出必须经过严格 JSON 解析、执行校验和 Diff 预览。
- 默认预览无目标文件和历史副作用。
- `--apply` 确认后复用同一响应，执行期间不再次联网。
- 预览指纹过期、非 UTF-8、危险路径和计划冲突继续安全失败。
- FakeProvider、计划文件和 Web fake 审批流程保持兼容。
- 不新增第三方依赖，所有自动化测试通过。
