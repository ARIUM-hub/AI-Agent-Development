# Batch Result Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 批量分析成功后，在批量结果列表上方展示当前批次的记录数、待复核数、问题类型、责任方和证据强度摘要。

**Architecture:** 保持后端 `/api/analyze-batch-file` 响应不变，在前端 `renderBatchResults(payload)` 内基于 `payload.records` 构建本批次摘要。新增纯前端 helper 负责统计和渲染，复用现有 `summaryMetric()`、`summaryDistribution()`、`labelFor()` 和 `escapeHtml()`，但批次摘要的分布不使用可点击平台筛选。

**Tech Stack:** FastAPI + Jinja2 静态页面，原生 JavaScript，CSS，pytest + TestClient。

---

## File Structure

- Modify: `tests/test_app.py`
  - 扩展静态 JS hook 测试，锁定批量摘要函数与中文文案。
  - 扩展 CSS hook 测试，锁定批量摘要样式类。
- Modify: `src/customer_issue_agent/static/app.js`
  - 新增 `buildBatchSummary(records)`、`rankBatchSummary(counter)`、`batchSummaryDistribution(title, labelGroup, items)`、`batchSummaryHtml(payload)`。
  - 修改 `renderBatchResults(payload)`，在 `.batch-list` 之前插入批次摘要 HTML。
- Modify: `src/customer_issue_agent/static/styles.css`
  - 为批次摘要添加轻量布局，使其和现有 summary card 视觉一致。

---

### Task 1: Add Static Hook Tests For Batch Summary

**Files:**
- Modify: `tests/test_app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing JS hook test**

Modify `test_static_app_js_contains_batch_and_feedback_hooks` so it includes these assertions:

```python
def test_static_app_js_contains_batch_and_feedback_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "submitBatchForm" in script
    assert "renderBatchResults" in script
    assert "bindFeedbackForms" in script
    assert "submitFeedbackForm" in script
    assert "buildBatchSummary" in script
    assert "batchSummaryHtml" in script
    assert "batchSummaryDistribution" in script
    assert "本批次摘要" in script
    assert "待复核" in script
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_batch_and_feedback_hooks -q
```

Expected: `FAIL` because `buildBatchSummary` is not present in `src/customer_issue_agent/static/app.js`.

- [ ] **Step 3: Commit the failing test**

Run:

```powershell
git add -- tests/test_app.py
git commit -m "test: cover batch result summary hooks"
```

Expected: commit succeeds with only `tests/test_app.py` staged.

---

### Task 2: Implement Front-End Batch Summary Rendering

**Files:**
- Modify: `src/customer_issue_agent/static/app.js`
- Test: `tests/test_app.py`

- [ ] **Step 1: Update `renderBatchResults(payload)` to include the summary**

Replace the current `renderBatchResults(payload)` template with this structure:

```javascript
function renderBatchResults(payload) {
  const container = document.getElementById("batch-results");
  container.innerHTML = `
    <div class="result-header">
      <div>
        <p class="eyebrow">批量分析完成</p>
        <h2>${payload.count} 条会话已生成分析</h2>
      </div>
      <span class="record-id">批次 #${escapeHtml(payload.batch_id.slice(0, 8))}</span>
    </div>
    ${batchSummaryHtml(payload)}
    <div class="batch-list"></div>
  `;
  const list = container.querySelector(".batch-list");
  payload.records.forEach((record) => {
    list.appendChild(buildRecordCard(record));
  });
  bindFeedbackForms(container);
}
```

- [ ] **Step 2: Add summary helpers after `renderBatchResults(payload)`**

Insert these functions immediately after `renderBatchResults(payload)`:

```javascript
function batchSummaryHtml(payload) {
  const summary = buildBatchSummary(payload.records || []);
  return `
    <section class="batch-summary" aria-label="本批次摘要">
      <div class="batch-summary-header">
        <p class="eyebrow">本批次摘要</p>
        <h3>先看整体，再逐条复核</h3>
      </div>
      <div class="summary-metrics batch-summary-metrics">
        ${summaryMetric("本批次记录", payload.count ?? summary.total_records)}
        ${summaryMetric("待复核", summary.unreviewed_records)}
      </div>
      <div class="summary-grid batch-summary-grid">
        ${batchSummaryDistribution("问题类型", "issue_category", summary.issue_categories)}
        ${batchSummaryDistribution("责任方", "responsibility", summary.responsibilities)}
        ${batchSummaryDistribution("证据强度", "evidence", summary.evidence_strengths)}
      </div>
    </section>
  `;
}

function buildBatchSummary(records) {
  const issueCategories = {};
  const responsibilities = {};
  const evidenceStrengths = {};

  records.forEach((record) => {
    const attribution = record.analysis?.attribution || {};
    incrementBatchCounter(issueCategories, attribution.issue_category);
    incrementBatchCounter(responsibilities, attribution.primary_responsibility);
    incrementBatchCounter(evidenceStrengths, attribution.evidence_strength);
  });

  return {
    total_records: records.length,
    unreviewed_records: records.length,
    issue_categories: rankBatchSummary(issueCategories),
    responsibilities: rankBatchSummary(responsibilities),
    evidence_strengths: rankBatchSummary(evidenceStrengths),
  };
}

function incrementBatchCounter(counter, value) {
  const key = String(value || "unknown").trim() || "unknown";
  counter[key] = (counter[key] || 0) + 1;
}

function rankBatchSummary(counter) {
  return Object.entries(counter)
    .map(([value, count]) => ({ value, count }))
    .sort((left, right) => right.count - left.count || left.value.localeCompare(right.value));
}

function batchSummaryDistribution(title, labelGroup, items = []) {
  const rows = items.length
    ? items.map((item) => `
        <li>
          <span>${escapeHtml(labelFor(labelGroup, item.value))}</span>
          <strong>${escapeHtml(item.count)}</strong>
        </li>
      `).join("")
    : `<li><span>暂无数据</span><strong>0</strong></li>`;

  return `
    <article class="summary-card distribution-card batch-summary-card">
      <h4>${escapeHtml(title)}</h4>
      <ul class="distribution-list">${rows}</ul>
    </article>
  `;
}
```

- [ ] **Step 3: Run the focused JS hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_batch_and_feedback_hooks -q
```

Expected: `1 passed`.

- [ ] **Step 4: Commit the implementation**

Run:

```powershell
git add -- src/customer_issue_agent/static/app.js
git commit -m "feat: summarize batch analysis results"
```

Expected: commit succeeds with only `src/customer_issue_agent/static/app.js` staged.

---

### Task 3: Add Batch Summary Styles And CSS Hooks

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing CSS hook test**

Modify `test_styles_cover_enhanced_workbench_components` to include:

```python
def test_styles_cover_enhanced_workbench_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".workspace-grid" in css
    assert ".tabs" in css
    assert ".result-grid" in css
    assert ".result-card" in css
    assert ".form-message.is-visible" in css
    assert ".batch-summary" in css
    assert ".batch-summary-grid" in css
    assert ".batch-summary-card" in css
    assert "@media (max-width: 720px)" in css
```

- [ ] **Step 2: Run the focused CSS hook test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_enhanced_workbench_components -q
```

Expected: `FAIL` because `.batch-summary` is not present in `src/customer_issue_agent/static/styles.css`.

- [ ] **Step 3: Add the CSS implementation**

Insert this CSS near the existing `.batch-results` and `.batch-list` rules:

```css
.batch-summary {
  display: grid;
  gap: 14px;
  margin: 18px 0;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.68);
}

.batch-summary-header h3 {
  margin: 4px 0 0;
  font-size: 18px;
}

.batch-summary-metrics {
  margin: 0;
}

.batch-summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.batch-summary-card h4 {
  margin: 0 0 10px;
  font-size: 15px;
}
```

Inside the existing `@media (max-width: 720px)` block, add:

```css
  .batch-summary-grid {
    grid-template-columns: 1fr;
  }
```

- [ ] **Step 4: Run the focused CSS hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_enhanced_workbench_components -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the styles and test**

Run:

```powershell
git add -- tests/test_app.py src/customer_issue_agent/static/styles.css
git commit -m "style: add batch summary layout"
```

Expected: commit succeeds with `tests/test_app.py` and `src/customer_issue_agent/static/styles.css` staged.

---

### Task 4: Full Verification And PR Update

**Files:**
- Verify: repository test suite
- Push: `codex/customer-issue-agent-mvp`

- [ ] **Step 1: Check git status before verification**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
```

Expected: clean working tree on `codex/customer-issue-agent-mvp`, possibly ahead of `origin/codex/customer-issue-agent-mvp` because `origin` may point to the old repository.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect recent commits**

Run:

```powershell
git log --oneline -6
```

Expected: latest commits include:

```text
style: add batch summary layout
feat: summarize batch analysis results
test: cover batch result summary hooks
docs: design batch result summary
```

- [ ] **Step 4: Push only to the target repository PR branch**

Run:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: push succeeds and updates PR #2 in `ARIUM-hub/Agent-Operations-Workflow`.

---

## Self-Review

- Spec coverage: The plan covers front-end-only summary rendering, current-batch-only statistics, no API changes, no partial failure support, safe empty data rendering, CSS hooks, focused tests, full verification, and explicit target-repo push.
- Completion scan: 所有实现步骤都有明确代码、命令和预期结果。
- Type consistency: Function names are consistent across tests and implementation: `buildBatchSummary`, `batchSummaryHtml`, `batchSummaryDistribution`, `rankBatchSummary`, and `incrementBatchCounter`.
