# Recent Record Detail Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add expandable structured details to recent record cards without changing storage or API behavior.

**Architecture:** Render persisted recent-record detail markup directly in the existing Jinja template using already-loaded `record.analysis` and `record.feedback` data. Add small vanilla JavaScript helpers to toggle `hidden`, `aria-expanded`, and button text, and to generate the same detail structure for newly prepended records. Keep styling local to record detail classes.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, vanilla JavaScript, CSS, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-recent-record-detail-toggle-design.md`

## Scope Check

This plan implements only expandable details for the existing recent-record cards. It does not add a record detail API, modal/drawer UI, detail editing, pagination, rich text rendering, storage changes, or model calls.

## File Structure

- Modify: `tests/test_app.py`
  - Add HTML, JS, and CSS hook tests for record detail toggles.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add persisted recent-record detail buttons and hidden detail regions.
- Modify: `src/customer_issue_agent/static/app.js`
  - Add detail toggle binding and dynamic detail markup for newly prepended records.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Add detail toggle and detail grid styles.
- Modify: `README.md`
  - Document how to expand recent record details.

## Task 1: Persisted Recent Record Detail Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write failing persisted-detail markup test**

Append to `tests/test_app.py`:

```python
def test_recent_records_include_expandable_detail_markup(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = response.json()["record_id"]
    client.post(
        f"/api/records/{record_id}/feedback",
        data={"accepted": "false", "note": "需要复核安装步骤"},
    )

    html = client.get("/").text

    assert "查看详情" in html
    assert "data-record-detail-toggle" in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="record-detail-' in html
    assert 'class="record-detail"' in html
    assert "客户问题" in html
    assert "下一步建议" in html
    assert "人工备注" in html
    assert "需要复核安装步骤" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_recent_records_include_expandable_detail_markup -q
```

Expected: FAIL because recent records do not contain `data-record-detail-toggle` or `record-detail` markup.

- [ ] **Step 3: Add persisted detail markup**

Modify the recent-record loop in `src/customer_issue_agent/templates/index.html`. Insert this block immediately after the existing record report paragraph:

```html
                  <button
                    class="record-detail-toggle secondary-action"
                    type="button"
                    data-record-detail-toggle
                    aria-expanded="false"
                    aria-controls="record-detail-{{ record.id }}"
                  >查看详情</button>
                  <div id="record-detail-{{ record.id }}" class="record-detail" hidden>
                    <dl class="record-detail-grid">
                      <div>
                        <dt>客户问题</dt>
                        <dd>{{ record.analysis.attribution.customer_problem or "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>问题类型</dt>
                        <dd>{{ record.analysis.attribution.issue_category or "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>业务原因</dt>
                        <dd>{{ record.analysis.attribution.root_causes|join("；") if record.analysis.attribution.root_causes else "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>优先责任方</dt>
                        <dd>{{ record.analysis.attribution.primary_responsibility or "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>证据强度</dt>
                        <dd>{{ record.analysis.attribution.evidence_strength or "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>下一步建议</dt>
                        <dd>{{ record.analysis.attribution.recommended_actions|join("；") if record.analysis.attribution.recommended_actions else "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>需要补充信息</dt>
                        <dd>{{ record.analysis.attribution.missing_information|join("；") if record.analysis.attribution.missing_information else "暂无信息" }}</dd>
                      </div>
                      <div>
                        <dt>人工复核</dt>
                        <dd>{{ "已认可" if record.feedback and record.feedback.accepted else "已修正" if record.feedback else "未复核" }}</dd>
                      </div>
                      <div>
                        <dt>人工备注</dt>
                        <dd>{{ record.feedback.note if record.feedback and record.feedback.note else "暂无信息" }}</dd>
                      </div>
                    </dl>
                  </div>
```

- [ ] **Step 4: Run markup test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_recent_records_include_expandable_detail_markup -q
```

Expected: selected test passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html tests/test_app.py
git commit -m "feat: add recent record detail markup"
```

## Task 2: Detail Toggle JavaScript And Dynamic Cards

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing JavaScript hook test**

Append to `tests/test_app.py`:

```python
def test_static_app_js_contains_record_detail_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindRecordDetails" in script
    assert "toggleRecordDetail" in script
    assert "recordDetailHtml" in script
    assert "data-record-detail-toggle" in script
    assert "aria-expanded" in script
    assert "收起详情" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: FAIL because the JS detail helpers do not exist.

- [ ] **Step 3: Add detail binding on page load**

Modify the DOMContentLoaded callback in `src/customer_issue_agent/static/app.js`:

```javascript
  bindRecordDetails(document);
```

Place it after `bindRecordFilters();` so initial records have both filter and detail behavior.

- [ ] **Step 4: Add detail toggle helpers**

Add these functions before `bindRecordFilters()` in `src/customer_issue_agent/static/app.js`:

```javascript
function bindRecordDetails(root = document) {
  root.querySelectorAll("[data-record-detail-toggle]").forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.dataset.bound = "true";
    button.addEventListener("click", () => toggleRecordDetail(button));
  });
}

function toggleRecordDetail(button) {
  const detailId = button.getAttribute("aria-controls");
  const detail = detailId ? document.getElementById(detailId) : null;
  if (!detail) {
    return;
  }

  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  button.textContent = expanded ? "查看详情" : "收起详情";
  detail.hidden = expanded;
}

function recordDetailHtml(recordId, analysis, feedback = null) {
  const attribution = analysis.attribution;
  const feedbackStatus = feedback ? (feedback.accepted ? "已认可" : "已修正") : "未复核";
  const feedbackNote = feedback?.note || "暂无信息";
  const detailId = `record-detail-${recordId}`;

  return `
    <button
      class="record-detail-toggle secondary-action"
      type="button"
      data-record-detail-toggle
      aria-expanded="false"
      aria-controls="${escapeHtml(detailId)}"
    >查看详情</button>
    <div id="${escapeHtml(detailId)}" class="record-detail" hidden>
      <dl class="record-detail-grid">
        ${recordDetailRow("客户问题", attribution.customer_problem)}
        ${recordDetailRow("问题类型", labelFor("issue_category", attribution.issue_category))}
        ${recordDetailRow("业务原因", listText((attribution.root_causes || []).map((item) => labelFor("rootCause", item))))}
        ${recordDetailRow("优先责任方", labelFor("responsibility", attribution.primary_responsibility))}
        ${recordDetailRow("证据强度", labelFor("evidence", attribution.evidence_strength))}
        ${recordDetailRow("下一步建议", listText(attribution.recommended_actions))}
        ${recordDetailRow("需要补充信息", listText(attribution.missing_information))}
        ${recordDetailRow("人工复核", feedbackStatus)}
        ${recordDetailRow("人工备注", feedbackNote)}
      </dl>
    </div>
  `;
}

function recordDetailRow(label, value) {
  return `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value || "暂无信息")}</dd>
    </div>
  `;
}

function listText(value) {
  if (!Array.isArray(value)) {
    return value || "暂无信息";
  }
  return value.filter(Boolean).join("；") || "暂无信息";
}
```

- [ ] **Step 5: Add dynamic detail markup to newly prepended records**

In `prependRecentRecord(payload)`, insert the detail HTML after the existing report paragraph:

```javascript
    <p>${escapeHtml(analysis.report)}</p>
    ${recordDetailHtml(payload.record_id, analysis)}
```

Then after `list.prepend(article);`, add:

```javascript
  bindRecordDetails(article);
```

The final part of `prependRecentRecord()` should be:

```javascript
  article.innerHTML = `
    <div class="record-meta">
      <strong>${escapeHtml(analysis.request.platform)}</strong>
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <p>${escapeHtml(analysis.report)}</p>
    ${recordDetailHtml(payload.record_id, analysis)}
  `;
  list.prepend(article);
  bindRecordDetails(article);
  applyRecordFilters();
```

- [ ] **Step 6: Run JavaScript hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_record_detail_hooks -q
```

Expected: selected test passes.

- [ ] **Step 7: Run app tests**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py -q
```

Expected: all app tests pass.

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: toggle recent record details"
```

## Task 3: Detail Styles

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write failing CSS hook test**

Append to `tests/test_app.py`:

```python
def test_styles_cover_record_detail_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".record-detail-toggle" in css
    assert ".record-detail" in css
    assert ".record-detail-grid" in css
    assert ".record-detail-grid dt" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_record_detail_components -q
```

Expected: FAIL because record detail classes are not styled.

- [ ] **Step 3: Add CSS styles**

Add to `src/customer_issue_agent/static/styles.css` near existing `.record` styles:

```css
.record-detail-toggle {
  margin-top: 12px;
}

.record-detail {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fbfcf8;
  white-space: normal;
}

.record-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.record-detail-grid div {
  min-width: 0;
}

.record-detail-grid dt {
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.record-detail-grid dd {
  margin: 6px 0 0;
  line-height: 1.6;
}
```

Add this inside `@media (max-width: 720px)`:

```css
  .record-detail-grid {
    grid-template-columns: 1fr;
  }
```

- [ ] **Step 4: Run CSS hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_record_detail_components -q
```

Expected: selected test passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "style: add recent record detail styles"
```

## Task 4: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Append this paragraph to the “筛选最近记录” section in `README.md`:

```markdown
每条最近记录都可以点击 `查看详情` 展开结构化明细，包括客户问题、业务原因、下一步建议、需要补充信息以及人工复核备注。详情展开只影响页面显示，不会修改记录内容。
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
git commit -m "docs: document recent record details"
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

- Spec coverage: persisted detail markup, default hidden state, accessible toggle attributes, JavaScript toggle behavior, dynamic newly prepended records, CSS styling, README docs, and regression verification are covered.
- Deferred items: record detail API, modal/drawer, editing, pagination, rich text rendering, storage changes, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `data-record-detail-toggle`, `record-detail`, `record-detail-grid`, `bindRecordDetails`, `toggleRecordDetail`, and `recordDetailHtml` are named consistently across tasks.
