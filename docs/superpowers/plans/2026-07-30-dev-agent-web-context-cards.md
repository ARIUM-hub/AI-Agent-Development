# Web 上下文可读面板 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Web 上下文区域渲染项目与 Git 状态优先的分层卡片，并提供只复制、不执行的验证命令交互。

**Architecture:** 复用现有 `/api/context` payload，不新增后端路由或 schema。前端 `loadContext()` 只请求一次数据，随后分别渲染 context cards 和 raw JSON；独立 helper 负责安全归一化字段、格式化验证命令、创建 DOM 与剪贴板反馈。

**Tech Stack:** Python stdlib HTTP server、pytest、原生 HTML/CSS/JavaScript，无前端构建工具，无真实模型 provider 请求。

---

## File Structure

- Modify: `tests/test_web_server.py`
  - 扩展 `/api/context` 契约测试，保护项目、偏好、规则、扫描、Git 和验证步骤字段。
  - 扩展静态资源测试，保护 context cards 容器、渲染 helper、剪贴板反馈、CSS class 和 raw JSON 顺序。
- Create: `tests/web_context_cards.test.mjs`
  - 使用 Node 内建测试直接执行上下文命令格式化、字段回退、去重、安全 DOM 渲染及剪贴板双分支。
- Modify: `src/dev_agent/web/static/index.html`
  - 在 `<pre id="context">` 前新增 `context-cards` 容器和“原始 JSON”标题。
- Modify: `src/dev_agent/web/static/app.js`
  - 新增上下文值归一化、命令格式化和去重、分区 DOM 渲染、一键复制反馈。
  - 修改 `loadContext()`，先渲染可读卡片，再渲染 raw JSON。
- Modify: `src/dev_agent/web/static/styles.css`
  - 新增项目、Git、标签、验证命令、补充信息和移动端样式。
  - 复用现有纸张、苔藓和陶土色系统。

## Safety Scope

- 不调用真实模型供应商。
- 不批量探测 provider，不做循环健康检查、压力测试或批量重试。
- 不启动并发后台智能体。
- 不执行页面展示的命令，不新增执行按钮。
- 不新增后端接口、payload 字段或持久化结构。
- 所有动态文本通过 `textContent` 渲染。
- 所有文本读写保持 UTF-8；中文直接写中文，不使用 `\uXXXX` 转义。

---

### Task 1: Protect the Context Payload Contract

**Files:**
- Modify: `tests/test_web_server.py`
- Test: `tests/test_web_server.py::test_context_route_returns_project_context`

- [ ] **Step 1: Expand the context fixture and assertions**

Replace `test_context_route_returns_project_context()` with:

```python
def test_context_route_returns_project_context(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    write_text_utf8(
        tmp_path / ".agent" / "project.yaml",
        "name: 示例项目\ntech_stack:\n  - python\n  - pytest\n",
    )
    write_text_utf8(
        tmp_path / ".agent" / "commands.yaml",
        "test: python -m pytest -v\nlint: python -m ruff check .\n",
    )
    write_text_utf8(tmp_path / ".agent" / "rules.md", "所有文本使用 UTF-8。\n")
    write_text_utf8(
        tmp_path / ".dev-agent" / "preferences.yaml",
        "language: zh-CN\napproval_mode: confirm\n",
    )
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/context")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["project"] == {
        "name": "示例项目",
        "tech_stack": ["python", "pytest"],
    }
    assert payload["preferences"] == {
        "language": "zh-CN",
        "approval_mode": "confirm",
    }
    assert payload["rules_text"] == "所有文本使用 UTF-8。\n"
    assert payload["scan"]["root"] == str(tmp_path.resolve())
    assert payload["scan"]["languages"] == ["python"]
    assert payload["scan"]["markers"] == ["pyproject.toml"]
    assert payload["scan"]["suggested_commands"] == {
        "test": "python -m pytest",
        "lint": None,
        "typecheck": None,
        "build": None,
    }
    assert set(payload["git"]) == {"status", "diff_stat", "recent_log"}
    assert all(isinstance(value, str) for value in payload["git"].values())
    assert payload["verification_steps"] == [
        {"name": "test", "command": ["python", "-m", "pytest", "-v"]},
        {"name": "lint", "command": ["python", "-m", "ruff", "check", "."]},
    ]
```

- [ ] **Step 2: Run the focused contract test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_context_route_returns_project_context -v
```

Expected: PASS. This is a characterization test proving the existing backend already supplies every field required by the cards.

- [ ] **Step 3: Commit the payload contract test**

Run:

```powershell
git add tests/test_web_server.py
git commit -m "test: cover web context payload fields"
```

Expected: commit succeeds.

---

### Task 2: Add the Context Cards Container

**Files:**
- Modify: `tests/test_web_server.py`
- Modify: `src/dev_agent/web/static/index.html`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Write failing HTML assertions**

In `test_static_assets_include_console_interactions()`, add these assertions after `assert "Provider plan 审批" in index_body`:

```python
    assert 'id="context-cards"' in index_body
    assert 'class="context-card-list"' in index_body
    assert '<h3 class="result-heading">原始 JSON</h3>' in index_body
    context_cards_index = index_body.index('id="context-cards"')
    context_json_index = index_body.index('id="context"')
    assert context_cards_index < context_json_index
```

- [ ] **Step 2: Run the static asset test and verify RED**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because `index.html` does not yet contain `context-cards`.

- [ ] **Step 3: Add the HTML container and raw JSON heading**

In `src/dev_agent/web/static/index.html`, replace:

```html
        <article class="panel">
          <h2>上下文</h2>
          <pre id="context">加载中...</pre>
        </article>
```

with:

```html
        <article class="panel">
          <h2>上下文</h2>
          <div id="context-cards" class="context-card-list"></div>
          <h3 class="result-heading">原始 JSON</h3>
          <pre id="context">加载中...</pre>
        </article>
```

- [ ] **Step 4: Re-run the static asset test and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: PASS.

- [ ] **Step 5: Commit the context HTML scaffold**

Run:

```powershell
git add tests/test_web_server.py src/dev_agent/web/static/index.html
git commit -m "feat: add web context card container"
```

Expected: commit succeeds.

---

### Task 3: Render Context Cards and Copyable Commands

**Files:**
- Modify: `tests/test_web_server.py`
- Modify: `src/dev_agent/web/static/app.js`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Write failing JavaScript wiring assertions**

In `test_static_assets_include_console_interactions()`, add these assertions after `assert "loadContext" in js_body`:

```python
    assert "contextCards" in js_body
    assert "clearContextCards" in js_body
    assert "formatContextCommand" in js_body
    assert "collectContextCommands" in js_body
    assert "contextCommandLabel" in js_body
    assert "copyContextCommand" in js_body
    assert "renderContextCards" in js_body
    assert "navigator.clipboard.writeText(command)" in js_body
    assert 'button.textContent = "已复制"' in js_body
    assert 'button.textContent = "复制失败"' in js_body
    load_context_index = js_body.index("async function loadContext")
    render_context_index = js_body.index("renderContextCards(payload)", load_context_index)
    context_json_index = js_body.index('renderJson("context", payload)', load_context_index)
    assert render_context_index < context_json_index
```

- [ ] **Step 2: Run the static asset test and verify RED**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because the context rendering and clipboard helpers do not exist.

- [ ] **Step 3: Add context normalization and command helpers**

In `src/dev_agent/web/static/app.js`, add this block after `getJson` and before `historyCards`:

```javascript
const contextCards = () => document.getElementById("context-cards");

const clearContextCards = () => {
  contextCards().replaceChildren();
};

const contextObject = (value) => {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value;
  }
  return {};
};

const contextText = (value, fallback) => {
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  return fallback;
};

const contextValues = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => typeof item === "string" || typeof item === "number")
    .map((item) => String(item).trim())
    .filter((item) => item !== "");
};

const contextCommandLabel = (name) => {
  const labels = {
    test: "测试",
    lint: "代码检查",
    typecheck: "类型检查",
    build: "构建",
  };
  return labels[name] || contextText(name, "验证命令");
};

const formatContextCommandPart = (part) => {
  const text = String(part);
  if (text === "" || /[\s\"]/.test(text)) {
    return JSON.stringify(text);
  }
  return text;
};

const formatContextCommand = (command) => {
  if (typeof command === "string") {
    return command.trim();
  }
  if (!Array.isArray(command)) {
    return "";
  }
  return command
    .filter((part) => typeof part === "string" || typeof part === "number")
    .map(formatContextCommandPart)
    .join(" ")
    .trim();
};

const collectContextCommands = (payload) => {
  const source = contextObject(payload);
  const steps = Array.isArray(source.verification_steps) ? source.verification_steps : [];
  let candidates = steps
    .map((step) => {
      const item = contextObject(step);
      return {
        label: contextCommandLabel(item.name),
        command: formatContextCommand(item.command),
      };
    })
    .filter((item) => item.command !== "");

  if (candidates.length === 0) {
    const scan = contextObject(source.scan);
    const suggested = contextObject(scan.suggested_commands);
    candidates = ["test", "lint", "typecheck", "build"]
      .map((name) => ({
        label: contextCommandLabel(name),
        command: formatContextCommand(suggested[name]),
      }))
      .filter((item) => item.command !== "");
  }

  const seen = new Set();
  return candidates.filter((item) => {
    if (seen.has(item.command)) {
      return false;
    }
    seen.add(item.command);
    return true;
  });
};

const copyContextCommand = async (button, command) => {
  try {
    await navigator.clipboard.writeText(command);
    button.textContent = "已复制";
  } catch (_error) {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => {
    if (button.isConnected) {
      button.textContent = "一键复制";
    }
  }, 1600);
};
```

- [ ] **Step 4: Add focused DOM construction helpers**

Add this block immediately after `copyContextCommand`:

```javascript
const appendContextText = (parent, className, text) => {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
};

const appendContextTags = (parent, label, values) => {
  const field = document.createElement("section");
  field.className = "context-field";
  appendContextText(field, "context-label", label);

  const tags = document.createElement("div");
  tags.className = "context-tag-list";
  const normalized = contextValues(values);
  if (normalized.length === 0) {
    appendContextText(tags, "context-empty-state", "未检测到");
  } else {
    normalized.forEach((value) => {
      appendContextText(tags, "context-tag", value);
    });
  }
  field.appendChild(tags);
  parent.appendChild(field);
};

const appendContextGitSection = (parent, label, value, emptyText) => {
  const section = document.createElement("section");
  section.className = "context-git-section";
  appendContextText(section, "context-label", label);
  const output = document.createElement("pre");
  output.className = "context-git-output";
  output.textContent = contextText(value, emptyText);
  section.appendChild(output);
  parent.appendChild(section);
};

const buildContextProjectCard = (payload) => {
  const source = contextObject(payload);
  const project = contextObject(source.project);
  const scan = contextObject(source.scan);
  const card = document.createElement("article");
  card.className = "context-card context-project-card";

  appendContextText(card, "context-card-kicker", "项目总览");
  const title = document.createElement("h3");
  title.textContent = contextText(project.name, "未命名项目");
  card.appendChild(title);
  appendContextText(card, "context-path", `扫描目录：${contextText(scan.root, "未检测到")}`);

  const fields = document.createElement("div");
  fields.className = "context-field-grid";
  appendContextTags(fields, "技术栈", project.tech_stack);
  appendContextTags(fields, "识别语言", scan.languages);
  appendContextTags(fields, "项目标记", scan.markers);
  card.appendChild(fields);
  return card;
};

const buildContextGitCard = (payload) => {
  const source = contextObject(payload);
  const git = contextObject(source.git);
  const card = document.createElement("article");
  let stateClass = "context-git-unknown";
  let stateLabel = "暂无 Git 状态";
  let statusText = "暂无 Git 状态";

  if (typeof git.status === "string") {
    if (git.status.trim() === "") {
      stateClass = "context-git-clean";
      stateLabel = "工作区干净";
      statusText = "没有未提交变更。";
    } else {
      stateClass = "context-git-changed";
      stateLabel = "工作区有变更";
      statusText = git.status;
    }
  }

  card.className = `context-card context-git-card ${stateClass}`;
  const header = document.createElement("div");
  header.className = "context-card-header";
  const title = document.createElement("h3");
  title.textContent = "Git 状态";
  const badge = document.createElement("span");
  badge.className = `context-status-badge ${stateClass}`;
  badge.textContent = stateLabel;
  header.append(title, badge);
  card.appendChild(header);

  const fields = document.createElement("div");
  fields.className = "context-git-grid";
  appendContextGitSection(fields, "工作区", statusText, "暂无 Git 状态");
  appendContextGitSection(fields, "变更统计", git.diff_stat, "暂无变更统计");
  appendContextGitSection(fields, "最近提交", git.recent_log, "暂无提交记录");
  card.appendChild(fields);
  return card;
};

const buildContextCommandsCard = (payload) => {
  const card = document.createElement("article");
  card.className = "context-card context-command-card";
  const title = document.createElement("h3");
  title.textContent = "验证命令";
  card.appendChild(title);

  const list = document.createElement("div");
  list.className = "context-command-list";
  const commands = collectContextCommands(payload);
  if (commands.length === 0) {
    appendContextText(list, "context-empty-state", "暂无验证命令");
  } else {
    commands.forEach(({ label, command }) => {
      const row = document.createElement("div");
      row.className = "context-command-row";
      const main = document.createElement("div");
      main.className = "context-command-main";
      appendContextText(main, "context-command-label", label);
      const code = document.createElement("code");
      code.className = "context-command-code";
      code.textContent = command;
      main.appendChild(code);

      const button = document.createElement("button");
      button.type = "button";
      button.className = "context-copy-button";
      button.textContent = "一键复制";
      button.setAttribute("aria-label", `复制${label}命令`);
      button.addEventListener("click", () => copyContextCommand(button, command));
      row.append(main, button);
      list.appendChild(row);
    });
  }
  card.appendChild(list);
  return card;
};

const buildContextSupportCard = (payload) => {
  const source = contextObject(payload);
  const preferences = contextObject(source.preferences);
  const card = document.createElement("article");
  card.className = "context-card context-support-card";
  const title = document.createElement("h3");
  title.textContent = "偏好与规则";
  card.appendChild(title);

  const fields = document.createElement("div");
  fields.className = "context-preferences";
  appendContextText(
    fields,
    "context-preference",
    `语言：${contextText(preferences.language, "未设置")}`,
  );
  appendContextText(
    fields,
    "context-preference",
    `审批模式：${contextText(preferences.approval_mode, "未设置")}`,
  );
  card.appendChild(fields);

  const details = document.createElement("details");
  details.className = "context-rule-detail";
  const summary = document.createElement("summary");
  summary.textContent = "查看项目规则";
  const rules = document.createElement("pre");
  rules.className = "context-rule-text";
  rules.textContent = contextText(source.rules_text, "暂无项目规则");
  details.append(summary, rules);
  card.appendChild(details);
  return card;
};

const renderContextCards = (payload) => {
  clearContextCards();
  const source = contextObject(payload);
  const overview = document.createElement("div");
  overview.className = "context-overview-grid";
  overview.append(buildContextProjectCard(source), buildContextGitCard(source));
  contextCards().append(
    overview,
    buildContextCommandsCard(source),
    buildContextSupportCard(source),
  );
};
```

- [ ] **Step 5: Render cards before raw JSON**

Replace:

```javascript
async function loadContext() {
  renderJson("context", await getJson("/api/context"));
}
```

with:

```javascript
async function loadContext() {
  const payload = await getJson("/api/context");
  renderContextCards(payload);
  renderJson("context", payload);
}
```

- [ ] **Step 6: Run the static asset test and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: PASS.

- [ ] **Step 7: Commit context rendering and clipboard behavior**

Run:

```powershell
git add tests/test_web_server.py src/dev_agent/web/static/app.js
git commit -m "feat: render web context cards"
```

Expected: commit succeeds.

---

### Task 4: Style the Context Cards

**Files:**
- Modify: `tests/test_web_server.py`
- Modify: `src/dev_agent/web/static/styles.css`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Write failing CSS assertions**

In `test_static_assets_include_console_interactions()`, add these assertions after `assert ".history-detail" in css_body`:

```python
    assert ".context-card-list" in css_body
    assert ".context-card" in css_body
    assert ".context-project-card" in css_body
    assert ".context-git-clean" in css_body
    assert ".context-git-changed" in css_body
    assert ".context-status-badge" in css_body
    assert ".context-command-row" in css_body
    assert ".context-copy-button" in css_body
    assert ".context-rule-detail" in css_body
```

- [ ] **Step 2: Run the static asset test and verify RED**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because the context CSS classes do not exist.

- [ ] **Step 3: Add context card styles**

In `src/dev_agent/web/static/styles.css`, insert this block before `.history-card-list`:

```css
.context-card-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.context-overview-grid {
  display: grid;
  gap: 12px;
}

.context-card {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.52);
  box-shadow: 0 12px 28px rgba(31, 45, 33, 0.08);
}

.context-project-card {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.72);
}

.context-git-card.context-git-clean {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.66);
}

.context-git-card.context-git-changed {
  border-color: rgba(201, 112, 74, 0.46);
  background: rgba(255, 244, 232, 0.86);
}

.context-git-card.context-git-unknown {
  background: rgba(255, 255, 255, 0.56);
}

.context-card h3 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.context-card-kicker,
.context-label,
.context-command-label {
  color: var(--muted);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.context-card-kicker {
  margin-bottom: 5px;
  color: var(--moss);
}

.context-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.context-status-badge {
  flex: 0 0 auto;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.68);
  font-size: 0.76rem;
  font-weight: 800;
  white-space: nowrap;
}

.context-status-badge.context-git-clean {
  color: #2f5b2d;
  background: rgba(229, 244, 218, 0.9);
}

.context-status-badge.context-git-changed {
  color: #8b3f1e;
  background: rgba(255, 232, 211, 0.95);
}

.context-status-badge.context-git-unknown {
  color: var(--muted);
}

.context-path,
.context-preference,
.context-empty-state {
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.context-path {
  margin-top: 8px;
}

.context-field-grid,
.context-git-grid,
.context-preferences {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.context-field-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.context-field,
.context-git-section,
.context-preference {
  min-width: 0;
  border-radius: 12px;
  padding: 10px;
  background: rgba(255, 252, 244, 0.62);
}

.context-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
}

.context-tag {
  max-width: 100%;
  border: 1px solid rgba(82, 107, 74, 0.24);
  border-radius: 999px;
  padding: 3px 8px;
  color: var(--moss);
  background: rgba(255, 255, 255, 0.68);
  font-size: 0.78rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.context-git-output,
.context-rule-text {
  min-height: auto;
  margin-top: 7px;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.context-command-list {
  display: grid;
  gap: 9px;
  margin-top: 12px;
}

.context-command-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  border-radius: 12px;
  padding: 10px;
  background: rgba(255, 252, 244, 0.7);
}

.context-command-main {
  min-width: 0;
}

.context-command-code {
  display: block;
  margin-top: 5px;
  color: var(--ink);
  font: 0.82rem/1.5 Consolas, "Microsoft YaHei UI", monospace;
  overflow-wrap: anywhere;
}

.context-copy-button {
  min-height: 36px;
  margin: 0;
  padding: 8px 12px;
  font-size: 0.76rem;
  white-space: nowrap;
}

.context-rule-detail {
  margin-top: 10px;
  border-radius: 12px;
  padding: 9px 10px;
  background: rgba(255, 252, 244, 0.64);
}

.context-rule-detail summary {
  cursor: pointer;
  color: var(--moss);
  font-weight: 800;
}
```

- [ ] **Step 4: Add mobile stacking rules**

In the existing `@media (max-width: 860px)` block, replace:

```css
  .history-card-header,
  .preview-card-header,
  .audit-card-header {
    flex-direction: column;
  }
```

with:

```css
  .context-card-header,
  .history-card-header,
  .preview-card-header,
  .audit-card-header {
    flex-direction: column;
  }

  .context-field-grid,
  .context-command-row {
    grid-template-columns: 1fr;
  }

  .context-copy-button {
    width: 100%;
  }
```

- [ ] **Step 5: Run the static asset test and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: PASS.

- [ ] **Step 6: Commit context card styles**

Run:

```powershell
git add tests/test_web_server.py src/dev_agent/web/static/styles.css
git commit -m "style: add responsive web context cards"
```

Expected: commit succeeds.

---

### Task 5: Verify the Complete Feature

**Files:**
- No source changes expected.
- Test: web server tests, full suite, local Web smoke, browser behavior.

- [ ] **Step 1: Run Web server tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py -v
```

Expected: all `tests/test_web_server.py` tests pass.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Run the local Web smoke check**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m dev_agent.cli serve --port 0 --check
```

Expected: command exits 0 and JSON includes `"ok": true` plus a local `http://127.0.0.1:<port>/` URL.

- [ ] **Step 4: Perform a local browser acceptance check**

Start the local server without invoking any provider:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m dev_agent.cli serve --port 8765
```

Open `http://127.0.0.1:8765/` and confirm:

- 项目总览、Git 状态、验证命令、偏好与规则按顺序显示。
- Git 状态有文字标签，空字段使用“未检测到”“暂无”或“未设置”。
- 点击“一键复制”后显示“已复制”；在剪贴板权限被拒绝时显示“复制失败”。
- 复制操作不会执行命令，也不会产生新的网络请求。
- 中文、长路径和长命令正常换行；窄屏下按钮移到命令下方且页面不横向滚动。
- “原始 JSON”仍位于可读卡片之后并包含完整 payload。

Stop the local server with `Ctrl+C` after acceptance is complete.

- [ ] **Step 5: Confirm repository state**

Run:

```powershell
git status --short --branch
git log --oneline -10
```

Expected: working tree is clean, and recent commits include:

```text
test: cover web context payload fields
feat: add web context card container
feat: render web context cards
style: add responsive web context cards
docs: clarify web context command shape
docs: design web context cards
```

---

## Plan Self-Review

**Spec coverage:** Tasks cover the project overview, Git clean/changed/unknown states, scan root, technology/language/marker tags, verification step priority, suggested-command fallback, command-array formatting, deduplication, copy success/failure feedback, preferences, collapsible rules, raw JSON retention, `textContent` safety, empty values, responsive wrapping, API contract protection, local smoke and full tests.

**Placeholder scan:** 计划未包含任何未完成标记或延期实现描述，每个代码修改步骤都给出了要添加或替换的完整代码块。

**Type consistency:** The plan uses the current payload names `project`, `preferences`, `rules_text`, `scan`, `git`, and `verification_steps`. It treats `verification_steps[].command` as the existing `list[str]` shape while accepting a string for defensive compatibility. New functions are consistently named `contextCards`, `clearContextCards`, `contextObject`, `contextText`, `contextValues`, `contextCommandLabel`, `formatContextCommand`, `collectContextCommands`, `copyContextCommand`, `buildContextProjectCard`, `buildContextGitCard`, `buildContextCommandsCard`, `buildContextSupportCard`, and `renderContextCards`.

**Scope control:** The plan modifies only existing Web static assets and tests. It adds no backend routes, schema changes, dependencies, command execution, Git writes, provider calls, supplier probing, background agents, pressure tests, or destructive behavior.

## Post-Review Hardening

代码审查后增加以下约束，执行时以本节为准：

- 参数数组按 Windows PowerShell 和 Windows 原生程序参数规则格式化，不使用 `JSON.stringify` 生成 Shell 文本。
- 可执行文件使用调用运算符 `&`；参数区使用 `--%` 停止 PowerShell 重解析，再按 Windows CRT 引号算法编码空参数、空白、双引号和尾部反斜杠。
- `verification_steps` 的名称和命令必须同时有效，否则回退到 `scan.suggested_commands`。
- 每条复制按钮配套独立的 `role="status"` live region，播报成功和失败并在复位时清空。
- `tests/test_web_server.py` 调用 `tests/web_context_cards.test.mjs`，以 Node 内建测试执行上述行为，并覆盖恶意文本只能通过 `textContent` 呈现；Windows 下使用临时 Node 探针对 PowerShell 命令执行真实 `argv` 往返验证。
- 外层 `context-cards` 不设置 live region，只保留命令行内独立的 `role="status"` 节点，避免重复播报。
