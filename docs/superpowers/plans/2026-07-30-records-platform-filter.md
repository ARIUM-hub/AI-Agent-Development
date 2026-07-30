# Records Platform Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a platform filter to the recent-records toolbar and filtered CSV export flow.

**Architecture:** Reuse the existing `platform-presets` datalist, recent record `data-platform` attributes, local JavaScript filtering, and server-side `filter_records(..., platform=...)` export support. This adds one front-end control and threads its value through local filtering plus `buildFilteredExportUrl()` without changing storage, analysis, feedback, or summary behavior.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, vanilla JavaScript, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-30-records-platform-filter-design.md`

## Scope Check

This plan implements only platform filtering for the existing recent-records UI and filtered CSV export URL. It does not add backend APIs, alter JSONL history, normalize platform aliases, change operations summary semantics, or call model providers.

## File Structure

- Modify: `tests/test_app.py`
  - Extend existing recent-record filter markup test to require `platform-filter`.
  - Extend existing static JS hook tests to require platform filtering and filtered export platform query support.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add a platform input to the existing `#record-filter` form.
  - Bind it to the existing shared `platform-presets` datalist.
- Modify: `src/customer_issue_agent/static/app.js`
  - Read `#platform-filter` in `applyRecordFilters()`.
  - Pass `platform` to `recordMatchesFilters()`.
  - Match platform case-insensitively with contains semantics.
  - Add `platform` to filtered CSV export URLs when present.
- Modify: `README.md`
  - Document platform filtering in the “筛选最近记录” section.

## Task 1: Platform Filter Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write failing markup test**

Modify `test_index_contains_recent_record_filter_controls` in `tests/test_app.py` by adding these assertions after the `record-search` assertion:

```python
assert 'id="platform-filter"' in html
assert 'name="platform"' in html
assert 'id="platform-filter" name="platform" list="platform-presets"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: FAIL because the recent-record filter form does not contain `platform-filter`.

- [ ] **Step 3: Add platform filter input**

Modify `src/customer_issue_agent/templates/index.html` inside `<form id="record-filter" ...>`, immediately after the keyword search field:

```html
            <label class="filter-field" for="platform-filter">
              <span>平台</span>
              <input id="platform-filter" name="platform" list="platform-presets" placeholder="全部平台">
            </label>
```

Keep the existing shared `<datalist id="platform-presets">` unchanged.

- [ ] **Step 4: Run markup test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: selected test passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html tests/test_app.py
git commit -m "feat: add platform filter control"
```

## Task 2: Platform Filter Behavior And Export URL

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing JavaScript hook tests**

Modify `test_static_app_js_contains_recent_record_filter_hooks` in `tests/test_app.py` by adding:

```python
assert "platform-filter" in script
assert "matchesPlatform" in script
assert "filters.platform" in script
```

Modify `test_static_app_js_contains_filtered_export_hooks` in `tests/test_app.py` by adding:

```python
assert "platform-filter" in script
assert 'params.set("platform", platform)' in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
```

Expected: FAIL because `app.js` does not read `platform-filter`, does not define `matchesPlatform`, and does not set the filtered export `platform` parameter.

- [ ] **Step 3: Add platform parameter to filtered export URL**

Modify `buildFilteredExportUrl()` in `src/customer_issue_agent/static/app.js`:

```javascript
  const platform = document.getElementById("platform-filter")?.value.trim() || "";
```

Place it after the existing `query` line.

Then add this block after the existing `if (query) { ... }` block and before issue category handling:

```javascript
  if (platform) {
    params.set("platform", platform);
  }
```

- [ ] **Step 4: Add platform matching to local filters**

Modify `applyRecordFilters()` in `src/customer_issue_agent/static/app.js`:

```javascript
  const platform = document.getElementById("platform-filter")?.value.trim().toLowerCase() || "";
```

Place it after the existing `query` line.

Then update the `recordMatchesFilters()` call:

```javascript
    const matches = recordMatchesFilters(record, { query, platform, issue, responsibility, feedback });
```

Modify `recordMatchesFilters(record, filters)`:

```javascript
  const platform = (record.dataset.platform || "").toLowerCase();
  const matchesQuery = !filters.query || searchText.includes(filters.query);
  const matchesPlatform = !filters.platform || platform.includes(filters.platform);
  const matchesIssue = !filters.issue || record.dataset.issueCategory === filters.issue;
  const matchesResponsibility = !filters.responsibility || record.dataset.responsibility === filters.responsibility;
  const matchesFeedback = !filters.feedback || record.dataset.feedbackStatus === filters.feedback;
  return matchesQuery && matchesPlatform && matchesIssue && matchesResponsibility && matchesFeedback;
```

- [ ] **Step 5: Run JavaScript hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
```

Expected: selected tests pass.

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
git commit -m "feat: filter recent records by platform"
```

## Task 3: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README filtering docs**

Modify the first paragraph under `## 筛选最近记录` in `README.md` from:

```markdown
工作台“最近记录”区域支持本地筛选当前页面展示的最近 10 条记录。可以按关键词、问题类型、责任方和复核状态组合筛选；点击 `清空` 可恢复显示全部当前记录。
```

To:

```markdown
工作台“最近记录”区域支持本地筛选当前页面展示的最近 10 条记录。可以按平台、关键词、问题类型、责任方和复核状态组合筛选；点击 `清空` 可恢复显示全部当前记录。
```

Modify the next paragraph from:

```markdown
筛选只影响页面显示，不改变 JSONL 存储；如果需要把相同条件应用到全部本地记录导出，请使用 `导出筛选 CSV`。
```

To:

```markdown
筛选只影响页面显示，不改变 JSONL 存储；如果需要把相同平台和其他筛选条件应用到全部本地记录导出，请使用 `导出筛选 CSV`。
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
git commit -m "docs: document recent records platform filtering"
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

- Spec coverage: platform filter input, platform presets reuse, local `data-platform` matching, case-insensitive contains matching, reset behavior through `form.reset()`, filtered CSV `platform` parameter, README docs, and full regression verification are covered.
- Deferred items: backend API additions, JSONL schema changes, alias normalization, summary semantics changes, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `platform-filter`, `platform`, `filters.platform`, `matchesPlatform`, `data-platform`, and `platform-presets` are named consistently across tests, implementation, and documentation.
