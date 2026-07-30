# Export Filter Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在“导出筛选 CSV”附近展示当前将被应用到筛选导出的条件提示，降低运营人员误导出的风险。

**Architecture:** 采用轻量前端增强：模板提供只读提示容器，`app.js` 读取现有筛选控件和运营概览时间范围并更新文案，CSS 复用当前筛选栏视觉体系。后端导出接口、CSV 字段、URL 参数语义和 JSONL 存储保持不变。

**Tech Stack:** FastAPI + Jinja2 模板、原生 JavaScript、CSS、pytest + TestClient 静态资源断言。

---

## File Structure

- `tests/test_app.py`：扩展现有 HTML、静态 JS、静态 CSS 测试，先锁定导出筛选提示区和更新钩子。
- `src/customer_issue_agent/templates/index.html`：在最近记录筛选表单中新增 `#export-filter-summary` 只读提示。
- `src/customer_issue_agent/static/app.js`：新增 `updateExportFilterSummary()`，并在筛选输入、重置、时间范围切换和初始化时调用。
- `src/customer_issue_agent/static/styles.css`：为 `.export-filter-summary` 增加轻量样式，跟随现有 `.filter-count` 风格。
- `README.md`：补充筛选导出前会展示当前导出条件。

## Task 1: Add Export Summary Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write the failing HTML test**

Update `tests/test_app.py::test_index_contains_recent_record_filter_controls` by appending these assertions after the existing `data-filter-reset` assertion:

```python
    assert 'id="export-filter-summary"' in html
    assert 'class="export-filter-summary"' in html
    assert 'aria-live="polite"' in html
    assert "将导出全部记录" in html
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: FAIL because `id="export-filter-summary"` is not present in the rendered HTML.

- [ ] **Step 3: Add the minimal template markup**

In `src/customer_issue_agent/templates/index.html`, inside `<form id="record-filter" ...>`, add the summary paragraph after the `导出筛选 CSV` and `清空` buttons and before `#filter-count`:

```html
            <button class="secondary-action" type="button" data-filter-export>导出筛选 CSV</button>
            <button class="secondary-action" type="button" data-filter-reset>清空</button>
            <p id="export-filter-summary" class="export-filter-summary" aria-live="polite">将导出全部记录</p>
            <p id="filter-count" class="filter-count" aria-live="polite">当前显示 {{ records|length }} / {{ records|length }} 条</p>
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
git commit -m "feat: add export filter summary markup"
```

## Task 2: Add Export Summary JavaScript Behavior

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write the failing JS hook tests**

Update `tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks` by appending:

```python
    assert "updateExportFilterSummary" in script
    assert "export-filter-summary" in script
    assert "将导出全部记录" in script
    assert "筛选导出将应用" in script
    assert "updateExportFilterSummary();" in script
```

Update `tests/test_app.py::test_static_app_js_contains_summary_range_hooks` by appending:

```python
    assert "updateExportFilterSummary();" in script
```

Update `tests/test_app.py::test_static_app_js_contains_filtered_export_hooks` by appending:

```python
    assert "时间" in script
    assert "最近 7 天" in script
    assert "最近 30 天" in script
```

- [ ] **Step 2: Run the JS hook tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
```

Expected: FAIL because `updateExportFilterSummary` and its user-facing strings are not in `app.js`.

- [ ] **Step 3: Add range label helper and summary updater**

In `src/customer_issue_agent/static/app.js`, add these functions after `buildFilteredExportUrl()` and before `bindPlatformSummaryDrilldown()`:

```javascript
function exportRangeLabel(value) {
  const rangeLabels = {
    all: "全部记录",
    "7d": "最近 7 天",
    "30d": "最近 30 天",
  };
  return rangeLabels[value] || rangeLabels.all;
}

function updateExportFilterSummary() {
  const summary = document.getElementById("export-filter-summary");
  if (!summary) {
    return;
  }

  const query = document.getElementById("record-search")?.value.trim() || "";
  const platform = document.getElementById("platform-filter")?.value.trim() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";
  const range = document.getElementById("summary-range")?.value || "all";
  const conditions = [];

  if (platform) {
    conditions.push(`平台：${platform}`);
  }
  if (query) {
    conditions.push(`关键词：${query}`);
  }
  if (issue) {
    conditions.push(`问题类型：${labelFor("issue", issue)}`);
  }
  if (responsibility) {
    conditions.push(`责任方：${labelFor("responsibility", responsibility)}`);
  }
  if (feedback) {
    conditions.push(`复核状态：${labelFor("feedback", feedback)}`);
  }
  if (range !== "all") {
    conditions.push(`时间：${exportRangeLabel(range)}`);
  }

  summary.textContent = conditions.length
    ? `筛选导出将应用：${conditions.join("；")}`
    : "将导出全部记录";
}
```

- [ ] **Step 4: Wire the updater into existing events**

In `src/customer_issue_agent/static/app.js`, update `bindSummaryRange()`:

```javascript
  select.addEventListener("change", () => {
    loadRecordsSummary();
    updateExportFilterSummary();
  });
```

Update `bindRecordFilters()`:

```javascript
  form.addEventListener("input", () => {
    applyRecordFilters();
    updateExportFilterSummary();
  });
  form.addEventListener("change", () => {
    applyRecordFilters();
    updateExportFilterSummary();
  });
```

Update `resetRecordFilters(form)`:

```javascript
function resetRecordFilters(form) {
  form.reset();
  applyRecordFilters();
  updateExportFilterSummary();
}
```

The existing `bindRecordFilters()` already calls `applyRecordFilters()` during page initialization; after this task it can also call `updateExportFilterSummary()` explicitly at the end:

```javascript
  applyRecordFilters();
  updateExportFilterSummary();
```

- [ ] **Step 5: Run the JS hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
```

Expected: PASS.

- [ ] **Step 6: Commit JavaScript behavior**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/static/app.js
git commit -m "feat: summarize filtered export conditions"
```

## Task 3: Style the Export Summary Hint

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write the failing CSS hook test**

Update `tests/test_app.py::test_styles_cover_recent_record_filter_components` by appending:

```python
    assert ".export-filter-summary" in css
```

- [ ] **Step 2: Run the focused CSS test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: FAIL because `.export-filter-summary` is not present in `styles.css`.

- [ ] **Step 3: Add the CSS style**

In `src/customer_issue_agent/static/styles.css`, update the shared text style selector:

```css
.filter-field span,
.filter-count,
.export-filter-summary {
  color: var(--muted);
  font-size: 13px;
}
```

Then add a dedicated block after `.filter-count`:

```css
.export-filter-summary {
  grid-column: 1 / -1;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.7);
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
git commit -m "style: present export filter summary"
```

## Task 4: Document and Verify

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

In `README.md` under `## 导出分析记录`, replace the paragraph:

```markdown
如果只想导出某一组记录，可以先在“最近记录”筛选栏设置关键词、问题类型、责任方或复核状态，然后点击 `导出筛选 CSV`。筛选导出由服务端基于全部本地 JSONL 记录执行，不限于页面当前展示的最近 10 条；原有 `导出 CSV` 仍始终导出全部记录。
```

With:

```markdown
如果只想导出某一组记录，可以先在“最近记录”筛选栏设置平台、关键词、问题类型、责任方或复核状态，然后点击 `导出筛选 CSV`。按钮附近会先显示本次筛选导出将应用的条件；筛选导出由服务端基于全部本地 JSONL 记录执行，不限于页面当前展示的最近 10 条。原有 `导出 CSV` 仍始终导出全部记录。
```

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: PASS, with all existing tests and the new hook assertions passing.

- [ ] **Step 3: Review the diff for accidental scope creep**

Run:

```powershell
git diff -- src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js src/customer_issue_agent/static/styles.css tests/test_app.py README.md
```

Expected: Diff only contains the export filter summary hint, tests, CSS, and README wording. No backend endpoint, CSV, JSONL storage, model-provider, or unrelated old-repo changes are present.

- [ ] **Step 4: Commit documentation**

Run:

```powershell
git add README.md
git commit -m "docs: describe export filter summary"
```

- [ ] **Step 5: Final verification before push**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
python -m pytest -q
gh pr view 2 --repo ARIUM-hub/Agent-Operations-Workflow --json number,state,headRefName,url,title
git log --oneline -5
```

Expected:

```text
## codex/customer-issue-agent-mvp
```

`python -m pytest -q` passes, PR #2 is open on `codex/customer-issue-agent-mvp`, and recent commits include the plan plus the export filter summary implementation commits.

- [ ] **Step 6: Push the branch**

Run:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: Push succeeds and PR #2 updates.

## Self-Review

- Spec coverage: Task 1 adds `#export-filter-summary` markup with `aria-live="polite"` and default text. Task 2 covers platform, keyword, issue, responsibility, feedback, time range labels, page init, input/change, reset, and summary range change. Task 3 covers styling. Task 4 covers README, full verification, scope diff, and push.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, vague “add tests” steps, or “similar to” shortcuts remain. Each code-changing step includes exact snippets and commands.
- Type and name consistency: The plan consistently uses `updateExportFilterSummary`, `exportRangeLabel`, `export-filter-summary`, existing `labelFor(group, value)`, and existing DOM IDs `platform-filter`, `record-search`, `issue-filter`, `responsibility-filter`, `feedback-filter`, and `summary-range`.
