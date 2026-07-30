# Filtered CSV Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add filtered CSV export for all saved customer issue analysis records while preserving the existing full export.

**Architecture:** Add a focused Python filter module that accepts JSON-ready record dictionaries plus query criteria and returns matching records. Reuse the existing CSV builder and endpoint, adding optional query parameters before rendering CSV. Add one progressive-enhancement button in the existing filter bar that builds a download URL from current filter controls.

**Tech Stack:** Python 3.12, FastAPI, vanilla JavaScript, CSS, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-filtered-csv-export-design.md`

## Scope Check

This plan implements only filtered CSV export. It does not add `.xlsx`, saved filters, pagination, database queries, async exports, time filters, or model calls.

## File Structure

- Create: `src/customer_issue_agent/record_filters.py`
  - Filters analysis record dictionaries by platform, issue category, responsibility, feedback status, and keyword.
- Create: `tests/test_record_filters.py`
  - Covers filter behavior independently from FastAPI and CSV rendering.
- Modify: `src/customer_issue_agent/app.py`
  - Adds optional query parameters to `GET /api/records/export.csv`.
- Modify: `tests/test_app.py`
  - Covers filtered CSV API behavior and front-end hooks.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Adds the “导出筛选 CSV” button to the existing record filter bar.
- Modify: `src/customer_issue_agent/static/app.js`
  - Adds click handler that builds the filtered export URL from current controls.
- Modify: `README.md`
  - Documents full export vs filtered export semantics.

## Task 1: Record Filter Module

**Files:**
- Create: `src/customer_issue_agent/record_filters.py`
- Create: `tests/test_record_filters.py`

- [ ] **Step 1: Write failing filter tests**

Create `tests/test_record_filters.py`:

```python
from customer_issue_agent.record_filters import filter_records


def _record(
    record_id: str,
    *,
    platform: str = "Amazon",
    issue_category: str = "function_use",
    responsibility: str = "customer_service_training",
    evidence_strength: str = "likely",
    report: str = "客户反馈无法连接，客服需要补问设备型号。",
    feedback: dict | None = None,
) -> dict:
    return {
        "id": record_id,
        "analysis": {
            "request": {"platform": platform},
            "attribution": {
                "customer_problem": report,
                "issue_category": issue_category,
                "primary_responsibility": responsibility,
                "evidence_strength": evidence_strength,
                "recommended_actions": ["补问设备型号"],
                "missing_information": ["错误提示截图"],
            },
            "report": report,
        },
        "feedback": feedback,
    }


def test_filter_records_returns_all_when_no_filters():
    records = [_record("one"), _record("two", platform="TikTok Shop")]

    assert filter_records(records) == records


def test_filter_records_matches_platform_keyword_case_insensitively():
    records = [_record("one", platform="Amazon"), _record("two", platform="TikTok Shop")]

    filtered = filter_records(records, platform="amazon")

    assert [record["id"] for record in filtered] == ["one"]


def test_filter_records_matches_enums_and_feedback_status():
    records = [
        _record("one", issue_category="function_use", responsibility="customer_service_training"),
        _record(
            "two",
            issue_category="product_fault",
            responsibility="product",
            feedback={"accepted": False, "note": "质量团队复核"},
        ),
        _record("three", issue_category="product_fault", responsibility="product", feedback={"accepted": True}),
    ]

    filtered = filter_records(
        records,
        issue_category="product_fault",
        responsibility="product",
        feedback_status="corrected",
    )

    assert [record["id"] for record in filtered] == ["two"]


def test_filter_records_searches_record_text_and_feedback_note():
    records = [
        _record("one", report="客户反馈安装失败"),
        _record("two", report="客户反馈缺少配件", feedback={"accepted": False, "note": "需要配件补发"}),
    ]

    assert [record["id"] for record in filter_records(records, q="安装")] == ["one"]
    assert [record["id"] for record in filter_records(records, q="补发")] == ["two"]


def test_filter_records_unknown_feedback_status_matches_nothing():
    records = [_record("one"), _record("two", feedback={"accepted": True})]

    assert filter_records(records, feedback_status="archived") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_record_filters.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'customer_issue_agent.record_filters'`.

- [ ] **Step 3: Implement filter module**

Create `src/customer_issue_agent/record_filters.py`:

```python
from __future__ import annotations

from typing import Any


def filter_records(
    records: list[dict[str, Any]],
    *,
    platform: str = "",
    issue_category: str = "",
    responsibility: str = "",
    feedback_status: str = "",
    q: str = "",
) -> list[dict[str, Any]]:
    filters = {
        "platform": _clean(platform),
        "issue_category": _clean(issue_category),
        "responsibility": _clean(responsibility),
        "feedback_status": _clean(feedback_status),
        "q": _clean(q),
    }
    if not any(filters.values()):
        return records
    return [record for record in records if _matches(record, filters)]


def _matches(record: dict[str, Any], filters: dict[str, str]) -> bool:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}

    if filters["platform"] and filters["platform"] not in _clean(request.get("platform")):
        return False
    if filters["issue_category"] and filters["issue_category"] != _clean(attribution.get("issue_category")):
        return False
    if filters["responsibility"] and filters["responsibility"] != _clean(attribution.get("primary_responsibility")):
        return False
    if filters["feedback_status"] and filters["feedback_status"] != _feedback_status(record.get("feedback")):
        return False
    if filters["q"] and filters["q"] not in _search_text(record):
        return False
    return True


def _feedback_status(feedback: object) -> str:
    if not isinstance(feedback, dict):
        return "unreviewed"
    return "accepted" if feedback.get("accepted") else "corrected"


def _search_text(record: dict[str, Any]) -> str:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}
    feedback = record.get("feedback") or {}
    values = [
        record.get("id"),
        request.get("platform"),
        analysis.get("report"),
        attribution.get("customer_problem"),
        attribution.get("issue_category"),
        attribution.get("primary_responsibility"),
        attribution.get("evidence_strength"),
        attribution.get("recommended_actions"),
        attribution.get("missing_information"),
        feedback.get("note"),
    ]
    return _clean(" ".join(_flatten(values)))


def _flatten(values: list[object]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        elif value is not None:
            flattened.append(str(value))
    return flattened


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
```

- [ ] **Step 4: Run filter tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_record_filters.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/record_filters.py tests/test_record_filters.py
git commit -m "feat: filter analysis records for export"
```

## Task 2: Filtered CSV API

**Files:**
- Modify: `src/customer_issue_agent/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_app.py`:

```python
def test_export_records_csv_endpoint_filters_by_query_params(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    amazon_response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    tiktok_response = client.post(
        "/api/analyze",
        data={"platform": "TikTok Shop", "conversation_text": "Customer: missing cable"},
    )
    client.post(
        f"/api/records/{amazon_response.json()['record_id']}/feedback",
        data={"accepted": "false", "note": "需要产品团队复核"},
    )
    client.post(
        f"/api/records/{tiktok_response.json()['record_id']}/feedback",
        data={"accepted": "true"},
    )

    response = client.get(
        "/api/records/export.csv",
        params={"platform": "amazon", "feedback_status": "corrected", "q": "产品团队"},
    )

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert "Amazon" in text
    assert "TikTok Shop" not in text
    assert "需要产品团队复核" in text


def test_export_records_csv_endpoint_filtered_empty_returns_header(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )

    response = client.get("/api/records/export.csv", params={"feedback_status": "archived"})

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 1
    assert lines[0].startswith("记录 ID,创建时间,平台")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_export_records_csv_endpoint_filters_by_query_params tests/test_app.py::test_export_records_csv_endpoint_filtered_empty_returns_header -q
```

Expected: FAIL because the endpoint ignores query parameters and still exports all records.

- [ ] **Step 3: Add query parameters to endpoint**

Modify imports in `src/customer_issue_agent/app.py`:

```python
from customer_issue_agent.record_filters import filter_records
```

Modify the endpoint:

```python
    @app.get("/api/records/export.csv")
    async def export_records_csv(
        platform: str = "",
        issue_category: str = "",
        responsibility: str = "",
        feedback_status: str = "",
        q: str = "",
    ) -> Response:
        records = filter_records(
            store.list_records(),
            platform=platform,
            issue_category=issue_category,
            responsibility=responsibility,
            feedback_status=feedback_status,
            q=q,
        )
        return Response(
            content=build_records_csv(records),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=customer-issue-records.csv"},
        )
```

- [ ] **Step 4: Run API tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_export_records_csv_endpoint_filters_by_query_params tests/test_app.py::test_export_records_csv_endpoint_filtered_empty_returns_header tests/test_app.py::test_export_records_csv_endpoint_returns_bom_csv_with_feedback -q
```

Expected: all selected tests pass, including the existing full export regression.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/app.py tests/test_app.py
git commit -m "feat: filter records csv export"
```

## Task 3: Filtered Export UI

**Files:**
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/app.js`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing UI hook tests**

Append to `tests/test_app.py`:

```python
def test_index_contains_filtered_export_button(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "导出筛选 CSV" in html
    assert "data-filter-export" in html


def test_static_app_js_contains_filtered_export_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindFilteredExport" in script
    assert "buildFilteredExportUrl" in script
    assert "data-filter-export" in script
    assert "feedback_status" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_filtered_export_button tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
```

Expected: FAIL because the button and JS hooks do not exist.

- [ ] **Step 3: Add button markup**

Modify the record filter form in `src/customer_issue_agent/templates/index.html`, near the existing reset button:

```html
            <button class="secondary-action" type="button" data-filter-export>导出筛选 CSV</button>
            <button class="secondary-action" type="button" data-filter-reset>清空</button>
```

- [ ] **Step 4: Add JavaScript hooks**

Modify the DOMContentLoaded callback in `src/customer_issue_agent/static/app.js`:

```javascript
  bindFilteredExport();
```

Add these functions near `bindRecordFilters()`:

```javascript
function bindFilteredExport() {
  const button = document.querySelector("[data-filter-export]");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => {
    window.location.href = buildFilteredExportUrl();
  });
}

function buildFilteredExportUrl() {
  const params = new URLSearchParams();
  const query = document.getElementById("record-search")?.value.trim() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";

  if (query) {
    params.set("q", query);
  }
  if (issue) {
    params.set("issue_category", issue);
  }
  if (responsibility) {
    params.set("responsibility", responsibility);
  }
  if (feedback) {
    params.set("feedback_status", feedback);
  }

  const queryString = params.toString();
  return queryString ? `/api/records/export.csv?${queryString}` : "/api/records/export.csv";
}
```

- [ ] **Step 5: Run UI hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_filtered_export_button tests/test_app.py::test_static_app_js_contains_filtered_export_hooks -q
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
git add src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: add filtered csv export button"
```

## Task 4: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Append to the export section in `README.md`:

```markdown
如果只想导出某一组记录，可以先在“最近记录”筛选栏设置关键词、问题类型、责任方或复核状态，然后点击 `导出筛选 CSV`。筛选导出由服务端基于全部本地 JSONL 记录执行，不限于页面当前展示的最近 10 条；原有 `导出 CSV` 仍始终导出全部记录。
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
git commit -m "docs: document filtered csv export"
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

- Spec coverage: query-parameter filtered CSV, full JSONL scope, platform/issue/responsibility/feedback/q filters, unchanged full export, filtered button, empty result CSV, README docs, and regression verification are covered.
- Deferred items: `.xlsx`, saved filters, pagination, async exports, database queries, time filters, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `filter_records`, `platform`, `issue_category`, `responsibility`, `feedback_status`, `q`, `bindFilteredExport`, and `buildFilteredExportUrl` are named consistently across tasks.
