# Web Preview Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render provider plan preview changes as human-readable risk-first cards in the Web approval panel while keeping raw JSON available.

**Architecture:** This is a static Web UI enhancement only. Existing provider plan preview/apply APIs continue returning JSON; `src/dev_agent/web/static/app.js` transforms `preview_changes` into safe DOM nodes using `textContent`, and `styles.css` adds responsive card styling that matches the current paper/moss/clay visual system.

**Tech Stack:** Python 3.13, pytest, static HTML/CSS/JavaScript, built-in HTTP server tests, no frontend build tools.

---

## File Structure

- Modify: `tests/test_web_server.py`
  - Extend `test_static_assets_include_console_interactions` to assert preview card container, renderer helpers, state clearing calls, and CSS classes exist.
- Modify: `src/dev_agent/web/static/index.html`
  - Add `provider-preview-cards` container before raw preview JSON.
  - Add a small raw JSON label for clarity.
- Modify: `src/dev_agent/web/static/app.js`
  - Add DOM getter and helper functions for safe card rendering.
  - Render cards after preview success.
  - Clear cards on preview failure, input changes, apply success, and apply failure.
- Modify: `src/dev_agent/web/static/styles.css`
  - Add risk-first card styles, semantic risk classes, truncation note, empty state, and mobile wrapping rules.

## Task 1: Add Failing Static Asset Contract Tests

**Files:**
- Modify: `tests/test_web_server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Extend static resource assertions**

In `tests/test_web_server.py::test_static_assets_include_console_interactions`, add these assertions after the existing Provider plan form assertions:

```python
    assert "provider-preview-cards" in index_body
    assert "原始 JSON" in index_body
```

Add these CSS assertions after the existing `.danger` assertion:

```python
    assert ".preview-card-list" in css_body
    assert ".preview-card" in css_body
    assert ".risk-badge" in css_body
    assert ".risk-overwrite" in css_body
    assert ".content-preview" in css_body
    assert ".truncation-note" in css_body
    assert "overflow-wrap: anywhere" in css_body
```

Add these JS assertions after the existing reset/provider endpoint assertions:

```python
    assert "providerPreviewCards" in js_body
    assert "renderProviderPreviewCards" in js_body
    assert "clearProviderPreviewCards" in js_body
    assert "providerRiskLabel" in js_body
    assert "providerRiskClass" in js_body
    assert "content_preview_truncated" in js_body
    assert "textContent" in js_body
```

- [ ] **Step 2: Run the focused static asset test to verify it fails**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because `provider-preview-cards`, card CSS classes, and render helper functions do not exist yet.

## Task 2: Add HTML Container and Raw JSON Label

**Files:**
- Modify: `src/dev_agent/web/static/index.html`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add preview card container**

In `src/dev_agent/web/static/index.html`, replace the right side of the Provider plan approval panel:

```html
                <h3>审批状态</h3>
                <p id="provider-status" class="status-pill">等待预览</p>
                <pre id="provider-preview-result" aria-live="polite">等待 provider plan 预览...</pre>
                <pre id="provider-apply-result" aria-live="polite">确认执行后显示结果。</pre>
                <p id="provider-error" class="danger" role="alert" hidden></p>
```

with:

```html
                <h3>审批状态</h3>
                <p id="provider-status" class="status-pill">等待预览</p>
                <div id="provider-preview-cards" class="preview-card-list" aria-live="polite"></div>
                <h4 class="result-heading">原始 JSON</h4>
                <pre id="provider-preview-result" aria-live="polite">等待 provider plan 预览...</pre>
                <h4 class="result-heading">执行结果</h4>
                <pre id="provider-apply-result" aria-live="polite">确认执行后显示结果。</pre>
                <p id="provider-error" class="danger" role="alert" hidden></p>
```

- [ ] **Step 2: Run the focused static asset test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: still FAIL because JS helpers and CSS classes are not implemented yet.

## Task 3: Add Safe Preview Card Rendering

**Files:**
- Modify: `src/dev_agent/web/static/app.js`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add DOM getter and risk helpers**

In `src/dev_agent/web/static/app.js`, add this near the existing provider DOM getters:

```javascript
const providerPreviewCards = () => document.getElementById("provider-preview-cards");

const providerRiskLabel = (risk) => {
  if (risk === "create") {
    return "新建";
  }
  if (risk === "overwrite") {
    return "覆盖";
  }
  if (risk === "append") {
    return "追加";
  }
  if (risk === "append_create") {
    return "追加并创建";
  }
  return risk || "未知风险";
};

const providerRiskClass = (risk) => {
  if (risk === "create") {
    return "risk-create";
  }
  if (risk === "overwrite") {
    return "risk-overwrite";
  }
  if (risk === "append") {
    return "risk-append";
  }
  if (risk === "append_create") {
    return "risk-append-create";
  }
  return "risk-unknown";
};
```

- [ ] **Step 2: Add card rendering helpers**

Add these functions after `clearProviderError()`:

```javascript
const clearProviderPreviewCards = () => {
  providerPreviewCards().replaceChildren();
};

const appendText = (parent, className, text) => {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
};

const renderProviderPreviewCards = (payload) => {
  clearProviderPreviewCards();
  const changes = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  if (changes.length === 0) {
    appendText(providerPreviewCards(), "preview-empty-state", "没有可显示的预览变更。");
    return;
  }

  changes.forEach((change) => {
    const riskClass = providerRiskClass(change.risk);
    const card = document.createElement("article");
    card.className = `preview-card ${riskClass}`;

    const header = document.createElement("div");
    header.className = "preview-card-header";
    const path = document.createElement("h4");
    path.textContent = change.path || "未命名路径";
    const badge = document.createElement("span");
    badge.className = `risk-badge ${riskClass}`;
    badge.textContent = providerRiskLabel(change.risk);
    header.append(path, badge);

    const meta = document.createElement("p");
    meta.className = "preview-meta";
    const targetState = change.exists ? "目标已存在" : "目标不存在";
    const bytes = Number.isFinite(change.content_bytes) ? `${change.content_bytes} bytes` : "未知 bytes";
    const lines = Number.isFinite(change.content_preview_line_count)
      ? `原始内容 ${change.content_preview_line_count} 行`
      : "行数未知";
    meta.textContent = `${targetState} · 将写入 ${bytes} · ${lines}`;

    const previewLabel = document.createElement("div");
    previewLabel.className = "preview-content-label";
    previewLabel.textContent = "内容预览";

    const preview = document.createElement("pre");
    preview.className = "content-preview";
    if (typeof change.content_preview === "string") {
      preview.textContent = change.content_preview === "" ? "内容为空" : change.content_preview;
    } else {
      preview.textContent = "此预览没有内容片段字段，请重新生成预览或检查服务版本。";
    }

    card.append(header, meta, previewLabel, preview);
    if (change.content_preview_truncated === true) {
      appendText(card, "truncation-note", "内容已截断，请查看原始 JSON 或缩小计划内容后重新预览。");
    }
    providerPreviewCards().appendChild(card);
  });
};
```

- [ ] **Step 3: Wire card rendering into preview/apply states**

Update `resetProviderPreview()` so it clears cards before returning:

```javascript
const resetProviderPreview = () => {
  if (lastProviderPreview === null) {
    return;
  }
  clearProviderPreviewCards();
  lastProviderPreview = null;
  providerStatus().textContent = "内容已变化，需要重新预览";
  providerApplyButton().disabled = true;
};
```

Update `submitProviderPreview()`:

```javascript
  clearProviderError();
  clearProviderPreviewCards();
  lastProviderPreview = null;
```

Inside preview success, after `lastProviderPreview = payload;`, call:

```javascript
    renderProviderPreviewCards(payload);
```

Inside preview failure, before rendering failure JSON, call:

```javascript
    clearProviderPreviewCards();
```

Update `submitProviderApply()` so both success and failure clear stale cards:

```javascript
    clearProviderPreviewCards();
    lastProviderPreview = null;
```

Use that pair in the success block after `providerStatus().textContent = ...`, and in the catch block before `showProviderError(error.message);`.

- [ ] **Step 4: Run the focused static asset test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: still FAIL because CSS classes are not implemented yet.

## Task 4: Add Risk-First Card Styling

**Files:**
- Modify: `src/dev_agent/web/static/styles.css`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add preview card CSS**

In `src/dev_agent/web/static/styles.css`, add this before `.danger`:

```css
.result-heading {
  margin: 16px 0 0;
  color: var(--muted);
  font-size: 0.82rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.preview-card-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.preview-empty-state,
.preview-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.52);
}

.preview-empty-state {
  padding: 14px;
  color: var(--muted);
  line-height: 1.6;
}

.preview-card {
  padding: 14px;
  box-shadow: 0 12px 28px rgba(31, 45, 33, 0.08);
}

.preview-card.risk-create {
  border-color: rgba(82, 107, 74, 0.34);
  background: rgba(238, 247, 231, 0.74);
}

.preview-card.risk-overwrite {
  border-color: rgba(201, 112, 74, 0.46);
  background: rgba(255, 244, 232, 0.86);
}

.preview-card.risk-append,
.preview-card.risk-append-create {
  border-color: rgba(64, 112, 111, 0.34);
  background: rgba(235, 247, 244, 0.76);
}

.preview-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.preview-card-header h4 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.risk-badge {
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

.risk-badge.risk-create {
  color: #2f5b2d;
  background: rgba(229, 244, 218, 0.9);
}

.risk-badge.risk-overwrite {
  color: #8b3f1e;
  background: rgba(255, 232, 211, 0.95);
}

.risk-badge.risk-append,
.risk-badge.risk-append-create {
  color: #285f5a;
  background: rgba(222, 244, 240, 0.95);
}

.preview-meta,
.preview-content-label,
.truncation-note {
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.55;
}

.preview-meta {
  margin: 8px 0 0;
}

.preview-content-label {
  margin-top: 10px;
  font-weight: 800;
}

.content-preview {
  min-height: auto;
  margin-top: 6px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.truncation-note {
  margin-top: 10px;
  border-radius: 12px;
  padding: 9px 10px;
  color: #7a4a18;
  background: rgba(255, 244, 214, 0.88);
}
```

- [ ] **Step 2: Add narrow-screen wrapping**

Inside the existing `@media (max-width: 860px)` block, add:

```css
  .preview-card-header {
    flex-direction: column;
  }

  .risk-badge {
    white-space: normal;
  }
```

- [ ] **Step 3: Run the focused static asset test**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: PASS.

- [ ] **Step 4: Commit Web card implementation**

Run:

```powershell
git add -- tests/test_web_server.py src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css
git commit -m "feat: render provider preview cards"
```

## Task 5: Verification and Smoke

**Files:**
- Verify: entire repository.

- [ ] **Step 1: Run Web server tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_server.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: PASS with all tests passing.

- [ ] **Step 3: Run CLI serve smoke using current source tree**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m dev_agent.cli serve --port 0 --check
```

Expected: command exits `0` and returns JSON containing `ok: true` and a local URL.

- [ ] **Step 4: Inspect final status**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected: working tree is clean on `codex/dev-agent-web-preview-cards`, with the implementation commit above the design/plan commits.

## Self-Review Checklist

- Spec coverage: Tasks cover card container, raw JSON preservation, risk labels/classes, safe `textContent` rendering, stale-card clearing, preview failure, apply success/failure, responsive wrapping, and no backend/API changes.
- Placeholder scan: The plan contains exact paths, code snippets, commands, and expected outcomes.
- Type consistency: Helper names are consistently `providerPreviewCards`, `clearProviderPreviewCards`, `renderProviderPreviewCards`, `providerRiskLabel`, and `providerRiskClass`; CSS classes match the spec.
