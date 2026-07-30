# Platform Summary Drilldown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators click a platform in the operations summary and immediately filter recent records by that platform.

**Architecture:** Keep the drilldown entirely in the existing front-end workbench. Extend the existing `summaryDistribution()` renderer so only `labelGroup === "platform"` rows render as buttons, then bind those buttons to the existing `#platform-filter` and `applyRecordFilters()` flow.

**Tech Stack:** Python 3.12, FastAPI static file serving, vanilla JavaScript, CSS, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-30-platform-summary-drilldown-design.md`

## Scope Check

This plan implements only a platform-summary-to-recent-records front-end drilldown. It does not add backend APIs, alter JSONL records, normalize platform aliases, change CSV export behavior, change summary aggregation semantics, or call model providers.

## File Structure

- Modify: `tests/test_app.py`
  - Extend summary dashboard JS hook tests for platform drilldown functions and data attributes.
  - Extend summary dashboard CSS hook tests for the new clickable platform style.
- Modify: `src/customer_issue_agent/static/app.js`
  - Render platform distribution values as buttons with `data-summary-platform-filter`.
  - Bind platform drilldown buttons after summary rendering.
  - Set `#platform-filter`, call `applyRecordFilters()`, and scroll to recent records.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Add `.summary-filter-link` styles that look like an inline, accessible text action.
- Modify: `README.md`
  - Document platform summary drilldown in the operations overview section.

## Task 1: Platform Drilldown Markup And Behavior

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing JavaScript hook test**

Modify `test_static_app_js_contains_summary_dashboard_hooks` in `tests/test_app.py` by adding:

```python
assert "bindSummaryPlatformFilters" in script
assert "applySummaryPlatformFilter" in script
assert "data-summary-platform-filter" in script
assert "scrollIntoView" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks -q
```

Expected: FAIL because `app.js` does not yet include the platform drilldown binding or `data-summary-platform-filter`.

- [ ] **Step 3: Render platform rows as buttons**

Modify `renderRecordsSummary(summary)` in `src/customer_issue_agent/static/app.js` so it binds platform drilldown buttons after assigning `container.innerHTML`:

```javascript
  bindSummaryPlatformFilters(container);
```

Modify `summaryDistribution(title, labelGroup, items = [])` so it uses a label helper:

```javascript
function summaryDistribution(title, labelGroup, items = []) {
  const rows = items.length
    ? items.map((item) => `
        <li>
          ${summaryDistributionLabel(labelGroup, item.value)}
          <strong>${escapeHtml(item.count)}</strong>
        </li>
      `).join("")
    : `<li><span>暂无数据</span><strong>0</strong></li>`;

  return `
    <article class="summary-card distribution-card">
      <h3>${escapeHtml(title)}</h3>
      <ul class="distribution-list">${rows}</ul>
    </article>
  `;
}
```

Add this helper immediately after `summaryDistribution()`:

```javascript
function summaryDistributionLabel(labelGroup, value) {
  const label = labelFor(labelGroup, value);
  if (labelGroup !== "platform") {
    return `<span>${escapeHtml(label)}</span>`;
  }
  return `
    <button
      class="summary-filter-link"
      type="button"
      data-summary-platform-filter="${escapeHtml(value)}"
    >${escapeHtml(label)}</button>
  `;
}
```

- [ ] **Step 4: Add drilldown click binding**

Add these functions after `summaryDistributionLabel()` in `src/customer_issue_agent/static/app.js`:

```javascript
function bindSummaryPlatformFilters(root = document) {
  root.querySelectorAll("[data-summary-platform-filter]").forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      applySummaryPlatformFilter(button.dataset.summaryPlatformFilter || "");
    });
  });
}

function applySummaryPlatformFilter(platform) {
  const value = platform.trim();
  const input = document.getElementById("platform-filter");
  if (!value || !input) {
    return;
  }

  input.value = value;
  applyRecordFilters();

  const recentRecords = document.getElementById("recent-records");
  const target = recentRecords?.closest("section") || recentRecords;
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}
```

- [ ] **Step 5: Run JavaScript hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks -q
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
git commit -m "feat: drill into platform summary"
```

## Task 2: Drilldown Link Styling

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write failing CSS hook test**

Modify `test_styles_cover_summary_dashboard_components` in `tests/test_app.py` by adding:

```python
assert ".summary-filter-link" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_summary_dashboard_components -q
```

Expected: FAIL because `styles.css` does not yet define `.summary-filter-link`.

- [ ] **Step 3: Add summary filter link styles**

Add this CSS after `.distribution-list li` in `src/customer_issue_agent/static/styles.css`:

```css
.summary-filter-link {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  text-align: left;
}

.summary-filter-link:hover,
.summary-filter-link:focus-visible {
  text-decoration: underline;
}
```

- [ ] **Step 4: Run CSS hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_summary_dashboard_components -q
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
git commit -m "style: highlight platform summary drilldown"
```

## Task 3: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README operations overview**

Modify the “查看运营概览” section in `README.md` by adding this sentence after the sentence that lists the summary dimensions:

```markdown
在“平台分布”中点击某个平台名称，可以自动填入最近记录的平台筛选栏并查看当前页面中的相关样本。
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
git commit -m "docs: document platform summary drilldown"
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

- Spec coverage: platform-only clickable summary rows, `#platform-filter` population, `applyRecordFilters()` reuse, recent records scrolling, graceful no-op behavior, styles, README docs, and full regression verification are covered.
- Deferred items: backend API additions, JSONL changes, CSV behavior changes, alias normalization, all-dimension drilldown, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `bindSummaryPlatformFilters`, `applySummaryPlatformFilter`, `data-summary-platform-filter`, `summary-filter-link`, `platform-filter`, and `applyRecordFilters` are named consistently across tests, implementation, and documentation.
