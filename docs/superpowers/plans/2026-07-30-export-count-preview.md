# Export Count Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在筛选导出前显示与真实 CSV 导出口径一致的预计导出记录数。

**Architecture:** 新增轻量后端计数接口 `GET /api/records/export-count`，复用现有 `filter_records()`，保证数量与 CSV 导出筛选逻辑一致。前端新增只读数量提示区，复用导出参数构建逻辑异步请求数量，并用请求序号避免旧响应覆盖新输入。

**Tech Stack:** FastAPI、Jinja2、原生 JavaScript、CSS、pytest + TestClient。

---

## File Structure

- `tests/test_app.py`：新增后端计数接口测试，扩展 HTML/JS/CSS 静态 hook 测试。
- `src/customer_issue_agent/app.py`：新增 `/api/records/export-count` endpoint，并复用 `filter_records()`。
- `src/customer_issue_agent/templates/index.html`：在 `#export-filter-summary` 附近新增 `#export-count-preview`。
- `src/customer_issue_agent/static/app.js`：抽出 `buildExportFilterParams()`，新增 `buildExportCountPreviewUrl()` 和 `updateExportCountPreview()`，并接入现有筛选触发点。
- `src/customer_issue_agent/static/styles.css`：为 `.export-count-preview` 增加与导出提示一致的轻量样式。
- `README.md`：说明预计导出数量来自后端真实导出口径。

## Task 1: Add Export Count API

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/app.py`

- [ ] **Step 1: Write the failing backend API tests**

In `tests/test_app.py`, add these tests after `test_export_records_csv_endpoint_filters_by_time_range_and_query`:

```python
def test_export_records_count_endpoint_matches_filtered_export_scope(tmp_path):
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

    response = client.get("/api/records/export-count", params={"range": "30d", "platform": "amazon"})

    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_export_records_count_endpoint_returns_zero_for_empty_filter_result(tmp_path):
    storage_path = tmp_path / "analyses.jsonl"
    _write_jsonl_records(
        storage_path,
        [
            _stored_record("amazon", platform="Amazon", created_at=datetime.now(UTC)),
        ],
    )
    app = create_app(storage_path=storage_path)
    client = TestClient(app)

    response = client.get("/api/records/export-count", params={"feedback_status": "archived"})

    assert response.status_code == 200
    assert response.json() == {"count": 0}
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_export_records_count_endpoint_matches_filtered_export_scope tests/test_app.py::test_export_records_count_endpoint_returns_zero_for_empty_filter_result -q
```

Expected: FAIL with HTTP 404 because `/api/records/export-count` does not exist yet.

- [ ] **Step 3: Add the minimal endpoint**

In `src/customer_issue_agent/app.py`, add this route after `export_records_csv()` and before `records_summary()`:

```python
    @app.get("/api/records/export-count")
    async def export_records_count(
        platform: str = "",
        issue_category: str = "",
        responsibility: str = "",
        feedback_status: str = "",
        q: str = "",
        range: str = "all",
    ) -> dict:
        records = filter_records(
            store.list_records(),
            platform=platform,
            issue_category=issue_category,
            responsibility=responsibility,
            feedback_status=feedback_status,
            q=q,
            range=range,
        )
        return {"count": len(records)}
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_export_records_count_endpoint_matches_filtered_export_scope tests/test_app.py::test_export_records_count_endpoint_returns_zero_for_empty_filter_result -q
```

Expected: PASS.

- [ ] **Step 5: Commit backend API**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/app.py
git commit -m "feat: add filtered export count endpoint"
```

## Task 2: Add Export Count Preview Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write the failing HTML test**

Update `tests/test_app.py::test_index_contains_recent_record_filter_controls` by appending:

```python
    assert 'id="export-count-preview"' in html
    assert 'class="export-count-preview"' in html
    assert "预计导出数量加载中..." in html
```

The existing test already asserts `aria-live="polite"` for this page; keep that assertion and do not remove the existing `#export-filter-summary` checks.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_recent_record_filter_controls -q
```

Expected: FAIL because `id="export-count-preview"` is not present in the rendered HTML.

- [ ] **Step 3: Add the minimal template markup**

In `src/customer_issue_agent/templates/index.html`, add the preview paragraph immediately after `#export-filter-summary`:

```html
            <p id="export-filter-summary" class="export-filter-summary" aria-live="polite">将导出全部记录</p>
            <p id="export-count-preview" class="export-count-preview" aria-live="polite">预计导出数量加载中...</p>
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
git commit -m "feat: add export count preview markup"
```

## Task 3: Add Export Count Preview JavaScript

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write the failing JS hook tests**

Update `tests/test_app.py::test_static_app_js_contains_filtered_export_hooks` by appending:

```python
    assert "buildExportFilterParams" in script
    assert "buildExportCountPreviewUrl" in script
    assert "updateExportCountPreview" in script
    assert "/api/records/export-count" in script
    assert "export-count-preview" in script
    assert "预计导出" in script
    assert "预计数量暂不可用" in script
    assert "latestExportCountRequestId" in script
```

Update `tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks` by appending:

```python
    assert "updateExportCountPreview();" in script
```

Update `tests/test_app.py::test_static_app_js_contains_summary_range_hooks` by appending:

```python
    assert "updateExportCountPreview();" in script
```

- [ ] **Step 2: Run the JS hook tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_filtered_export_hooks tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
```

Expected: FAIL because count preview URL building, request handling, and strings do not exist yet.

- [ ] **Step 3: Add a shared export params helper**

In `src/customer_issue_agent/static/app.js`, add this variable near the top after the `labels` constant:

```javascript
let latestExportCountRequestId = 0;
```

Replace the body of `buildFilteredExportUrl()` with a call to a new helper, and place the helper before `buildFilteredExportUrl()`:

```javascript
function buildExportFilterParams() {
  const params = new URLSearchParams();
  const summaryRange = document.getElementById("summary-range")?.value || "all";
  const query = document.getElementById("record-search")?.value.trim() || "";
  const platform = document.getElementById("platform-filter")?.value.trim() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";

  if (summaryRange !== "all") {
    params.set("range", summaryRange);
  }
  if (query) {
    params.set("q", query);
  }
  if (platform) {
    params.set("platform", platform);
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
  return params;
}

function buildFilteredExportUrl() {
  const params = buildExportFilterParams();
  const queryString = params.toString();
  return queryString ? `/api/records/export.csv?${queryString}` : "/api/records/export.csv";
}

function buildExportCountPreviewUrl() {
  const params = buildExportFilterParams();
  const queryString = params.toString();
  return queryString ? `/api/records/export-count?${queryString}` : "/api/records/export-count";
}
```

- [ ] **Step 4: Add async count preview updater**

In `src/customer_issue_agent/static/app.js`, add this function after `updateExportFilterSummary()`:

```javascript
async function updateExportCountPreview() {
  const preview = document.getElementById("export-count-preview");
  if (!preview) {
    return;
  }

  const requestId = latestExportCountRequestId + 1;
  latestExportCountRequestId = requestId;
  preview.textContent = "预计导出数量加载中...";

  try {
    const response = await fetch(buildExportCountPreviewUrl());
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    if (requestId !== latestExportCountRequestId) {
      return;
    }
    preview.textContent = `预计导出 ${payload.count} 条`;
  } catch (error) {
    if (requestId === latestExportCountRequestId) {
      preview.textContent = "预计数量暂不可用";
    }
  }
}
```

- [ ] **Step 5: Wire the updater into existing triggers**

In `bindSummaryRange()`, update the change listener:

```javascript
  select.addEventListener("change", () => {
    loadRecordsSummary();
    updateExportFilterSummary();
    updateExportCountPreview();
  });
```

In `applySummaryPlatformFilter(platform)`, call count preview after updating the summary:

```javascript
  input.value = value;
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
```

In `bindRecordFilters()`, update both `input` and `change` listeners:

```javascript
  form.addEventListener("input", () => {
    applyRecordFilters();
    updateExportFilterSummary();
    updateExportCountPreview();
  });
  form.addEventListener("change", () => {
    applyRecordFilters();
    updateExportFilterSummary();
    updateExportCountPreview();
  });
```

At the end of `bindRecordFilters()`, initialize both hints:

```javascript
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
```

In `resetRecordFilters(form)`, refresh count after resetting:

```javascript
function resetRecordFilters(form) {
  form.reset();
  applyRecordFilters();
  updateExportFilterSummary();
  updateExportCountPreview();
}
```

- [ ] **Step 6: Run the JS hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_static_app_js_contains_filtered_export_hooks tests/test_app.py::test_static_app_js_contains_recent_record_filter_hooks tests/test_app.py::test_static_app_js_contains_summary_range_hooks -q
```

Expected: PASS.

- [ ] **Step 7: Commit JavaScript behavior**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/static/app.js
git commit -m "feat: preview filtered export count"
```

## Task 4: Style the Export Count Preview

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write the failing CSS hook test**

Update `tests/test_app.py::test_styles_cover_recent_record_filter_components` by appending:

```python
    assert ".export-count-preview" in css
```

- [ ] **Step 2: Run the focused CSS test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_styles_cover_recent_record_filter_components -q
```

Expected: FAIL because `.export-count-preview` is not present in `styles.css`.

- [ ] **Step 3: Add CSS for the preview**

In `src/customer_issue_agent/static/styles.css`, update the shared muted text selector:

```css
.filter-field span,
.filter-count,
.export-filter-summary,
.export-count-preview {
  color: var(--muted);
  font-size: 13px;
}
```

Add a dedicated block after `.export-filter-summary`:

```css
.export-count-preview {
  grid-column: 1 / -1;
  margin: -4px 0 0;
  color: var(--ink);
  font-weight: 700;
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
git commit -m "style: highlight export count preview"
```

## Task 5: Document and Verify

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

In `README.md` under `## 导出分析记录`, replace the paragraph:

```markdown
如果只想导出某一组记录，可以先在“最近记录”筛选栏设置平台、关键词、问题类型、责任方或复核状态，然后点击 `导出筛选 CSV`。按钮附近会先显示本次筛选导出将应用的条件；筛选导出由服务端基于全部本地 JSONL 记录执行，不限于页面当前展示的最近 10 条。原有 `导出 CSV` 仍始终导出全部记录。
```

With:

```markdown
如果只想导出某一组记录，可以先在“最近记录”筛选栏设置平台、关键词、问题类型、责任方或复核状态，然后点击 `导出筛选 CSV`。按钮附近会先显示本次筛选导出将应用的条件和预计导出数量；预计数量由后端按真实导出口径基于全部本地 JSONL 记录计算，不限于页面当前展示的最近 10 条。原有 `导出 CSV` 仍始终导出全部记录。
```

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: PASS with all existing tests plus the export count preview tests.

- [ ] **Step 3: Review the diff for accidental scope creep**

Run:

```powershell
git diff -- src/customer_issue_agent/app.py src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/app.js src/customer_issue_agent/static/styles.css tests/test_app.py README.md
```

Expected: Diff only contains export count endpoint, count preview UI, tests, CSS, and README wording. No CSV response format, JSONL storage, model-provider, old-repo, or unrelated feature changes are present.

- [ ] **Step 4: Commit documentation**

Run:

```powershell
git add README.md
git commit -m "docs: describe export count preview"
```

- [ ] **Step 5: Final verification before push**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
git status --short --branch
python -m pytest -q
gh pr view 2 --repo ARIUM-hub/Agent-Operations-Workflow --json number,state,headRefName,url,title
git log --oneline -8
```

Expected:

```text
## codex/customer-issue-agent-mvp
```

`python -m pytest -q` passes, PR #2 remains open on `codex/customer-issue-agent-mvp`, and recent commits include the export count preview spec, plan, and implementation commits.

- [ ] **Step 6: Push the branch**

Run:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: Push succeeds and PR #2 updates.

## Self-Review

- Spec coverage: Task 1 implements the true backend count endpoint with the same query params and `filter_records()` reuse. Task 2 adds the read-only preview region. Task 3 handles URL sharing, async fetch, initialization, input/change, reset, time range, platform drilldown, failure fallback, and stale response protection. Task 4 styles the preview. Task 5 updates README, runs full verification, checks scope, and pushes the existing PR branch.
- Placeholder scan: The plan contains no unfinished requirement markers, vague implementation instructions, or references to undefined production functions. Each code-changing step includes exact snippets and commands.
- Type and name consistency: The plan consistently uses `export_records_count`, `buildExportFilterParams`, `buildExportCountPreviewUrl`, `updateExportCountPreview`, `latestExportCountRequestId`, `export-count-preview`, and `/api/records/export-count`.
