# Web 执行审计卡片 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Web provider plan apply 后渲染结果优先的执行审计卡片，让用户能快速复盘执行结论、实际变更、内容片段和 Git diff 摘要。

**Architecture:** 不新增后端路由，继续复用 `/api/provider-plan/apply` 的现有 payload。前端在 apply 成功或失败后把 payload 转成安全的 DOM 卡片，raw JSON 仍保留；preview 成功、preview 失败和输入变化时清空过期审计结果。

**Tech Stack:** Python stdlib HTTP server、pytest、原生 HTML/CSS/JavaScript，无前端构建工具，无真实模型 provider 请求。

---

## File Structure

- Modify: `tests/test_web_server.py`
  - 扩展 `test_static_assets_include_console_interactions()`，覆盖审计卡片 DOM、JS helper、CSS class 和 raw apply JSON 标题。
  - 扩展 `test_provider_plan_apply_route_writes_file_and_records_history()`，确认 apply payload 继续提供前端审计卡片需要的数据源。
- Modify: `src/dev_agent/web/static/index.html`
  - 在 apply raw JSON `<pre>` 前加入 `<div id="provider-audit-cards" class="audit-card-list" aria-live="polite"></div>`。
  - 将 apply raw JSON 标题改为“执行结果 JSON”，preview raw JSON 标题保持“原始 JSON”。
- Modify: `src/dev_agent/web/static/app.js`
  - 新增审计卡片 DOM getter、清空函数、失败渲染函数和 apply payload 渲染函数。
  - apply 成功后渲染审计卡片；apply 请求失败时渲染失败审计状态。
  - preview 成功、preview 失败和输入变化时清空过期审计卡片。
- Modify: `src/dev_agent/web/static/styles.css`
  - 新增 `.audit-card-list`、`.audit-card`、`.audit-card-header`、`.audit-status-badge`、`.audit-meta`、`.audit-diff`、`.audit-error`、`.audit-success`、`.audit-failed`、`.audit-neutral`。
  - 复用现有纸张、苔藓、陶土色系统，并保证长路径、内容片段、diff stat 可换行。

## Safety Scope

- 不调用真实模型供应商。
- 不批量探测 provider。
- 不启动并发智能体。
- 不做压力测试或批量重试。
- 所有测试使用本地 fake provider plan payload。
- 所有文本读写保持 UTF-8；中文直接写中文，不使用 `\uXXXX` 转义。

---

### Task 1: Protect Apply Payload Data Source

**Files:**
- Modify: `tests/test_web_server.py`
- Test: `tests/test_web_server.py::test_provider_plan_apply_route_writes_file_and_records_history`

- [ ] **Step 1: Write the failing payload assertions**

In `tests/test_web_server.py`, append these assertions inside `test_provider_plan_apply_route_writes_file_and_records_history()` after the existing `assert payload["applied_changes"][0]["path"] == "docs/from-web-route.md"` line:

```python
    assert payload["preview_changes"][0]["path"] == "docs/from-web-route.md"
    assert payload["preview_changes"][0]["content_preview"] == "确认 route 写入\n"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert "diff_stat" in payload
    assert payload["execution_error"] is None
```

- [ ] **Step 2: Run the focused test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_provider_plan_apply_route_writes_file_and_records_history -v
```

Expected: PASS. This verifies the existing backend already supplies the data needed by the UI. If it fails, stop and inspect `src/dev_agent/web/api.py` before changing frontend code.

- [ ] **Step 3: Commit if the test file changed**

Run:

```powershell
git add tests/test_web_server.py
git commit -m "test: cover web apply audit payload"
```

Expected: commit succeeds if the assertions were not already present.

---

### Task 2: Add Static Asset Coverage and Audit Container

**Files:**
- Modify: `tests/test_web_server.py`
- Modify: `src/dev_agent/web/static/index.html`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Write failing static asset assertions**

In `tests/test_web_server.py`, extend `test_static_assets_include_console_interactions()` with these assertions.

Add after `assert "provider-preview-cards" in index_body`:

```python
    assert "provider-audit-cards" in index_body
    assert "执行结果 JSON" in index_body
```

Add after `assert ".truncation-note" in css_body`:

```python
    assert ".audit-card-list" in css_body
    assert ".audit-card" in css_body
    assert ".audit-status-badge" in css_body
    assert ".audit-success" in css_body
    assert ".audit-failed" in css_body
    assert ".audit-diff" in css_body
```

Add after `assert "clearProviderPreviewCards" in js_body`:

```python
    assert "providerAuditCards" in js_body
    assert "renderProviderAuditCards" in js_body
    assert "renderProviderAuditFailure" in js_body
    assert "clearProviderAuditCards" in js_body
    assert "execution_error" in js_body
    assert "applied_changes" in js_body
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

Expected: FAIL because `provider-audit-cards` and audit JS/CSS classes do not exist yet.

- [ ] **Step 3: Add the audit card container to HTML**

In `src/dev_agent/web/static/index.html`, replace this block:

```html
                <h4 class="result-heading">执行结果</h4>
                <pre id="provider-apply-result" aria-live="polite">确认执行后显示结果。</pre>
```

with:

```html
                <div id="provider-audit-cards" class="audit-card-list" aria-live="polite"></div>
                <h4 class="result-heading">执行结果 JSON</h4>
                <pre id="provider-apply-result" aria-live="polite">确认执行后显示结果。</pre>
```

- [ ] **Step 4: Re-run static test and verify partial RED**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because JS and CSS audit functions/classes do not exist yet.

---

### Task 3: Render Audit Cards in JavaScript

**Files:**
- Modify: `src/dev_agent/web/static/app.js`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Add audit DOM getter**

In `src/dev_agent/web/static/app.js`, add this line after `const providerPreviewCards = () => document.getElementById("provider-preview-cards");`:

```javascript
const providerAuditCards = () => document.getElementById("provider-audit-cards");
```

- [ ] **Step 2: Add audit clearing and matching helpers**

Add this block after `const clearProviderPreviewCards = () => { providerPreviewCards().replaceChildren(); };`:

```javascript
const clearProviderAuditCards = () => {
  providerAuditCards().replaceChildren();
};

const previewChangeAt = (payload, index) => {
  const changes = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  return changes[index] || {};
};
```

- [ ] **Step 3: Add audit rendering helpers**

Add this block after `const renderProviderPreviewCards = (payload) => { ... };` and before `const resetProviderPreview = () => { ... };`. Keep the existing `renderProviderPreviewCards` function unchanged.

```javascript
const renderProviderAuditFailure = (message) => {
  clearProviderAuditCards();
  const card = document.createElement("article");
  card.className = "audit-card audit-failed";

  const header = document.createElement("div");
  header.className = "audit-card-header";
  const title = document.createElement("h4");
  title.textContent = "执行失败";
  const badge = document.createElement("span");
  badge.className = "audit-status-badge audit-failed";
  badge.textContent = "失败";
  header.append(title, badge);

  const error = document.createElement("div");
  error.className = "audit-error";
  error.textContent = message || "执行请求失败，请查看错误提示或原始 JSON。";

  card.append(header, error);
  providerAuditCards().appendChild(card);
};

const renderProviderAuditCards = (payload) => {
  clearProviderAuditCards();
  const appliedChanges = Array.isArray(payload.applied_changes) ? payload.applied_changes : [];
  const previewChanges = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  const hasExecutionError = typeof payload.execution_error === "string" && payload.execution_error.length > 0;

  const summary = document.createElement("article");
  summary.className = `audit-card ${hasExecutionError ? "audit-failed" : "audit-success"}`;
  const summaryHeader = document.createElement("div");
  summaryHeader.className = "audit-card-header";
  const summaryTitle = document.createElement("h4");
  summaryTitle.textContent = hasExecutionError ? "执行失败" : "执行完成";
  const summaryBadge = document.createElement("span");
  summaryBadge.className = `audit-status-badge ${hasExecutionError ? "audit-failed" : "audit-success"}`;
  summaryBadge.textContent = hasExecutionError ? "失败" : "成功";
  summaryHeader.append(summaryTitle, summaryBadge);
  const summaryMeta = document.createElement("p");
  summaryMeta.className = "audit-meta";
  summaryMeta.textContent = `已应用 ${appliedChanges.length} 项变更 · 计划 ${previewChanges.length} 项预览变更 · 历史已刷新`;
  summary.append(summaryHeader, summaryMeta);
  if (hasExecutionError) {
    appendText(summary, "audit-error", payload.execution_error);
  }
  providerAuditCards().appendChild(summary);

  if (appliedChanges.length === 0) {
    appendText(providerAuditCards(), "preview-empty-state", "没有实际应用变更记录。");
  }

  appliedChanges.forEach((change, index) => {
    const previewChange = previewChangeAt(payload, index);
    const riskClass = providerRiskClass(previewChange.risk);
    const card = document.createElement("article");
    card.className = `audit-card ${riskClass}`;

    const header = document.createElement("div");
    header.className = "audit-card-header";
    const path = document.createElement("h4");
    path.textContent = change.path || previewChange.path || "未命名路径";
    const badge = document.createElement("span");
    badge.className = `risk-badge ${riskClass}`;
    badge.textContent = providerRiskLabel(previewChange.risk || change.action);
    header.append(path, badge);

    const meta = document.createElement("p");
    meta.className = "audit-meta";
    const action = change.action || "未知动作";
    const bytes = Number.isFinite(change.content_bytes) ? `${change.content_bytes} bytes` : "未知 bytes";
    const targetState = typeof previewChange.exists === "boolean"
      ? (previewChange.exists ? "执行前目标已存在" : "执行前目标不存在")
      : "执行前目标状态未知";
    meta.textContent = `${action} · 写入 ${bytes} · ${targetState}`;

    const previewLabel = document.createElement("div");
    previewLabel.className = "preview-content-label";
    previewLabel.textContent = "已审阅内容片段";

    const preview = document.createElement("pre");
    preview.className = "content-preview";
    if (typeof previewChange.content_preview === "string") {
      preview.textContent = previewChange.content_preview === "" ? "内容为空" : previewChange.content_preview;
    } else {
      preview.textContent = "此执行结果没有可读内容片段，请查看原始 JSON。";
    }

    card.append(header, meta, previewLabel, preview);
    if (previewChange.content_preview_truncated === true) {
      appendText(card, "truncation-note", "内容片段已截断，请查看原始 JSON 或缩小计划后重新预览。");
    }
    providerAuditCards().appendChild(card);
  });

  const diff = document.createElement("article");
  diff.className = "audit-card audit-neutral";
  const diffHeader = document.createElement("div");
  diffHeader.className = "audit-card-header";
  const diffTitle = document.createElement("h4");
  diffTitle.textContent = "Git diff 摘要";
  const diffBadge = document.createElement("span");
  diffBadge.className = "audit-status-badge audit-neutral";
  diffBadge.textContent = "diff";
  diffHeader.append(diffTitle, diffBadge);
  const diffBody = document.createElement("pre");
  diffBody.className = "audit-diff";
  if (typeof payload.diff_stat === "string") {
    diffBody.textContent = payload.diff_stat === "" ? "没有 Git diff 摘要。" : payload.diff_stat;
  } else {
    diffBody.textContent = "此执行结果没有 Git diff 摘要字段。";
  }
  diff.append(diffHeader, diffBody);
  providerAuditCards().appendChild(diff);
};
```

- [ ] **Step 4: Clear audit cards on preview and input transitions**

In `resetProviderPreview()`, add `clearProviderAuditCards();` immediately after `clearProviderPreviewCards();`:

```javascript
  clearProviderPreviewCards();
  clearProviderAuditCards();
```

In `submitProviderPreview()`, add `clearProviderAuditCards();` immediately after `clearProviderPreviewCards();`:

```javascript
  clearProviderPreviewCards();
  clearProviderAuditCards();
```

In the `catch` block of `submitProviderPreview()`, add `clearProviderAuditCards();` after `clearProviderPreviewCards();`:

```javascript
    clearProviderPreviewCards();
    clearProviderAuditCards();
```

- [ ] **Step 5: Render audit cards on apply success and failure**

In `submitProviderApply()`, replace this success block:

```javascript
    renderJson("provider-apply-result", payload);
    providerStatus().textContent = payload.execution_error ? "执行失败" : "执行完成";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    await loadHistory();
```

with:

```javascript
    renderProviderAuditCards(payload);
    renderJson("provider-apply-result", payload);
    providerStatus().textContent = payload.execution_error ? "执行失败" : "执行完成";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    await loadHistory();
```

In the `catch` block of `submitProviderApply()`, replace this block:

```javascript
    renderJson("provider-apply-result", "执行失败。");
    providerStatus().textContent = "执行失败";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    showProviderError(error.message);
```

with:

```javascript
    renderProviderAuditFailure(error.message);
    renderJson("provider-apply-result", "执行失败。");
    providerStatus().textContent = "执行失败";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    showProviderError(error.message);
```

- [ ] **Step 6: Run static test and verify partial RED**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because CSS audit classes do not exist yet. If it fails because a JS assertion is missing, inspect `src/dev_agent/web/static/app.js` and fix the helper/function names before moving on.

---

### Task 4: Style Audit Cards

**Files:**
- Modify: `src/dev_agent/web/static/styles.css`
- Test: `tests/test_web_server.py::test_static_assets_include_console_interactions`

- [ ] **Step 1: Add audit card styles**

In `src/dev_agent/web/static/styles.css`, insert this block after the existing `.truncation-note` rule and before `.danger`:

```css
.audit-card-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.audit-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.52);
  box-shadow: 0 12px 28px rgba(31, 45, 33, 0.08);
}

.audit-card.audit-success {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.74);
}

.audit-card.audit-failed {
  border-color: rgba(154, 55, 45, 0.36);
  background: rgba(255, 238, 232, 0.86);
}

.audit-card.audit-neutral {
  border-color: rgba(64, 112, 111, 0.28);
  background: rgba(244, 248, 248, 0.72);
}

.audit-card.risk-create {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.68);
}

.audit-card.risk-overwrite {
  border-color: rgba(201, 112, 74, 0.46);
  background: rgba(255, 244, 232, 0.84);
}

.audit-card.risk-append,
.audit-card.risk-append-create {
  border-color: rgba(64, 112, 111, 0.34);
  background: rgba(235, 247, 244, 0.72);
}

.audit-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.audit-card-header h4 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.audit-status-badge {
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

.audit-status-badge.audit-success {
  color: #2f5b2d;
  background: rgba(229, 244, 218, 0.9);
}

.audit-status-badge.audit-failed {
  color: #7a251d;
  background: rgba(255, 223, 216, 0.95);
}

.audit-status-badge.audit-neutral {
  color: #285f5a;
  background: rgba(222, 244, 240, 0.95);
}

.audit-meta,
.audit-error {
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.55;
}

.audit-meta {
  margin: 8px 0 0;
}

.audit-error {
  margin-top: 10px;
  border-radius: 12px;
  padding: 9px 10px;
  color: #7a251d;
  background: rgba(255, 238, 232, 0.86);
}

.audit-diff {
  min-height: auto;
  margin-top: 10px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
```

- [ ] **Step 2: Make audit headers stack on mobile**

In the existing `@media (max-width: 860px)` block, replace:

```css
  .preview-card-header {
    flex-direction: column;
  }
```

with:

```css
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

- [ ] **Step 4: Commit frontend audit card rendering**

Run:

```powershell
git add tests/test_web_server.py src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css
git commit -m "feat: render web apply audit cards"
```

Expected: commit succeeds.

---

### Task 5: Full Verification and Smoke

**Files:**
- No source changes expected.
- Test: full local suite and web server check.

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
git log --oneline -6
```

Expected: working tree is clean, and recent commits include `docs: design web audit cards` and `feat: render web apply audit cards`.

---

## Plan Self-Review

**Spec coverage:** The plan covers the result-first audit container, success/failure summary, applied changes, preview content reuse, diff stat card, raw JSON retention, stale-state clearing, textContent safety, responsive CSS, local fake-provider-only testing, and full verification.

**Placeholder scan:** The plan contains no `TBD`, no `TODO`, no incomplete placeholder sections, and no implementation steps that defer behavior to future work.

**Type consistency:** The plan consistently uses existing payload names `applied_changes`, `preview_changes`, `diff_stat`, `execution_error`, existing functions `submitProviderPreview`, `submitProviderApply`, `resetProviderPreview`, `providerRiskLabel`, `providerRiskClass`, and new functions `providerAuditCards`, `clearProviderAuditCards`, `renderProviderAuditCards`, `renderProviderAuditFailure`.

**Scope control:** The plan does not add routes, real provider calls, supplier probing, background agents, complete diff generation, old-file reads, new dependencies, or destructive Git behavior.
