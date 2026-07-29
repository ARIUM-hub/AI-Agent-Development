# Records Time Range Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight `all`/`7d`/`30d` time range filtering to records summary and CSV export.

**Architecture:** Extend the existing `record_filters.filter_records()` module with a reusable time-range criterion based on each record's `created_at` timestamp. Reuse that same filter in both `/api/records/summary` and `/api/records/export.csv`, then add a single summary range selector in the workbench that also feeds the filtered CSV export URL.

**Tech Stack:** Python 3.12, FastAPI, vanilla JavaScript, Jinja2 templates, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-records-time-range-filter-design.md`

## Scope Check

This plan implements only preset time ranges for existing records. It does not add custom dates, trend charts, timezone configuration UI, database indexes, async reports, or model calls.

## File Structure

- Modify: `src/customer_issue_agent/record_filters.py`
  - Add `range` and test-only `now` parameters to the existing filter function.
- Modify: `tests/test_record_filters.py`
  - Add unit coverage for `all`, `7d`, `30d`, unknown ranges, and invalid timestamps.
- Modify: `src/customer_issue_agent/app.py`
  - Pass `range` into summary and CSV export filtering.
- Modify: `tests/test_app.py`
  - Add API tests for summary and CSV range filtering plus UI hook tests.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add a summary time-range selector.
- Modify: `src/customer_issue_agent/static/app.js`
  - Load summary with selected range, bind range changes, and include range in filtered export URLs.
- Modify: `README.md`
  - Document time-range behavior.

## Task 1: Time Range Filtering In Record Filter Module

**Files:**
- Modify: `src/customer_issue_agent/record_filters.py`
- Modify: `tests/test_record_filters.py`

- [ ] **Step 1: Write failing time range filter tests**

Append to `tests/test_record_filters.py`:

```python
from datetime import UTC, datetime


def test_filter_records_matches_recent_7_day_range():
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    records = [
        {**_record("recent"), "created_at": "2026-07-25T12:00:00+00:00"},
        {**_record("old"), "created_at": "2026-07-10T12:00:00+00:00"},
    ]

    filtered = filter_records(records, range="7d", now=now)

    assert [record["id"] for record in filtered] == ["recent"]


def test_filter_records_matches_recent_30_day_range():
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    records = [
        {**_record("recent"), "created_at": "2026-07-01T12:00:00+00:00"},
        {**_record("old"), "created_at": "2026-06-01T12:00:00+00:00"},
    ]

    filtered = filter_records(records, range="30d", now=now)

    assert [record["id"] for record in filtered] == ["recent"]


def test_filter_records_all_and_unknown_range_keep_existing_behavior():
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    records = [
        {**_record("missing-created-at")},
        {**_record("invalid-created-at"), "created_at": "not-a-date"},
    ]

    assert filter_records(records, range="all", now=now) == records
    assert filter_records(records, range="custom", now=now) == records


def test_filter_records_active_range_excludes_missing_or_invalid_created_at():
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    records = [
        {**_record("missing-created-at")},
        {**_record("invalid-created-at"), "created_at": "not-a-date"},
    ]

    assert filter_records(records, range="7d", now=now) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_record_filters.py -q
```

Expected: FAIL with `TypeError: filter_records() got an unexpected keyword argument 'range'`.

- [ ] **Step 3: Implement time range filtering**

Modify `src/customer_issue_agent/record_filters.py`:

```python
from datetime import UTC, datetime, timedelta
```

Update `filter_records()`:

```python
def filter_records(
    records: list[dict[str, Any]],
    *,
    platform: str = "",
    issue_category: str = "",
    responsibility: str = "",
    feedback_status: str = "",
    q: str = "",
    range: str = "all",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    filters = {
        "platform": _clean(platform),
        "issue_category": _clean(issue_category),
        "responsibility": _clean(responsibility),
        "feedback_status": _clean(feedback_status),
        "q": _clean(q),
        "range": _range_value(range),
    }
    if not any(value for key, value in filters.items() if key != "range") and filters["range"] == "all":
        return records
    current_time = now or datetime.now(UTC)
    return [record for record in records if _matches(record, filters, current_time)]
```

Update `_matches()` signature and body:

```python
def _matches(record: dict[str, Any], filters: dict[str, str], now: datetime) -> bool:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}

    if filters["range"] != "all" and not _matches_range(record, filters["range"], now):
        return False
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
```

Add helpers above `_feedback_status()`:

```python
def _matches_range(record: dict[str, Any], range_value: str, now: datetime) -> bool:
    created_at = _parse_created_at(record.get("created_at"))
    if created_at is None:
        return False
    days = 7 if range_value == "7d" else 30
    return created_at >= now - timedelta(days=days)


def _parse_created_at(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _range_value(value: object) -> str:
    cleaned = _clean(value)
    return cleaned if cleaned in {"7d", "30d"} else "all"
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
git commit -m "feat: filter records by time range"
```

## Task 2: API Time Range Support

**Files:**
- Modify: `src/customer_issue_agent/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_app.py`:

```python
import json
from datetime import UTC, datetime, timedelta


def _stored_record(record_id: str, *, platform: str, created_at: datetime, issue_category: str = "function_use") -> dict:
    return {
        "id": record_id,
        "created_at": created_at.isoformat(),
        "analysis": {
            "request": {"platform": platform, "conversation_text": "Customer: not working"},
            "attribution": {
                "customer_problem": f"{platform} 客户反馈无法使用",
                "issue_category": issue_category,
                "root_causes": ["unclear_instructions"],
                "primary_responsibility": "customer_service_training",
                "evidence_strength": "likely",
                "recommended_actions": ["补问设备型号"],
                "missing_information": ["错误提示截图"],
            },
            "report": f"{platform} 客户反馈无法使用",
        },
        "feedback": None,
    }


def _write_jsonl_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_records_summary_endpoint_filters_by_time_range(tmp_path):
    storage_path = tmp_path / "analyses.jsonl"
    now = datetime.now(UTC)
    _write_jsonl_records(
        storage_path,
        [
            _stored_record("recent", platform="Amazon", created_at=now - timedelta(days=2)),
            _stored_record("old", platform="TikTok Shop", created_at=now - timedelta(days=40)),
        ],
    )
    app = create_app(storage_path=storage_path)
    client = TestClient(app)

    response = client.get("/api/records/summary", params={"range": "7d"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 1
    assert payload["issue_categories"] == [{"value": "function_use", "count": 1}]


def test_export_records_csv_endpoint_filters_by_time_range_and_query(tmp_path):
    storage_path = tmp_path / "analyses.jsonl"
    now = datetime.now(UTC)
    _write_jsonl_records(
        storage_path,
        [
            _stored_record("recent-amazon", platform="Amazon", created_at=now - timedelta(days=2)),
            _stored_record("recent-tiktok", platform="TikTok Shop", created_at=now - timedelta(days=2)),
            _stored_record("old-amazon", platform="Amazon", created_at=now - timedelta(days=40)),
        ],
    )
    app = create_app(storage_path=storage_path)
    client = TestClient(app)

    response = client.get("/api/records/export.csv", params={"range": "30d", "platform": "amazon"})

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert "recent-amazon" in text
    assert "recent-tiktok" not in text
    assert "old-amazon" not in text
```

If `tests/test_app.py` already has imports after test functions, move the new imports to the top of the file before running the tests:

```python
import json
from datetime import UTC, datetime, timedelta
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_records_summary_endpoint_filters_by_time_range tests/test_app.py::test_export_records_csv_endpoint_filters_by_time_range_and_query -q
```

Expected: FAIL because summary ignores `range` and CSV export does not pass `range` into `filter_records()`.

- [ ] **Step 3: Add API range parameters**

Modify `src/customer_issue_agent/app.py`:

```python
    @app.get("/api/records/export.csv")
    async def export_records_csv(
        platform: str = "",
        issue_category: str = "",
        responsibility: str = "",
        feedback_status: str = "",
        q: str = "",
        range: str = "all",
    ) -> Response:
        records = filter_records(
            store.list_records(),
            platform=platform,
            issue_category=issue_category,
            responsibility=responsibility,
            feedback_status=feedback_status,
            q=q,
            range=range,
        )
```

Modify summary endpoint:

```python
    @app.get("/api/records/summary")
    async def records_summary(range: str = "all") -> dict:
        return build_records_summary(filter_records(store.list_records(), range=range))
```

- [ ] **Step 4: Run API tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_records_summary_endpoint_filters_by_time_range tests/test_app.py::test_export_records_csv_endpoint_filters_by_time_range_and_query tests/test_app.py::test_records_summary_endpoint_returns_counts tests/test_app.py::test_export_records_csv_endpoint_filters_by_query_params -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/app.py tests/test_app.py
git commit -m "feat: apply time range to records APIs"
```

## Task 3: Summary Range Selector And Export URL

**Files:**
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/app.js`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing UI hook tests**

Append to `tests/test_app.py`:

```python
def test_index_contains_summary_range_selector(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="summary-range"' in html
    assert 'value="7d"' in html
    assert 'value="30d"' in html
    assert "最近 7 天" in html


def test_static_app_js_contains_summary_range_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindSummaryRange" in script
    assert "summary-range" in script
    assert 'params.set("range", range)' in script
    assert 'params.set("range", summaryRange)' in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_summary_range_selector tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
```

Expected: FAIL because the range selector and JS hooks do not exist.

- [ ] **Step 3: Add summary range selector markup**

Modify `src/customer_issue_agent/templates/index.html` inside the `records-summary` section heading, replacing the current status span:

```html
            <label class="summary-range" for="summary-range">
              <span>时间范围</span>
              <select id="summary-range" name="range">
                <option value="all">全部记录</option>
                <option value="7d">最近 7 天</option>
                <option value="30d">最近 30 天</option>
              </select>
            </label>
```

- [ ] **Step 4: Add JavaScript range hooks**

Modify the DOMContentLoaded callback in `src/customer_issue_agent/static/app.js`:

```javascript
  bindSummaryRange();
  loadRecordsSummary();
```

Replace the old standalone `loadRecordsSummary();` call so it is not duplicated.

Update `loadRecordsSummary()`:

```javascript
async function loadRecordsSummary() {
  const container = document.getElementById("summary-content");
  if (!container) {
    return;
  }

  const range = document.getElementById("summary-range")?.value || "all";
  const params = new URLSearchParams();
  params.set("range", range);

  try {
    const response = await fetch(`/api/records/summary?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderRecordsSummary(payload);
  } catch (error) {
    container.innerHTML = `<p class="summary-error">${escapeHtml(error.message || "概览加载失败，请刷新页面重试。")}</p>`;
  }
}
```

Add function above `loadRecordsSummary()`:

```javascript
function bindSummaryRange() {
  const select = document.getElementById("summary-range");
  if (!select) {
    return;
  }

  select.addEventListener("change", () => {
    loadRecordsSummary();
  });
}
```

Update `buildFilteredExportUrl()` after creating `params`:

```javascript
  const summaryRange = document.getElementById("summary-range")?.value || "all";
  if (summaryRange !== "all") {
    params.set("range", summaryRange);
  }
```

- [ ] **Step 5: Run UI hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_summary_range_selector tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
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
git commit -m "feat: add records time range controls"
```

## Task 4: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Append this paragraph to the “查看运营概览” section in `README.md`:

```markdown
运营概览支持选择 `全部记录`、`最近 7 天` 和 `最近 30 天`。时间范围基于每条本地记录的 `created_at` 判断；切换范围只影响概览统计和 `导出筛选 CSV` 的默认时间条件，不会修改 JSONL 原始记录。
```

Append this sentence to the “导出分析记录” section:

```markdown
如果在运营概览中选择了最近 7 天或最近 30 天，`导出筛选 CSV` 会同时带上该时间范围；`导出 CSV` 仍导出全部记录。
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
git commit -m "docs: document records time range filtering"
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

- Spec coverage: `all`/`7d`/`30d`, summary API range, CSV export range, range plus existing filters, invalid timestamps, unknown ranges, UI selector, filtered export URL, README docs, and regression verification are covered.
- Deferred items: custom dates, trend charts, timezone UI, database indexes, async reports, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `range`, `filter_records`, `now`, `summary-range`, `bindSummaryRange`, and `buildFilteredExportUrl` are named consistently across tasks.
