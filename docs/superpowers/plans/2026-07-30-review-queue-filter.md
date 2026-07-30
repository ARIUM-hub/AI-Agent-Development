# Review Queue Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在“最近记录”筛选区增加 `只看待复核` 快捷按钮，让运营人员一键筛出未复核客户问题。

**Architecture:** 不新增后端接口，复用现有 `#feedback-filter` 的 `unreviewed` 值和本地筛选逻辑。前端新增快捷按钮绑定、激活态与待复核数量统计，并抽出统一刷新函数，确保列表筛选、导出条件提示、真实导出数量预估和快捷按钮状态同步更新。

**Tech Stack:** FastAPI + Jinja2 模板、原生 JavaScript、CSS、pytest + TestClient 静态资源断言。

---

## File Structure

- `tests/test_app.py`：扩展首页 HTML、静态 JS、静态 CSS hook 测试，覆盖快捷按钮、激活态、切换逻辑和统一刷新函数。
- `src/customer_issue_agent/templates/index.html`：在最近记录筛选表单中新增 `data-review-queue-toggle` 按钮。
- `src/customer_issue_agent/static/app.js`：新增 `bindReviewQueueToggle()`、`toggleReviewQueueFilter()`、`updateReviewQueueToggle()` 和 `refreshRecordFilterViews()`，并接入现有筛选刷新点。
- `src/customer_issue_agent/static/styles.css`：新增 `.review-queue-toggle` 与 `.review-queue-toggle.is-active` 样式。
- `README.md`：补充 `只看待复核` 快捷入口说明。

## Task 1: Add Review Queue Toggle Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write the failing HTML test**

Update `tests/test_app.py::test_index_contains_recent_record_filter_controls` by appending these assertions after the existing `feedback-filter` assertion or near the other filter control assertions:

```python
    assert "只看待复核" in html
    assert 'data-review-queue-toggle' in html
    assert 'class="secondary-action review-queue-toggle"' in html
    assert 'aria-pressed="false"' in html
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: FAIL because `data-review-queue-toggle` and `只看待复核` are not present in the rendered HTML.

- [ ] **Step 3: Add the minimal template markup**

In `src/customer_issue_agent/templates/index.html`, inside `<form id="record-filter" ...>`, add the button after the `复核状态` field and before `导出筛选 CSV`:

```html
            <button class="secondary-action review-queue-toggle" type="button" data-review-queue-toggle aria-pressed="false">只看待复核（0）</button>
            <button class="secondary-action" type="button" data-filter-export>导出筛选 CSV</button>
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: PASS.

- [ ] **Step 5: Commit markup**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/templates/index.html
git commit -m "feat: add review queue filter toggle"
```

## Task 2: Add Review Queue Toggle Behavior

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write the failing JS hook tests**

Update `tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks` by appending:

```python
    assert "bindReviewQueueToggle" in script
    assert "toggleReviewQueueFilter" in script
    assert "updateReviewQueueToggle" in script
    assert "refreshRecordFilterViews" in script
    assert "data-review-queue-toggle" in script
    assert 'feedbackFilter.value = "unreviewed"' in script
    assert 'feedbackFilter.value = ""' in script
    assert 'aria-pressed' in script
    assert "is-active" in script
    assert "只看待复核" in script
    assert 'data-feedback-status="unreviewed"' in script
```

Update `tests/test_app.py::test_static_app_js_contains_summary_range_hooks` by appending:

```python
    assert "refreshRecordFilterViews();" in script
```

- [ ] **Step 2: Run the JS hook tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
```

Expected: FAIL because the review queue toggle functions and strings do not exist yet.

- [ ] **Step 3: Bind the review queue toggle on page load**

In `src/customer_issue_agent/static/app.js`, update the `DOMContentLoaded` handler by adding `bindReviewQueueToggle();` after `bindRecordFilters();`:

```javascript
  bindFilteredExport();
  bindRecordFilters();
  bindReviewQueueToggle();
  bindRecordDetails(document);
```

- [ ] **Step 4: Add a unified filter refresh function**

In `src/customer_issue_agent/static/app.js`, add this function before `bindRecordFilters()`:

```javascript
function refreshRecordFilterViews() {
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
  updateReviewQueueToggle();
}
```

- [ ] **Step 5: Use the unified refresh in existing filter paths**

In `applySummaryPlatformFilter(platform)`, replace:

```javascript
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
```

With:

```javascript
  refreshRecordFilterViews();
```

In `prependRecentRecord(payload)`, replace:

```javascript
  applyRecordFilters();
```

With:

```javascript
  refreshRecordFilterViews();
```

In `bindRecordFilters()`, replace both input/change listeners and initialization:

```javascript
  form.addEventListener("input", () => {
    refreshRecordFilterViews();
  });
  form.addEventListener("change", () => {
    refreshRecordFilterViews();
  });
```

At the end of `bindRecordFilters()`, replace:

```javascript
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
```

With:

```javascript
  refreshRecordFilterViews();
```

In `resetRecordFilters(form)`, replace:

```javascript
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
```

With:

```javascript
  refreshRecordFilterViews();
```

In `bindSummaryRange()`, keep `loadRecordsSummary();`, then replace separate export hint calls with:

```javascript
    refreshRecordFilterViews();
```

- [ ] **Step 6: Add toggle behavior and state updater**

In `src/customer_issue_agent/static/app.js`, add these functions after `refreshRecordFilterViews()`:

```javascript
function bindReviewQueueToggle() {
  const button = document.querySelector("[data-review-queue-toggle]");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => toggleReviewQueueFilter());
  updateReviewQueueToggle();
}

function toggleReviewQueueFilter() {
  const feedbackFilter = document.getElementById("feedback-filter");
  if (!feedbackFilter) {
    return;
  }

  if (feedbackFilter.value === "unreviewed") {
    feedbackFilter.value = "";
  } else {
    feedbackFilter.value = "unreviewed";
  }
  refreshRecordFilterViews();
}

function updateReviewQueueToggle() {
  const button = document.querySelector("[data-review-queue-toggle]");
  if (!button) {
    return;
  }

  const feedbackFilter = document.getElementById("feedback-filter");
  const pendingCount = document.querySelectorAll('#recent-records .record[data-feedback-status="unreviewed"]').length;
  const active = feedbackFilter?.value === "unreviewed";
  button.textContent = `只看待复核（${pendingCount}）`;
  button.classList.toggle("is-active", active);
  button.setAttribute("aria-pressed", String(active));
}
```

- [ ] **Step 7: Run the JS hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
```

Expected: PASS.

- [ ] **Step 8: Commit JavaScript behavior**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/static/app.js
git commit -m "feat: wire review queue filter toggle"
```

## Task 3: Style the Review Queue Toggle

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write the failing CSS hook test**

Update `tests/test_app.py::test_styles_cover_recent_record_filter_components` by appending:

```python
    assert ".review-queue-toggle" in css
    assert ".review-queue-toggle.is-active" in css
```

- [ ] **Step 2: Run the focused CSS test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: FAIL because `.review-queue-toggle` is not present in `styles.css`.

- [ ] **Step 3: Add the CSS style**

In `src/customer_issue_agent/static/styles.css`, add these styles near the existing `.export-count-preview` or filter component styles:

```css
.review-queue-toggle {
  white-space: nowrap;
}

.review-queue-toggle.is-active {
  border-color: rgba(172, 92, 46, 0.55);
  background: rgba(172, 92, 46, 0.12);
  color: #8a3f20;
}
```

- [ ] **Step 4: Run the focused CSS test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: PASS.

- [ ] **Step 5: Commit CSS**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/static/styles.css
git commit -m "style: highlight review queue filter"
```

## Task 4: Document and Verify

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

In `README.md` under `## 批量分析与人工复核`, after the feedback bullet list, add:

```markdown
在“最近记录”区域可以点击 `只看待复核` 快速筛出当前页面中尚未人工确认的记录；该入口复用复核状态筛选，因此导出筛选条件提示和预计导出数量也会同步更新。
```

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: PASS with all existing tests plus the review queue filter hook assertions.

- [ ] **Step 3: Review the diff for accidental scope creep**

Run:

```powershell
git diff -- src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js src/customer_issue_agent/static/styles.css tests/test_app.py README.md
```

Expected: Diff only contains the review queue toggle, shared filter refresh wiring, tests, CSS, and README wording. No backend endpoint, CSV export behavior, JSONL storage, model-provider, old-repo, or unrelated file changes are present.

- [ ] **Step 4: Commit documentation**

Run:

```powershell
git add README.md
git commit -m "docs: describe review queue filter"
```

- [ ] **Step 5: Final verification before push**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
python -m pytest -q
gh pr view 2 --repo ARIUM-hub/Agent-Operations-Workflow --json number,state,headRefName,url,title
git log --oneline -8
```

Expected:

```text
## codex/customer-issue-agent-mvp
```

`python -m pytest -q` passes, PR #2 remains open on `codex/customer-issue-agent-mvp`, and recent commits include the review queue filter spec, plan, and implementation commits.

If unrelated untracked files are still present, do not stage or delete them. Mention them in the final response and only push committed review queue changes.

- [ ] **Step 6: Push the branch**

Run:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: Push succeeds and PR #2 updates.

## Self-Review

- Spec coverage: Task 1 adds the `只看待复核` button with `aria-pressed="false"`. Task 2 implements binding, toggle-on, toggle-off, active state, count display, shared refresh, reset behavior, platform drilldown refresh, page init, and newly prepended records. Task 3 covers active styling. Task 4 covers README, full verification, diff review, and push.
- Placeholder scan: The plan contains no unfinished requirement markers, vague implementation instructions, or references to undefined production functions. Each code-changing step includes exact snippets and commands.
- Type and name consistency: The plan consistently uses `bindReviewQueueToggle`, `toggleReviewQueueFilter`, `updateReviewQueueToggle`, `refreshRecordFilterViews`, `data-review-queue-toggle`, `review-queue-toggle`, `unreviewed`, and `#feedback-filter`.
