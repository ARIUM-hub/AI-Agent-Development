# Recent Records Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local filtering and keyword search for the current recent-records list in the workbench.

**Architecture:** Keep filtering entirely in the existing single-page workbench. The Jinja template emits filter controls and per-record `data-*` attributes, while the existing vanilla JavaScript file reads those attributes to show/hide current DOM records without changing storage, APIs, or CSV export behavior.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, vanilla JavaScript, CSS, pytest, httpx.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-recent-records-filter-design.md`

## Scope Check

This plan implements only front-end local filtering over the already-rendered recent 10 records. It does not add server-side search, pagination, JSONL schema changes, filtered CSV export, or a front-end framework.

## File Structure

- Modify: `src/customer_issue_agent/templates/index.html`
  - Add filter controls above the recent records list.
  - Add record `data-*` attributes for platform, issue category, responsibility, feedback status, and search text.
- Modify: `src/customer_issue_agent/static/app.js`
  - Add local filter binding, filtering, count updates, empty state, and reset behavior.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Style filter controls and no-match message.
- Modify: `tests/test_app.py`
  - Add HTML and static asset hook tests.
- Modify: `README.md`
  - Document local recent-record filtering.

## Task 1: Recent Record Filter Markup

**Files:**
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing markup tests**

Append to `tests/test_app.py`:

```python
def test_index_contains_recent_record_filter_controls(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="record-filter"' in html
    assert 'id="record-search"' in html
    assert 'id="issue-filter"' in html
    assert 'id="responsibility-filter"' in html
    assert 'id="feedback-filter"' in html
    assert 'id="filter-count"' in html
    assert 'id="filter-empty"' in html
    assert 'data-filter-reset' in html


def test_recent_records_include_filter_data_attributes(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = response.json()["record_id"]
    client.post(f"/api/records/{record_id}/feedback", data={"accepted": "true"})

    html = client.get("/").text

    assert 'data-record-id="' in html
    assert 'data-platform="Amazon"' in html
    assert 'data-issue-category="' in html
    assert 'data-responsibility="' in html
    assert 'data-feedback-status="accepted"' in html
    assert 'data-search-text="' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls tests/test_app.py::test_recent_records_include_filter_data_attributes -q
```

Expected: FAIL because filter controls and data attributes do not exist yet.

- [ ] **Step 3: Add filter controls and record data attributes**

Modify `src/customer_issue_agent/templates/index.html` inside the history section, between `.section-heading` and `#recent-records`:

```html
          <form id="record-filter" class="record-filter" role="search" aria-label="筛选最近记录">
            <label class="filter-field" for="record-search">
              <span>关键词</span>
              <input id="record-search" name="search" type="search" placeholder="搜索平台、报告或记录 ID">
            </label>
            <label class="filter-field" for="issue-filter">
              <span>问题类型</span>
              <select id="issue-filter" name="issue_category">
                <option value="">全部问题类型</option>
                <option value="installation">安装、开箱或组装问题</option>
                <option value="function_use">功能不会用或设置失败</option>
                <option value="expectation_gap">功能表现未达到预期</option>
                <option value="product_fault">产品异常或质量问题</option>
                <option value="compatibility">兼容性问题</option>
                <option value="accessory">配件或使用条件问题</option>
                <option value="non_usage">非产品使用问题</option>
                <option value="unclear">信息不足</option>
              </select>
            </label>
            <label class="filter-field" for="responsibility-filter">
              <span>责任方</span>
              <select id="responsibility-filter" name="responsibility">
                <option value="">全部责任方</option>
                <option value="operations">运营</option>
                <option value="customer_service_training">客服培训</option>
                <option value="product">产品</option>
                <option value="supply_chain_quality">供应链或质量</option>
                <option value="need_more_information">需要补充信息</option>
              </select>
            </label>
            <label class="filter-field" for="feedback-filter">
              <span>复核状态</span>
              <select id="feedback-filter" name="feedback_status">
                <option value="">全部复核状态</option>
                <option value="unreviewed">未复核</option>
                <option value="accepted">已认可</option>
                <option value="corrected">已修正</option>
              </select>
            </label>
            <button class="secondary-action" type="button" data-filter-reset>清空</button>
            <p id="filter-count" class="filter-count" aria-live="polite">当前显示 {{ records|length }} / {{ records|length }} 条</p>
          </form>
          <p id="filter-empty" class="filter-empty" hidden>没有符合条件的记录。</p>
```

Modify each recent record `<article>`:

```html
                <article
                  class="record"
                  data-record-id="{{ record.id }}"
                  data-platform="{{ record.analysis.request.platform }}"
                  data-issue-category="{{ record.analysis.attribution.issue_category }}"
                  data-responsibility="{{ record.analysis.attribution.primary_responsibility }}"
                  data-feedback-status="{{ 'accepted' if record.feedback and record.feedback.accepted else 'corrected' if record.feedback else 'unreviewed' }}"
                  data-search-text="{{ record.id }} {{ record.analysis.request.platform }} {{ record.analysis.report }} {{ record.feedback.note if record.feedback and record.feedback.note else '' }}"
                >
```

- [ ] **Step 4: Run markup tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls tests/test_app.py::test_recent_records_include_filter_data_attributes -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html tests/test_app.py
git commit -m "feat: add recent record filter markup"
```

## Task 2: Filter Behavior And Styling

**Files:**
- Modify: `src/customer_issue_agent/static/app.js`
- Modify: `src/customer_issue_agent/static/styles.css`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing JS and CSS hook tests**

Append to `tests/test_app.py`:

```python
def test_static_app_js_contains_recent_record_filter_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindRecordFilters" in script
    assert "applyRecordFilters" in script
    assert "resetRecordFilters" in script
    assert "recordMatchesFilters" in script


def test_styles_cover_recent_record_filter_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".record-filter" in css
    assert ".filter-field" in css
    assert ".filter-count" in css
    assert ".filter-empty" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: FAIL because filter JS and CSS hooks do not exist.

- [ ] **Step 3: Add filter JavaScript**

Modify `src/customer_issue_agent/static/app.js` in the DOMContentLoaded callback:

```javascript
  bindRecordFilters();
```

Add the following functions before `readError()`:

```javascript
function bindRecordFilters() {
  const form = document.getElementById("record-filter");
  if (!form) {
    return;
  }

  form.addEventListener("input", () => applyRecordFilters());
  form.addEventListener("change", () => applyRecordFilters());

  const reset = form.querySelector("[data-filter-reset]");
  if (reset) {
    reset.addEventListener("click", () => resetRecordFilters(form));
  }

  applyRecordFilters();
}

function applyRecordFilters() {
  const records = Array.from(document.querySelectorAll("#recent-records .record"));
  const query = document.getElementById("record-search")?.value.trim().toLowerCase() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";
  let visible = 0;

  records.forEach((record) => {
    const matches = recordMatchesFilters(record, { query, issue, responsibility, feedback });
    record.hidden = !matches;
    if (matches) {
      visible += 1;
    }
  });

  updateFilterState(visible, records.length);
}

function resetRecordFilters(form) {
  form.reset();
  applyRecordFilters();
}

function recordMatchesFilters(record, filters) {
  const searchText = (record.dataset.searchText || "").toLowerCase();
  const matchesQuery = !filters.query || searchText.includes(filters.query);
  const matchesIssue = !filters.issue || record.dataset.issueCategory === filters.issue;
  const matchesResponsibility = !filters.responsibility || record.dataset.responsibility === filters.responsibility;
  const matchesFeedback = !filters.feedback || record.dataset.feedbackStatus === filters.feedback;
  return matchesQuery && matchesIssue && matchesResponsibility && matchesFeedback;
}

function updateFilterState(visible, total) {
  const count = document.getElementById("filter-count");
  const empty = document.getElementById("filter-empty");
  if (count) {
    count.textContent = `当前显示 ${visible} / ${total} 条`;
  }
  if (empty) {
    empty.hidden = visible > 0 || total === 0;
  }
}
```

- [ ] **Step 4: Add filter CSS**

Add to `src/customer_issue_agent/static/styles.css`:

```css
.record-filter {
  display: grid;
  grid-template-columns: minmax(220px, 1.5fr) repeat(3, minmax(160px, 1fr)) auto;
  gap: 12px;
  margin-top: 18px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.62);
}

.filter-field {
  display: grid;
  gap: 6px;
  margin: 0;
}

.filter-field span,
.filter-count {
  color: var(--muted);
  font-size: 13px;
}

.filter-count {
  grid-column: 1 / -1;
  margin: 0;
}

.filter-empty {
  margin: 16px 0 0;
  padding: 16px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  color: var(--muted);
  text-align: center;
}
```

Add this mobile adjustment inside `@media (max-width: 900px)`:

```css
  .record-filter {
    grid-template-columns: 1fr;
  }
```

- [ ] **Step 5: Run JS/CSS hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: PASS.

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
git add src/customer_issue_agent/static/app.js src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "feat: filter recent records locally"
```

## Task 3: README And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with filtering usage**

Append to `README.md`:

```markdown
## 筛选最近记录

工作台“最近记录”区域支持本地筛选当前页面展示的最近 10 条记录。可以按关键词、问题类型、责任方和复核状态组合筛选；点击 `清空` 可恢复显示全部当前记录。

筛选只影响页面显示，不改变 JSONL 存储，也不影响 `导出 CSV` 下载全部记录。
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
git status --short --branch
```

Expected: only README is modified before commit.

- [ ] **Step 4: Commit**

Run:

```powershell
git add README.md
git commit -m "docs: document recent record filtering"
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
git status --short --branch
```

Expected: clean worktree on `codex/customer-issue-agent-mvp`.

- [ ] Push to target repository:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: push succeeds and updates the existing open PR in `ARIUM-hub/Agent-Operations-Workflow`.

## Self-Review Checklist

- Spec coverage: filter controls, record data attributes, keyword search, issue/responsibility/feedback filters, reset, count display, no-match display, JS fallback behavior, README docs, and regression verification are covered.
- Deferred items: server-side search, pagination, schema changes, full JSONL front-end loading, filtered CSV export, and saved filters are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder tasks.
- Type consistency: `bindRecordFilters`, `applyRecordFilters`, `resetRecordFilters`, `recordMatchesFilters`, `record-filter`, `filter-count`, and `filter-empty` are named consistently across tests and implementation steps.
