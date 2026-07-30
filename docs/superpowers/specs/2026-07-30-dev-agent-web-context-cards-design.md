# 研发助手型智能体：Web 上下文可读面板 v1 设计

## 背景

当前 Web 控制台的“上下文”区域仅把 `/api/context` 返回值渲染为 raw JSON。数据完整，但用户需要在嵌套字段中寻找项目技术栈、仓库扫描结果、Git 状态和验证命令，难以快速判断“当前项目是什么、仓库是否有改动、下一步应运行哪些检查”。

本阶段在不改变后端接口和数据结构的前提下，把上下文数据渲染为分层可读卡片。项目与 Git 状态是首要信息，验证命令是次要信息，并提供一键复制。原始 JSON 继续保留，用于调试和核对。

## 已选方案

用户已选择 **分层上下文卡片**：

1. 顶部展示项目和 Git 状态总览。
2. 下方展示技术栈、仓库扫描信息和验证命令。
3. 验证命令支持一键复制，但不会被页面执行。
4. 偏好和规则作为低优先级补充信息。
5. raw JSON 保留在可读卡片之后。

该方案比单一摘要条更易扫读，也比完整上下文工作台更符合 v1 范围。它复用现有静态页面模式，不引入前端框架、构建工具或后端聚合逻辑。

## 目标

- 优先展示项目名称、技术栈、识别语言和项目标记。
- 明确展示 Git 工作区状态、变更统计和最近提交。
- 展示验证命令，并支持键盘可操作的一键复制。
- 展示语言偏好、审批模式和规则内容等补充上下文。
- 字段缺失、类型异常或内容为空时仍可正常渲染。
- 所有动态数据通过 `textContent` 写入 DOM。
- 保留 `/api/context` 的原始 JSON。
- 桌面端和移动端都不产生页面级横向滚动。

## 非目标

- 不修改 `/api/context` 路由、payload 或上下文扫描逻辑。
- 不在浏览器中执行测试、检查、构建或其他命令。
- 不新增终端、任务队列、筛选、搜索或编辑能力。
- 不新增 Git 操作能力。
- 不引入前端框架、构建工具或外部依赖。
- 不调用真实模型供应商，不探测或压测 provider。

## 数据来源

接口保持不变：

```text
GET /api/context
```

当前 payload 包含：

```json
{
  "project": {
    "name": "项目名称",
    "tech_stack": []
  },
  "preferences": {
    "language": "zh-CN",
    "approval_mode": "confirm"
  },
  "rules_text": "项目规则",
  "scan": {
    "root": "仓库路径",
    "languages": [],
    "markers": [],
    "suggested_commands": {
      "test": "",
      "lint": "",
      "typecheck": "",
      "build": ""
    }
  },
  "git": {
    "status": "",
    "diff_stat": "",
    "recent_log": ""
  },
  "verification_steps": [
    {
      "name": "test",
      "command": ["python", "-m", "pytest"]
    }
  ]
}
```

前端只消费这些现有字段，不新增兼容层或第二份数据源。

## UI 结构

上下文 panel 从单一 raw JSON 升级为：

```text
上下文
项目总览卡
Git 状态卡
仓库扫描与补充信息卡
验证命令卡
原始 JSON
```

在 `<pre id="context">` 前新增：

```html
<div id="context-cards" class="context-card-list" aria-live="polite"></div>
<h3 class="result-heading">原始 JSON</h3>
```

卡片保持现有浅色纸张、苔藓绿和陶土色视觉系统。桌面端可使用双列信息区，移动端降为单列。卡片、路径、Git 输出和命令统一使用 `overflow-wrap: anywhere`。

## 信息层级

### 项目总览

- 项目名是卡片主标题，缺失时显示“未命名项目”。
- 技术栈、识别语言和项目标记使用可换行的文本标签展示。
- 扫描根目录作为辅助信息展示，长路径允许换行。
- 空集合显示“未检测到”，不隐藏字段标题。

### Git 状态

- `git.status` 为空字符串时显示“工作区干净”。
- `git.status` 为非空字符串时显示“工作区有变更”，并安全展示原始状态文本。
- `git.status` 缺失或类型不正确时显示“暂无 Git 状态”。
- `git.diff_stat` 和 `git.recent_log` 分区展示；空值显示“暂无变更统计”或“暂无提交记录”。
- 状态必须同时使用文字和颜色，不能只用颜色表达。
- 不解析特定语言或特定 Git 版本的状态文案，避免脆弱判断。

### 验证命令

- 优先展示 `verification_steps` 中名称和命令均有效的条目。
- `verification_steps[].command` 兼容参数数组和字符串；参数数组按 PowerShell 规则转换为可复制文本。安全 token 原样保留，其他 token 使用单引号并将内部单引号加倍；可执行文件需要引用时添加调用运算符 `&`。
- `verification_steps[].name` 中的 `test`、`lint`、`typecheck` 和 `build` 分别显示为“测试”“代码检查”“类型检查”和“构建”；其他名称安全显示原文。
- `verification_steps` 为空时，回退展示 `scan.suggested_commands` 中非空的 `test`、`lint`、`typecheck` 和 `build`。
- 回退命令使用“测试”“代码检查”“类型检查”“构建”作为标签。
- 同一命令只展示一次，保持原始顺序。
- 没有可用命令时显示“暂无验证命令”。
- 每条命令都有“一键复制”按钮，但不提供执行按钮。

### 补充信息

- 展示 `preferences.language` 和 `preferences.approval_mode`，缺失时显示“未设置”。
- 规则文本放在原生 `<details>` 中，默认折叠；为空时显示“暂无项目规则”。
- 完整规则仍可在原始 JSON 中核对，不生成模型摘要。

## 前端架构与数据流

`src/dev_agent/web/static/index.html`：

- 在现有 `context` raw JSON 前增加 `context-cards` 容器。
- 增加“原始 JSON”小标题。

`src/dev_agent/web/static/app.js`：

- 新增 `contextCards()` DOM getter。
- 新增 `clearContextCards()`。
- 新增 `renderContextCards(payload)`，负责调度各区块渲染。
- 新增小型 DOM helper，分别渲染标签、空态、Git 文本和命令行。
- 新增命令归一化 helper，兼容字符串和参数数组，并按既定优先级选择、格式化及去重验证命令。
- 修改 `loadContext()`：只请求一次 payload，先调用 `renderContextCards(payload)`，再调用 `renderJson("context", payload)`。

`src/dev_agent/web/static/styles.css`：

- 新增上下文卡片、状态标签、标签组、Git 文本和命令行样式。
- 复用现有 CSS 变量、间距、圆角、边框和响应式断点。
- 不引入新的字体、图标库或动画依赖。

每个 helper 只承担一种展示职责。渲染器只读取 payload，不修改 payload，也不依赖 raw JSON DOM 的内容。

## 复制交互

- 复制按钮使用 `navigator.clipboard.writeText(command)`。
- 成功后按钮短暂显示“已复制”，随后恢复“一键复制”。
- 失败时按钮显示“复制失败”，随后恢复，页面其余内容保持可用。
- 按钮使用原生 `<button type="button">`，支持键盘操作和焦点样式。
- 反馈文案通过按钮文本及每条命令独立的 `role="status"`、`aria-live="polite"` 状态节点传达。
- 复制逻辑只处理当前按钮关联的命令，不执行命令，也不发起额外网络请求。

## 错误处理与兼容性

- `project`、`preferences`、`scan` 或 `git` 缺失时按空对象处理。
- 数组字段缺失或类型不正确时按空数组处理。
- 文本字段缺失或类型不正确时使用对应占位文案。
- 所有仓库名、路径、规则、Git 输出和命令都通过 `textContent` 渲染。
- 单个区块缺少数据不阻止其他区块渲染。
- raw JSON 始终使用现有 `renderJson` 逻辑展示。
- `/api/context` 请求失败时沿用现有页面请求错误处理，不扩大为全局通知系统。

## 可访问性与响应式

- `context-cards` 使用 `aria-live="polite"`。
- Git 状态同时包含文字和颜色。
- 复制控件使用语义化按钮，并保留清晰的键盘焦点。
- 规则详情使用原生 `<details>` 和 `<summary>`。
- 长路径、命令和 Git 输出允许换行。
- 窄屏下所有卡片和命令行改为单列，按钮不遮挡命令文本。
- 不新增强制动画，并继续尊重现有 `prefers-reduced-motion` 设置。

## 测试策略

先扩展 `tests/test_web_server.py`，再编写实现：

- 断言 HTML 包含 `context-cards` 和上下文“原始 JSON”标题。
- 断言 JS 包含 `renderContextCards`、上下文清理逻辑和剪贴板调用。
- 断言 CSS 包含主要上下文卡片、Git 状态和命令行选择器。
- 继续断言动态内容使用 `textContent`。
- 验证 `/api/context` 仍返回项目、偏好、规则、扫描、Git 和验证步骤字段。
- 使用 Node 内建测试实际执行命令格式化、无效名称回退、命令去重、恶意文本 DOM 渲染以及剪贴板成功和失败分支；pytest 负责调用该测试，Node 不可用时明确跳过。
- 覆盖空字段或缺失字段不会破坏 payload 契约的后端行为，并通过本地浏览器验收 375px 布局。

人工验收：

- 完整 payload 能按层级展示项目、Git、扫描信息和验证命令。
- 空字段显示明确占位文案。
- Git 干净、有变更和无信息状态均有文字说明。
- 验证命令复制成功或失败时都有反馈，且不会被执行。
- 中文项目名、规则和命令正常显示，无乱码。
- 长路径和长命令在窄屏下不产生页面级横向滚动。
- raw JSON 继续显示完整 payload。

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

本阶段只修改本地 Web 静态展示和本地测试。不会调用真实模型供应商，不会批量探测 provider，不会循环健康检查，不会启动并发后台智能体，不会压力测试或批量重试外部请求。

## 验收标准

- 上下文区域先显示分层可读卡片，再显示原始 JSON。
- 项目与 Git 状态是最高视觉优先级。
- 技术栈、语言、项目标记和扫描根目录可读。
- 验证命令支持一键复制，并有成功或失败反馈。
- 页面永不执行展示的命令。
- 字段缺失或为空时显示占位信息，其他卡片仍正常渲染。
- 所有动态内容使用 `textContent`。
- 移动端布局不横向溢出。
- Web 专项测试、完整测试套件和 `serve --check` 通过。
