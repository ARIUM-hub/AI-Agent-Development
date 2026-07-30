# Record Detail Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a “复制详情” action to each recent record detail so operators can copy a structured plain-text summary for tickets, docs, or review chats.

**Architecture:** Keep the feature entirely in the existing front-end workbench. Add copy controls to both server-rendered recent-record details and JavaScript-generated details, then bind copy buttons to a DOM-based text builder that reads the current `.record` attributes and `.record-detail-grid` rows.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, vanilla JavaScript Clipboard API, CSS, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-30-record-detail-copy-design.md`

## Scope Check

This plan implements only front-end record-detail copying. It does not add backend APIs, alter JSONL storage, change analysis, batch, feedback, CSV export, summary aggregation, or call model providers.

## File Structure

- Modify: `tests/test_app.py`
  - Extend existing detail HTML tests for copy controls.
  - Extend existing detail JavaScript hook tests for copy binding, text building, Clipboard API, and newly appended record binding.
  - Extend existing detail CSS hook tests for copy action and status styling.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add `复制详情` button and status region to server-rendered record details.
- Modify: `src/customer_issue_agent/static/app.js`
  - Add copy controls to `recordDetailHtml()`.
  - Bind copy controls on DOMContentLoaded and after `prependRecentRecord()`.
  - Generate plain text from current DOM detail rows.
  - Use `navigator.clipboard.writeText()` with success and failure status messages.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Style copy action and status text.
- Modify: `README.md`
  - Document that expanded record details can be copied.

## Task 1: Copy Controls In Record Detail Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing markup tests**

Modify `test_recent_records_include_expandable_detail_markup` in `tests/test_app.py` by adding:

```python
assert "复制详情" in html
assert "data-record-copy" in html
assert "data-record-copy-status" in html
assert 'aria-live="polite"' in html
```

Modify `test_static_app_js_contains_record_detail_hooks` in `tests/test_app.py` by adding:

```python
assert "data-record-copy" in script
assert "data-record-copy-status" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_recent_records_include_expandable_detail_markup tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: FAIL because neither the server-rendered detail markup nor `recordDetailHtml()` includes copy controls.

- [ ] **Step 3: Add copy controls to server-rendered details**

Modify `src/customer_issue_agent/templates/index.html` inside each server-rendered `<div id="record-detail-{{ record.id }}" class="record-detail" hidden>`, immediately before `<dl class="record-detail-grid">`:

```html
                    <button class="record-copy-action secondary-action" type="button" data-record-copy>复制详情</button>
                    <p class="record-copy-status" data-record-copy-status aria-live="polite"></p>
```

- [ ] **Step 4: Add copy controls to JavaScript-generated details**

Modify `recordDetailHtml(recordId, analysis, feedback = null)` in `src/customer_issue_agent/static/app.js` so the generated detail `<div>` begins with:

```javascript
      <button class="record-copy-action secondary-action" type="button" data-record-copy>复制详情</button>
      <p class="record-copy-status" data-record-copy-status aria-live="polite"></p>
      <dl class="record-detail-grid">
```

The resulting block should keep all existing detail rows unchanged after the new controls.

- [ ] **Step 5: Run markup tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_recent_records_include_expandable_detail_markup tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: add record detail copy controls"
```

## Task 2: Copy Behavior

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing JavaScript behavior hook tests**

Modify `test_static_app_js_contains_record_detail_hooks` in `tests/test_app.py` by adding:

```python
assert "bindRecordCopyActions" in script
assert "copyRecordDetails" in script
assert "buildRecordDetailCopyText" in script
assert "navigator.clipboard.writeText" in script
assert "已复制详情" in script
assert "复制失败，请手动选择详情文本" in script
assert "bindRecordCopyActions(article)" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: FAIL because copy binding, copy text generation, Clipboard API calls, and new-record binding do not exist.

- [ ] **Step 3: Bind copy actions on page load and new records**

Modify the DOMContentLoaded callback in `src/customer_issue_agent/static/app.js` by adding this after `bindRecordDetails(document);`:

```javascript
  bindRecordCopyActions(document);
```

Modify `prependRecentRecord(payload)` by adding this after `bindRecordDetails(article);`:

```javascript
  bindRecordCopyActions(article);
```

- [ ] **Step 4: Add copy behavior functions**

Add these functions after `toggleRecordDetail(button)` and before `recordDetailHtml(...)` in `src/customer_issue_agent/static/app.js`:

```javascript
function bindRecordCopyActions(root = document) {
  root.querySelectorAll("[data-record-copy]").forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.dataset.bound = "true";
    button.addEventListener("click", () => copyRecordDetails(button));
  });
}

async function copyRecordDetails(button) {
  const record = button.closest(".record");
  const status = record?.querySelector("[data-record-copy-status]") || null;
  const text = record ? buildRecordDetailCopyText(record) : "";
  if (!text || !navigator.clipboard || !navigator.clipboard.writeText) {
    setRecordCopyStatus(status, "复制失败，请手动选择详情文本", false);
    return;
  }

  try {
    await navigator.clipboard.writeText(text);
    setRecordCopyStatus(status, "已复制详情", true);
  } catch (error) {
    setRecordCopyStatus(status, "复制失败，请手动选择详情文本", false);
  }
}

function buildRecordDetailCopyText(record) {
  const lines = [
    `平台：${record.dataset.platform || "暂无信息"}`,
    `记录 ID：${record.dataset.recordId || "暂无信息"}`,
  ];
  record.querySelectorAll(".record-detail-grid div").forEach((row) => {
    const label = row.querySelector("dt")?.textContent.trim();
    const value = row.querySelector("dd")?.textContent.trim() || "暂无信息";
    if (label) {
      lines.push(`${label}：${value}`);
    }
  });
  return lines.join("\n");
}

function setRecordCopyStatus(status, message, success) {
  if (!status) {
    return;
  }
  status.textContent = message;
  status.classList.toggle("is-success", success);
  status.classList.toggle("is-error", !success);
}
```

- [ ] **Step 5: Run JavaScript behavior hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: selected test passes.

- [ ] **Step 6: Run app tests**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py -q
```

Expected: all app tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: copy record details to clipboard"
```

## Task 3: Copy Styles

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write failing CSS hook test**

Modify `test_styles_cover_record_detail_components` in `tests/test_app.py` by adding:

```python
assert ".record-copy-action" in css
assert ".record-copy-status" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_record_detail_components -q
```

Expected: FAIL because `styles.css` does not yet define copy action or copy status styles.

- [ ] **Step 3: Add copy styles**

Add this CSS after `.record-detail` in `src/customer_issue_agent/static/styles.css`:

```css
.record-copy-action {
  margin-bottom: 12px;
}

.record-copy-status {
  min-height: 20px;
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 13px;
}

.record-copy-status.is-success {
  color: var(--accent);
}

.record-copy-status.is-error {
  color: #b42318;
}
```

- [ ] **Step 4: Run CSS hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_record_detail_components -q
```

Expected: selected test passes.

- [ ] **Step 5: Run app tests**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py -q
```

Expected: all app tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "style: add record detail copy feedback"
```

## Task 4: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README detail copy docs**

Modify the “筛选最近记录” section in `README.md` by changing:

```markdown
每条最近记录都可以点击 `查看详情` 展开结构化明细，包括客户问题、业务原因、下一步建议、需要补充信息以及人工复核备注。详情展开只影响页面显示，不会修改记录内容。
```

To:

```markdown
每条最近记录都可以点击 `查看详情` 展开结构化明细，包括客户问题、业务原因、下一步建议、需要补充信息以及人工复核备注。展开后可以点击 `复制详情`，把平台、记录 ID 和结构化明细复制为纯文本，方便贴到客服工单或复盘文档；详情展开和复制都只影响页面显示，不会修改记录内容。
```

- [ ] **Step 2: Run full automated verification**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Check worktree status**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
```

Expected: only `README.md` is modified before commit.

- [ ] **Step 4: Commit**

Run:

```powershell
git add README.md
git commit -m "docs: document record detail copy"
```

## Final Verification

- [ ] Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: all tests pass.

- [ ] Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
```

Expected: clean worktree on `codex/customer-issue-agent-mvp`.

- [ ] Push to target repository:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: push succeeds and updates the existing open PR in `ARIUM-hub/Agent-Operations-Workflow`.

## Self-Review Checklist

- Spec coverage: copy controls, server-rendered records, JavaScript-generated records, page-load binding, new-record binding, Clipboard API success, Clipboard API failure, plain-text detail generation, styles, README docs, and full regression verification are covered.
- Deferred items: backend APIs, JSONL changes, CSV changes, rich text, Markdown tables, original conversation copy, custom copy templates, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `data-record-copy`, `data-record-copy-status`, `record-copy-action`, `record-copy-status`, `bindRecordCopyActions`, `copyRecordDetails`, `buildRecordDetailCopyText`, and `setRecordCopyStatus` are named consistently across tests, implementation, and documentation.
