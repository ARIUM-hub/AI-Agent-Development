# Platform Distribution Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add platform distribution to the existing operations summary so overseas e-commerce operators can see which platforms produce the most customer usage issues.

**Architecture:** Extend the existing `build_records_summary()` aggregation with a `platforms` distribution sourced from `analysis.request.platform`, then render that distribution in the existing summary dashboard grid. Reuse current record time-range filtering, ranking behavior, and front-end distribution card rendering without adding new APIs, storage changes, or model calls.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, vanilla JavaScript, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-30-platform-distribution-summary-design.md`

## Scope Check

This plan implements only platform distribution in the existing operations summary. It does not normalize platform aliases, alter JSONL history, change analysis or feedback APIs, add platform API integrations, change CSV export behavior, or call model providers.

## File Structure

- Modify: `tests/test_summary.py`
  - Add platform data to the main summary test.
  - Add missing and blank platform coverage in the unknown-value test.
- Modify: `src/customer_issue_agent/summary.py`
  - Add a `platforms` counter.
  - Read platform from `analysis.request.platform`.
  - Return ranked `platforms` in the summary payload.
- Modify: `tests/test_app.py`
  - Assert `/api/records/summary` exposes `platforms`.
  - Assert empty summary includes `platforms: []`.
  - Assert the front-end script references “平台分布” and `summary.platforms`.
- Modify: `src/customer_issue_agent/static/app.js`
  - Render the platform distribution card in the existing summary grid.
- Modify: `README.md`
  - Document that the operations overview includes platform distribution.

## Task 1: Backend Summary Platforms

**Files:**
- Modify: `tests/test_summary.py`
- Modify: `src/customer_issue_agent/summary.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing summary tests**

Modify `tests/test_summary.py` so `test_build_records_summary_counts_totals_and_dimensions` includes platform values under `analysis.request`:

```python
records = [
    {
        "analysis": {
            "request": {"platform": "Amazon"},
            "attribution": {
                "issue_category": "function_use",
                "primary_responsibility": "customer_service_training",
                "evidence_strength": "likely",
            },
        },
        "feedback": {"accepted": True},
    },
    {
        "analysis": {
            "request": {"platform": "TikTok Shop"},
            "attribution": {
                "issue_category": "function_use",
                "primary_responsibility": "product",
                "evidence_strength": "clear",
            },
        },
        "feedback": {"accepted": False},
    },
    {
        "analysis": {
            "request": {"platform": "Amazon"},
            "attribution": {
                "issue_category": "product_fault",
                "primary_responsibility": "product",
                "evidence_strength": "likely",
            },
        },
        "feedback": None,
    },
]
```

Add this assertion after the existing total and review assertions:

```python
assert summary["platforms"] == [
    {"value": "Amazon", "count": 2},
    {"value": "TikTok Shop", "count": 1},
]
```

Modify `test_build_records_summary_handles_empty_and_unknown_values` so the empty summary expected value includes:

```python
"platforms": [],
```

Then replace the single unknown-record check with these records:

```python
summary = build_records_summary(
    [
        {"analysis": {"request": {}, "attribution": {}}, "feedback": None},
        {"analysis": {"request": {"platform": "   "}, "attribution": {}}, "feedback": None},
    ]
)
```

And add this assertion:

```python
assert summary["platforms"] == [{"value": "unknown", "count": 2}]
```

- [ ] **Step 2: Write failing API contract tests**

Modify `tests/test_app.py` in `test_records_summary_endpoint_returns_counts` by adding:

```python
assert payload["platforms"] == [{"value": "Amazon", "count": 1}]
```

Modify `test_records_summary_endpoint_returns_empty_summary` by adding:

```python
assert payload["platforms"] == []
```

Modify `test_records_summary_endpoint_filters_by_time_range` by adding:

```python
assert payload["platforms"] == [{"value": "Amazon", "count": 1}]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_summary.py tests/test_app.py::test_records_summary_endpoint_returns_counts tests/test_app.py::test_records_summary_endpoint_returns_empty_summary tests/test_app.py::test_records_summary_endpoint_filters_by_time_range -q
```

Expected: FAIL with missing `platforms` key in summary payloads.

- [ ] **Step 4: Add platform aggregation**

Modify `src/customer_issue_agent/summary.py`:

```python
def build_records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    platforms: Counter[str] = Counter()
    issue_categories: Counter[str] = Counter()
    responsibilities: Counter[str] = Counter()
    evidence_strengths: Counter[str] = Counter()
    feedback_statuses: Counter[str] = Counter()
    reviewed_records = 0
    corrected_records = 0

    for record in records:
        analysis = record.get("analysis") or {}
        request = analysis.get("request") or {}
        attribution = analysis.get("attribution") or {}
        platforms[_value(request.get("platform"))] += 1
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
        "platforms": _rank(platforms),
        "issue_categories": _rank(issue_categories),
        "responsibilities": _rank(responsibilities),
        "evidence_strengths": _rank(evidence_strengths),
        "feedback_statuses": _rank(feedback_statuses),
    }
```

- [ ] **Step 5: Run backend and API tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_summary.py tests/test_app.py::test_records_summary_endpoint_returns_counts tests/test_app.py::test_records_summary_endpoint_returns_empty_summary tests/test_app.py::test_records_summary_endpoint_filters_by_time_range -q
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/summary.py tests/test_summary.py tests/test_app.py
git commit -m "feat: add platform distribution summary"
```

## Task 2: Dashboard Platform Card

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing front-end hook test**

Modify `test_static_app_js_contains_summary_dashboard_hooks` in `tests/test_app.py` by adding:

```python
assert "平台分布" in script
assert "summary.platforms" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks -q
```

Expected: FAIL because `app.js` does not render `summary.platforms`.

- [ ] **Step 3: Render platform distribution in dashboard**

Modify `renderRecordsSummary(summary)` in `src/customer_issue_agent/static/app.js` so the `summary-grid` includes platform distribution before issue category distribution:

```javascript
    <div class="summary-grid">
      ${summaryDistribution("平台分布", "platform", summary.platforms)}
      ${summaryDistribution("问题类型", "issue_category", summary.issue_categories)}
      ${summaryDistribution("责任方", "responsibility", summary.responsibilities)}
      ${summaryDistribution("证据强度", "evidence", summary.evidence_strengths)}
      ${summaryDistribution("复核状态", "feedback", summary.feedback_statuses)}
    </div>
```

No `labels.platform` mapping is needed because `labelFor()` already returns the original value when a label group does not exist.

- [ ] **Step 4: Run front-end hook test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_summary_dashboard_hooks -q
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
git add src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: show platform distribution in dashboard"
```

## Task 3: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README operations overview**

Modify the “查看运营概览” section in `README.md` so this sentence:

```markdown
工作台会基于当前本地 JSONL 中的全部分析记录生成“运营概览”。概览包含总记录数、已复核数、已修正数，以及问题类型、责任方、证据强度和复核状态分布。
```

Becomes:

```markdown
工作台会基于当前本地 JSONL 中的全部分析记录生成“运营概览”。概览包含总记录数、已复核数、已修正数，以及平台、问题类型、责任方、证据强度和复核状态分布。
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
git commit -m "docs: document platform distribution summary"
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

- Spec coverage: backend `platforms` aggregation, unknown platform handling, API response contract, existing time range behavior, dashboard card, README docs, and full regression verification are covered.
- Deferred items: alias normalization, JSONL migration, API reshaping, CSV changes, platform API integrations, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `platforms`, `summary.platforms`, `analysis.request.platform`, and “平台分布” are named consistently across tests, implementation, and documentation.
