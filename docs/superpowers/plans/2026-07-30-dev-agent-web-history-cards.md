# Web 历史可读卡片 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Web 历史区域渲染任务复盘卡片，让用户能快速查看历史任务标题、状态、摘要、验证命令、事件和经验。

**Architecture:** 复用现有 `/api/history` payload，不新增后端路由或 schema。前端 `loadHistory()` 获取 payload 后同时渲染 history cards 和 raw JSON；卡片使用原生 DOM 与 `textContent` 安全渲染，并用 `<details>` 展示完整详情。

**Tech Stack:** Python stdlib HTTP server、pytest、原生 HTML/CSS/JavaScript，无前端构建工具，无真实模型 provider 请求。

---

## File Structure

- Modify: `tests/test_web_server.py`
  - 扩展历史 route 测试，保护 `TaskRecord` 字段契约。
  - 扩展静态资源测试，覆盖 `history-cards` 容器、JS helper、CSS class 和 raw JSON 标题。
- Modify: `src/dev_agent/web/static/index.html`
  - 在 `<pre id="history">` 前新增 `history-cards` 容器和历史 raw JSON 标题。
- Modify: `src/dev_agent/web/static/app.js`
  - 新增历史卡片 DOM getter、状态标签 helper、列表渲染 helper、卡片渲染函数。
  - 修改 `loadHistory()` 同步渲染卡片与 raw JSON。
- Modify: `src/dev_agent/web/static/styles.css`
  - 新增历史卡片、状态标签、摘要、详情列表和空态样式。
  - 复用现有纸张、苔藓、陶土色系统。

## Safety Scope

- 不调用真实模型供应商。
- 不批量探测 provider。
- 不启动并发智能体。
- 不做压力测试或批量重试。
- 不新增后端接口或持久化字段。
- 所有文本读写保持 UTF-8；中文直接写中文，不使用 `\uXXXX` 转义。

---

### Task 1: Protect History Payload Contract

**Files:**
- Modify: `tests/test_web_server.py`
- Test: `tests/test_web_server.py::test_history_route_returns_json`

- [ ] **Step 1: Add TaskRecord import**

In `tests/test_web_server.py`, add this import after `from dev_agent.encoding import write_text_utf8`:

```python
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
```

- [ ] **Step 2: Replace the empty-only history route test**

Replace the body of `test_history_route_returns_json()` with:

```python
def test_history_route_returns_json(tmp_path) -> None:
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-history-1",
            title="修复中文乱码",
            status="passed",
            summary="UTF-8 修复",
            events=["runtime_started", "runtime_completed"],
            verification=["python -m pytest -v"],
            lessons=["提交前运行完整测试"],
        )
    )
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/history")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["tasks"][0]["task_id"] == "task-history-1"
    assert payload["tasks"][0]["title"] == "修复中文乱码"
    assert payload["tasks"][0]["status"] == "passed"
    assert payload["tasks"][0]["summary"] == "UTF-8 修复"
    assert payload["tasks"][0]["events"] == ["runtime_started", "runtime_completed"]
    assert payload["tasks"][0]["verification"] == ["python -m pytest -v"]
    assert payload["tasks"][0]["lessons"] == ["提交前运行完整测试"]
```

- [ ] **Step 3: Run the focused test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_history_route_returns_json -v
```

Expected: PASS. This confirms the current backend payload already contains the fields the front end will render.

- [ ] **Step 4: Commit the contract test**

Run:

```powershell
git add tests/test_web_server.py
git commit -m "test: cover web history payload fields"
```

Expected: commit succeeds.

---

### Task 2: Add Static Asset Coverage and History Container

**Files:**
- Modify: `tests/test_web_server.py`
- Modify: `src/dev_agent/web/static/index.html`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Write failing static asset assertions**

In `tests/test_web_server.py`, extend `test_static_assets_include_console_interactions()` with these assertions.

Add after `assert "Provider plan 审批" in index_body`:

```python
    assert "history-cards" in index_body
    assert "历史 JSON" in index_body
```

Add after `assert ".audit-diff" in css_body`:

```python
    assert ".history-card-list" in css_body
    assert ".history-card" in css_body
    assert ".history-status-badge" in css_body
    assert ".history-status-passed" in css_body
    assert ".history-status-failed" in css_body
    assert ".history-detail" in css_body
```

Add after `assert "loadContext" in js_body`:

```python
    assert "historyCards" in js_body
    assert "renderHistoryCards" in js_body
    assert "historyStatusLabel" in js_body
    assert "historyStatusClass" in js_body
    assert "clearHistoryCards" in js_body
    assert "appendHistoryList" in js_body
```

Add after `assert "textContent" in js_body`:

```python
    load_history_index = js_body.index("async function loadHistory")
    render_history_index = js_body.index("renderHistoryCards(payload)", load_history_index)
    render_json_index = js_body.index('renderJson("history", payload)', load_history_index)
    assert render_history_index < render_json_index
```

- [ ] **Step 2: Run static test and verify RED**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because `history-cards` and history card JS/CSS do not exist yet.

- [ ] **Step 3: Add history cards container to HTML**

In `src/dev_agent/web/static/index.html`, replace:

```html
        <article class="panel">
          <h2>历史</h2>
          <pre id="history">加载中...</pre>
        </article>
```

with:

```html
        <article class="panel">
          <h2>历史</h2>
          <div id="history-cards" class="history-card-list" aria-live="polite"></div>
          <h3 class="result-heading">历史 JSON</h3>
          <pre id="history">加载中...</pre>
        </article>
```

- [ ] **Step 4: Re-run static test and verify partial RED**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because JS and CSS history helpers/classes do not exist yet.

---

### Task 3: Render History Cards in JavaScript

**Files:**
- Modify: `src/dev_agent/web/static/app.js`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Add history DOM getter**

Add this line after `const getJson = async (path) => { ... };`:

```javascript
const historyCards = () => document.getElementById("history-cards");
```

- [ ] **Step 2: Add history status helpers**

Add this block after `const historyCards = () => document.getElementById("history-cards");`:

```javascript
const historyStatusLabel = (status) => {
  if (status === "passed") {
    return "通过";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "running") {
    return "运行中";
  }
  if (status === "planned") {
    return "已计划";
  }
  return status || "未知状态";
};

const historyStatusClass = (status) => {
  if (status === "passed") {
    return "history-status-passed";
  }
  if (status === "failed") {
    return "history-status-failed";
  }
  if (status === "running") {
    return "history-status-running";
  }
  if (status === "planned") {
    return "history-status-planned";
  }
  return "history-status-unknown";
};
```

- [ ] **Step 3: Add history list rendering helper**

Add this block after `historyStatusClass`:

```javascript
const clearHistoryCards = () => {
  historyCards().replaceChildren();
};

const appendHistoryList = (parent, title, items, emptyText) => {
  const section = document.createElement("section");
  section.className = "history-detail-section";
  const heading = document.createElement("h5");
  heading.textContent = title;
  section.appendChild(heading);

  const list = document.createElement("ul");
  list.className = "history-list";
  const values = Array.isArray(items) ? items : [];
  if (values.length === 0) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    list.appendChild(item);
  } else {
    values.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = String(value);
      list.appendChild(item);
    });
  }
  section.appendChild(list);
  parent.appendChild(section);
};
```

- [ ] **Step 4: Add history card renderer**

Add this block after `appendHistoryList`:

```javascript
const renderHistoryCards = (payload) => {
  clearHistoryCards();
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
  if (tasks.length === 0) {
    appendText(historyCards(), "history-empty-state", "暂无历史任务。完成 dry-run 或确认执行后会出现在这里。");
    return;
  }

  tasks.forEach((task) => {
    const statusClass = historyStatusClass(task.status);
    const events = Array.isArray(task.events) ? task.events : [];
    const verification = Array.isArray(task.verification) ? task.verification : [];
    const lessons = Array.isArray(task.lessons) ? task.lessons : [];

    const card = document.createElement("article");
    card.className = `history-card ${statusClass}`;

    const header = document.createElement("div");
    header.className = "history-card-header";
    const title = document.createElement("h3");
    title.textContent = task.title || "未命名任务";
    const badge = document.createElement("span");
    badge.className = `history-status-badge ${statusClass}`;
    badge.textContent = historyStatusLabel(task.status);
    header.append(title, badge);

    const summary = document.createElement("p");
    summary.className = "history-summary";
    summary.textContent = task.summary || "暂无摘要";

    const latestEvent = events.length > 0 ? events[events.length - 1] : "暂无事件记录";
    const meta = document.createElement("p");
    meta.className = "history-meta";
    meta.textContent = `验证 ${verification.length} 项 · 经验 ${lessons.length} 条 · 最近事件：${latestEvent}`;

    const taskId = document.createElement("p");
    taskId.className = "history-task-id";
    taskId.textContent = `任务 ID：${task.task_id || "未知"}`;

    const details = document.createElement("details");
    details.className = "history-detail";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "查看详情";
    details.appendChild(detailsSummary);
    appendHistoryList(details, "验证命令", verification, "暂无验证命令");
    appendHistoryList(details, "经验", lessons, "暂无经验");
    appendHistoryList(details, "事件", events, "暂无事件");

    card.append(header, summary, meta, taskId, details);
    historyCards().appendChild(card);
  });
};
```

- [ ] **Step 5: Update loadHistory to render cards before raw JSON**

Replace:

```javascript
async function loadHistory() {
  renderJson("history", await getJson("/api/history"));
}
```

with:

```javascript
async function loadHistory() {
  const payload = await getJson("/api/history");
  renderHistoryCards(payload);
  renderJson("history", payload);
}
```

- [ ] **Step 6: Run static test and verify partial RED**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because CSS history classes do not exist yet. If JS assertions fail, inspect `src/dev_agent/web/static/app.js` and fix the function names before proceeding.

---

### Task 4: Style History Cards

**Files:**
- Modify: `src/dev_agent/web/static/styles.css`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Add history card styles**

In `src/dev_agent/web/static/styles.css`, insert this block before `.preview-card-list`:

```css
.history-card-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.history-empty-state,
.history-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.52);
}

.history-empty-state {
  padding: 14px;
  color: var(--muted);
  line-height: 1.6;
}

.history-card {
  padding: 14px;
  box-shadow: 0 12px 28px rgba(31, 45, 33, 0.08);
}

.history-card.history-status-passed {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.72);
}

.history-card.history-status-failed {
  border-color: rgba(154, 55, 45, 0.36);
  background: rgba(255, 238, 232, 0.86);
}

.history-card.history-status-running {
  border-color: rgba(64, 112, 111, 0.34);
  background: rgba(235, 247, 244, 0.74);
}

.history-card.history-status-planned,
.history-card.history-status-unknown {
  border-color: rgba(29, 38, 31, 0.16);
  background: rgba(255, 255, 255, 0.56);
}

.history-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.history-card-header h3 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.history-status-badge {
  flex: 0 0 auto;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 10px;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.64);
  font-size: 0.78rem;
  font-weight: 800;
  white-space: nowrap;
}

.history-status-badge.history-status-passed {
  color: #2f5b2d;
  background: rgba(229, 244, 218, 0.9);
}

.history-status-badge.history-status-failed {
  color: #7a251d;
  background: rgba(255, 223, 216, 0.95);
}

.history-status-badge.history-status-running {
  color: #285f5a;
  background: rgba(222, 244, 240, 0.95);
}

.history-summary,
.history-meta,
.history-task-id {
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.history-summary {
  margin: 10px 0 0;
  color: var(--ink);
}

.history-meta,
.history-task-id {
  margin: 8px 0 0;
}

.history-detail {
  margin-top: 10px;
  border-radius: 12px;
  padding: 9px 10px;
  background: rgba(255, 252, 244, 0.64);
}

.history-detail summary {
  cursor: pointer;
  color: var(--moss);
  font-weight: 800;
}

.history-detail-section h5 {
  margin: 12px 0 6px;
  color: var(--muted);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.history-list {
  margin: 0;
  padding-left: 18px;
  color: var(--ink);
  font-size: 0.84rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 2: Make history headers stack on mobile**

In the existing `@media (max-width: 860px)` block, replace:

```css
  .preview-card-header,
  .audit-card-header {
    flex-direction: column;
  }
```

with:

```css
  .history-card-header,
  .preview-card-header,
  .audit-card-header {
    flex-direction: column;
  }
```

- [ ] **Step 3: Run static test and verify GREEN**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: PASS.

- [ ] **Step 4: Commit frontend history cards**

Run:

```powershell
git add tests/test_web_server.py src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css
git commit -m "feat: render web history cards"
```

Expected: commit succeeds.

---

### Task 5: Full Verification and Smoke

**Files:**
- No source changes expected.
- Test: web server tests, full suite, and web smoke.

- [ ] **Step 1: Run web server tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py -v
```

Expected: all `tests/test_web_server.py` tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Run Web smoke check with explicit local PYTHONPATH**

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

- [ ] **Step 4: Confirm git state**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected: working tree is clean, and recent commits include `docs: design web history cards`, `docs: plan web history cards`, and `feat: render web history cards`.

---

## Plan Self-Review

**Spec coverage:** The plan covers history card container, status labels, task title/status/summary, verification and lesson counts, latest event, task id, details for events/verification/lessons, empty state, raw JSON retention, `loadHistory()` refresh behavior, `textContent` safety, mobile wrapping, local tests, full verification, and provider-safety exclusions.

**Placeholder scan:** The plan contains no `TBD`, no `TODO`, no incomplete placeholder sections, and no implementation steps that defer behavior to future work.

**Type consistency:** The plan consistently uses existing payload names `tasks`, `task_id`, `title`, `status`, `summary`, `events`, `verification`, and `lessons`; existing function `loadHistory`; and new functions `historyCards`, `renderHistoryCards`, `historyStatusLabel`, `historyStatusClass`, `clearHistoryCards`, and `appendHistoryList`.

**Scope control:** The plan does not add backend routes, persistence fields, real provider calls, supplier probing, background agents, complete history search, new dependencies, or destructive Git behavior.
