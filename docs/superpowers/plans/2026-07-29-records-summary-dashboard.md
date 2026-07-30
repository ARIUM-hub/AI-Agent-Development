# Records Summary Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight operations summary dashboard for saved customer issue analysis records.

**Architecture:** Keep aggregation in a focused Python module that accepts records from `AnalysisStore.list_records()` and returns JSON-ready summary data. Expose that data through a small FastAPI endpoint, then render it in the existing single-page workbench with vanilla JavaScript and CSS.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, vanilla JavaScript, CSS, pytest, httpx.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-records-summary-dashboard-design.md`

## Scope Check

This plan implements only the lightweight summary dashboard MVP. It does not add time filtering, trend charts, SKU/ASIN dimensions, database storage, BI exports, model calls, or charting libraries.

## File Structure

- Create: `src/customer_issue_agent/summary.py`
  - Computes total counts and sorted dimension counts from record dictionaries.
- Create: `tests/test_summary.py`
  - Covers totals, reviewed/corrected counts, dimension sorting, feedback status rules, unknown values, and empty input.
- Modify: `src/customer_issue_agent/app.py`
  - Adds `GET /api/records/summary`.
- Modify: `tests/test_app.py`
  - Covers the summary API, dashboard markup, JS hooks, and CSS hooks.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Adds the operations summary dashboard container.
- Modify: `src/customer_issue_agent/static/app.js`
  - Fetches and renders the summary dashboard.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Styles summary cards and distribution lists.
- Modify: `README.md`
  - Documents the operations summary dashboard.

## Task 1: Summary Aggregation Module

**Files:**
- Create: `src/customer_issue_agent/summary.py`
- Create: `tests/test_summary.py`

- [ ] **Step 1: Write failing summary tests**

Create `tests/test_summary.py`:

```python
from customer_issue_agent.summary import build_records_summary


def test_build_records_summary_counts_totals_and_dimensions():
    records = [
        {
            "analysis": {
                "attribution": {
                    "issue_category": "function_use",
                    "primary_responsibility": "customer_service_training",
                    "evidence_strength": "likely",
                }
            },
            "feedback": {"accepted": True},
        },
        {
            "analysis": {
                "attribution": {
                    "issue_category": "function_use",
                    "primary_responsibility": "product",
                    "evidence_strength": "clear",
                }
            },
            "feedback": {"accepted": False},
        },
        {
            "analysis": {
                "attribution": {
                    "issue_category": "product_fault",
                    "primary_responsibility": "product",
                    "evidence_strength": "likely",
                }
            },
            "feedback": None,
        },
    ]

    summary = build_records_summary(records)

    assert summary["total_records"] == 3
    assert summary["reviewed_records"] == 2
    assert summary["corrected_records"] == 1
    assert summary["issue_categories"] == [
        {"value": "function_use", "count": 2},
        {"value": "product_fault", "count": 1},
    ]
    assert summary["responsibilities"] == [
        {"value": "product", "count": 2},
        {"value": "customer_service_training", "count": 1},
    ]
    assert summary["evidence_strengths"] == [
        {"value": "likely", "count": 2},
        {"value": "clear", "count": 1},
    ]
    assert summary["feedback_statuses"] == [
        {"value": "accepted", "count": 1},
        {"value": "corrected", "count": 1},
        {"value": "unreviewed", "count": 1},
    ]


def test_build_records_summary_handles_empty_and_unknown_values():
    assert build_records_summary([]) == {
        "total_records": 0,
        "reviewed_records": 0,
        "corrected_records": 0,
        "issue_categories": [],
        "responsibilities": [],
        "evidence_strengths": [],
        "feedback_statuses": [],
    }

    summary = build_records_summary([{"analysis": {"attribution": {}}, "feedback": None}])

    assert summary["issue_categories"] == [{"value": "unknown", "count": 1}]
    assert summary["responsibilities"] == [{"value": "unknown", "count": 1}]
    assert summary["evidence_strengths"] == [{"value": "unknown", "count": 1}]
    assert summary["feedback_statuses"] == [{"value": "unreviewed", "count": 1}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_summary.py -q
```

Expected: FAIL because `customer_issue_agent.summary` does not exist.

- [ ] **Step 3: Implement summary module**

Create `src/customer_issue_agent/summary.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


def build_records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    issue_categories: Counter[str] = Counter()
    responsibilities: Counter[str] = Counter()
    evidence_strengths: Counter[str] = Counter()
    feedback_statuses: Counter[str] = Counter()
    reviewed_records = 0
    corrected_records = 0

    for record in records:
        attribution = ((record.get("analysis") or {}).get("attribution") or {})
        issue_categories[_value(attribution.get("issue_category"))] += 1
        responsibilities[_value(attribution.get("primary_responsibility"))] += 1
        evidence_strengths[_value(attribution.get("evidence_strength"))] += 1

        status = _feedback_status(record.get("feedback"))
        feedback_statuses[status] += 1
        if status != "unreviewed":
            reviewed_records += 1
        if status == "corrected":
            corrected_records += 1

    return {
        "total_records": len(records),
        "reviewed_records": reviewed_records,
        "corrected_records": corrected_records,
        "issue_categories": _rank(issue_categories),
        "responsibilities": _rank(responsibilities),
        "evidence_strengths": _rank(evidence_strengths),
        "feedback_statuses": _rank(feedback_statuses),
    }


def _feedback_status(feedback: object) -> str:
    if not isinstance(feedback, dict):
        return "unreviewed"
    return "accepted" if feedback.get("accepted") else "corrected"


def _rank(counter: Counter[str]) -> list[dict[str, int | str]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _value(value: object) -> str:
    if value is None:
        return "unknown"
    stripped = str(value).strip()
    return stripped or "unknown"
```

- [ ] **Step 4: Run summary tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_summary.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/summary.py tests/test_summary.py
git commit -m "feat: summarize analysis records"
```

## Task 2: Summary API

**Files:**
- Modify: `src/customer_issue_agent/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing API test**

Append to `tests/test_app.py`:

```python
def test_records_summary_endpoint_returns_counts(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    analysis_response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = analysis_response.json()["record_id"]
    client.post(f"/api/records/{record_id}/feedback", data={"accepted": "false"})

    response = client.get("/api/records/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 1
    assert payload["reviewed_records"] == 1
    assert payload["corrected_records"] == 1
    assert payload["issue_categories"]
    assert payload["responsibilities"]
    assert payload["evidence_strengths"]
    assert payload["feedback_statuses"] == [{"value": "corrected", "count": 1}]


def test_records_summary_endpoint_returns_empty_summary(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/api/records/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 0
    assert payload["issue_categories"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_records_summary_endpoint_returns_counts tests/test_app.py::test_records_summary_endpoint_returns_empty_summary -q
```

Expected: FAIL because `/api/records/summary` does not exist.

- [ ] **Step 3: Add API endpoint**

Modify `src/customer_issue_agent/app.py` imports:

```python
from customer_issue_agent.summary import build_records_summary
```

Add endpoint inside `create_app()`:

```python
    @app.get("/api/records/summary")
    async def records_summary() -> dict:
        return build_records_summary(store.list_records())
```

- [ ] **Step 4: Run app API tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_records_summary_endpoint_returns_counts tests/test_app.py::test_records_summary_endpoint_returns_empty_summary -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/app.py tests/test_app.py
git commit -m "feat: expose records summary API"
```

## Task 3: Summary Dashboard UI

**Files:**
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/app.js`
- Modify: `src/customer_issue_agent/static/styles.css`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing dashboard hook tests**

Append to `tests/test_app.py`:

```python
def test_index_contains_summary_dashboard_region(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="records-summary"' in html
    assert 'id="summary-content"' in html
    assert "运营概览" in html
    assert "概览加载中" in html


def test_static_app_js_contains_summary_dashboard_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "loadRecordsSummary" in script
    assert "renderRecordsSummary" in script
    assert "summaryMetric" in script
    assert "summaryDistribution" in script


def test_styles_cover_summary_dashboard_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".summary-dashboard" in css
    assert ".summary-metrics" in css
    assert ".summary-card" in css
    assert ".distribution-list" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_summary_dashboard_region tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks tests/test_app.py::test_styles_cover_summary_dashboard_components -q
```

Expected: FAIL because dashboard markup, JS, and CSS do not exist.

- [ ] **Step 3: Add dashboard markup**

Modify `src/customer_issue_agent/templates/index.html` between the workspace grid and history section:

```html
        <section id="records-summary" class="summary-dashboard panel" aria-live="polite">
          <div class="section-heading">
            <div>
              <p class="eyebrow">运营概览</p>
              <h2>分析记录分布</h2>
            </div>
            <span class="status">基于全部本地记录</span>
          </div>
          <div id="summary-content" class="summary-loading">概览加载中...</div>
        </section>
```

- [ ] **Step 4: Add summary JavaScript**

Modify `src/customer_issue_agent/static/app.js` in the DOMContentLoaded callback:

```javascript
  loadRecordsSummary();
```

Add feedback status labels near existing `labels`:

```javascript
  feedback: {
    unreviewed: "未复核",
    accepted: "已认可",
    corrected: "已修正",
  },
```

Add functions before `bindRecordFilters()`:

```javascript
async function loadRecordsSummary() {
  const container = document.getElementById("summary-content");
  if (!container) {
    return;
  }

  try {
    const response = await fetch("/api/records/summary");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderRecordsSummary(payload);
  } catch (error) {
    container.innerHTML = `<p class="summary-error">${escapeHtml(error.message || "概览加载失败，请刷新页面重试。")}</p>`;
  }
}

function renderRecordsSummary(summary) {
  const container = document.getElementById("summary-content");
  container.innerHTML = `
    <div class="summary-metrics">
      ${summaryMetric("总记录数", summary.total_records)}
      ${summaryMetric("已复核", summary.reviewed_records)}
      ${summaryMetric("已修正", summary.corrected_records)}
    </div>
    <div class="summary-grid">
      ${summaryDistribution("问题类型", "issue_category", summary.issue_categories)}
      ${summaryDistribution("责任方", "responsibility", summary.responsibilities)}
      ${summaryDistribution("证据强度", "evidence", summary.evidence_strengths)}
      ${summaryDistribution("复核状态", "feedback", summary.feedback_statuses)}
    </div>
  `;
}

function summaryMetric(label, value) {
  return `
    <article class="summary-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function summaryDistribution(title, labelGroup, items) {
  const rows = items.length
    ? items.map((item) => `
        <li>
          <span>${escapeHtml(labelFor(labelGroup, item.value))}</span>
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

- [ ] **Step 5: Add dashboard CSS**

Add to `src/customer_issue_agent/static/styles.css`:

```css
.summary-dashboard {
  margin-top: 24px;
}

.summary-loading,
.summary-error {
  margin-top: 16px;
  color: var(--muted);
}

.summary-metrics,
.summary-grid {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.summary-metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.summary-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px;
  background: #fbfcf8;
}

.summary-card span {
  color: var(--muted);
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 28px;
}

.distribution-card strong {
  margin-top: 0;
  font-size: 16px;
}

.distribution-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 14px 0 0;
  list-style: none;
}

.distribution-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
```

Add this inside `@media (max-width: 900px)`:

```css
  .summary-metrics,
  .summary-grid {
    grid-template-columns: 1fr;
  }
```

- [ ] **Step 6: Run dashboard hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_summary_dashboard_region tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks tests/test_app.py::test_styles_cover_summary_dashboard_components -q
```

Expected: PASS.

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
git add src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "feat: add records summary dashboard"
```

## Task 4: README And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with dashboard usage**

Append to `README.md`:

```markdown
## 查看运营概览

工作台会基于当前本地 JSONL 中的全部分析记录生成“运营概览”。概览包含总记录数、已复核数、已修正数，以及问题类型、责任方、证据强度和复核状态分布。

概览用于快速判断客户使用问题集中在哪些方向，不会调用模型，也不会改变原始记录。
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
git commit -m "docs: document records summary dashboard"
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

- Spec coverage: summary API, total/reviewed/corrected counts, issue/responsibility/evidence/feedback distributions, sorted counts, empty records, dashboard markup, JS rendering, CSS styling, README docs, and regression verification are covered.
- Deferred items: time filtering, trend charts, SKU/ASIN dimensions, database migration, BI reports, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder tasks.
- Type consistency: `build_records_summary`, `/api/records/summary`, `records-summary`, `summary-content`, `loadRecordsSummary`, and `renderRecordsSummary` are named consistently across tests and implementation steps.
