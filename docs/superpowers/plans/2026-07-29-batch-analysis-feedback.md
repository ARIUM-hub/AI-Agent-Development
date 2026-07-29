# Batch Analysis Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight batch file analysis and human feedback correction for customer issue attribution records.

**Architecture:** Keep the current FastAPI single-page workbench and JSONL storage. Extend ingestion with a small batch splitter, extend storage with append-only feedback events, then expose two API endpoints that the existing vanilla JavaScript UI can progressively enhance.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, openpyxl, Jinja2, vanilla JavaScript, CSS, pytest, httpx.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-batch-analysis-feedback-design.md`

## Scope Check

The approved spec contains two tightly coupled capabilities: batch analysis creates multiple records, and feedback lets users review those records. Both depend on the existing analysis pipeline and JSONL store, so they belong in one implementation plan. Queueing, login, model calls, report exports, and trend dashboards remain outside this plan.

## File Structure

- Modify: `src/customer_issue_agent/ingestion.py`
  - Add `extract_batch_conversation_texts()` for text, CSV, and Excel batch splitting.
- Modify: `src/customer_issue_agent/storage.py`
  - Add feedback event persistence and latest-feedback merging.
- Modify: `src/customer_issue_agent/app.py`
  - Add `/api/analyze-batch-file` and `/api/records/{record_id}/feedback`.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add batch upload tab and feedback controls in result/record cards.
- Modify: `src/customer_issue_agent/static/app.js`
  - Add batch submit, result list rendering, and feedback submit behavior.
- Modify: `src/customer_issue_agent/static/styles.css`
  - Style batch and feedback UI states.
- Modify: `README.md`
  - Document batch upload format and feedback flow.
- Modify: `tests/test_ingestion.py`
  - Add batch parsing coverage.
- Modify: `tests/test_storage.py`
  - Add feedback append/merge coverage.
- Modify: `tests/test_app.py`
  - Add API and HTML/static hook coverage.

## Task 1: Batch Conversation Extraction

**Files:**
- Modify: `src/customer_issue_agent/ingestion.py`
- Modify: `tests/test_ingestion.py`

- [ ] **Step 1: Add failing batch extraction tests**

Append to `tests/test_ingestion.py`:

```python
from customer_issue_agent.ingestion import extract_batch_conversation_texts


def test_extract_batch_text_upload_splits_on_explicit_separator():
    content = (
        "Customer: It will not connect\nAgent: Please restart it\n"
        "\n---\n"
        "Customer: Missing cable\nAgent: We can send a replacement"
    ).encode("utf-8")

    result = extract_batch_conversation_texts(filename="batch.txt", content=content)

    assert result == [
        "Customer: It will not connect\nAgent: Please restart it",
        "Customer: Missing cable\nAgent: We can send a replacement",
    ]


def test_extract_batch_csv_upload_uses_one_row_per_conversation():
    content = (
        "platform,conversation\n"
        "Amazon,\"Customer: It will not connect\"\n"
        "TikTok Shop,\"Customer: Missing cable\"\n"
    ).encode("utf-8")

    result = extract_batch_conversation_texts(filename="batch.csv", content=content)

    assert result == ["Customer: It will not connect", "Customer: Missing cable"]


def test_extract_batch_rejects_more_than_limit():
    conversations = "\n---\n".join(f"Customer: issue {index}" for index in range(51))

    try:
        extract_batch_conversation_texts(filename="batch.txt", content=conversations.encode("utf-8"))
    except ValueError as exc:
        assert "单次最多分析 50 条" in str(exc)
    else:
        raise AssertionError("batch over limit should fail")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_ingestion.py::test_extract_batch_text_upload_splits_on_explicit_separator tests/test_ingestion.py::test_extract_batch_csv_upload_uses_one_row_per_conversation tests/test_ingestion.py::test_extract_batch_rejects_more_than_limit -q
```

Expected: FAIL because `extract_batch_conversation_texts` is not defined.

- [ ] **Step 3: Implement batch extraction**

Modify `src/customer_issue_agent/ingestion.py`:

```python
BATCH_LIMIT = 50
BATCH_SEPARATORS = ("\n---\n", "\r\n---\r\n", "\n===\n", "\r\n===\r\n")
BATCH_TEXT_KEYS = (
    "conversation",
    "conversation_text",
    "message",
    "text",
    "content",
    "body",
    "客服会话",
    "会话",
    "消息",
    "内容",
)


def extract_batch_conversation_texts(filename: str, content: bytes, limit: int = BATCH_LIMIT) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".log"}:
        conversations = _split_batch_text(_decode_text(content))
    elif suffix == ".csv":
        conversations = _extract_batch_csv(content)
    elif suffix in {".xlsx", ".xlsm"}:
        conversations = _extract_batch_xlsx(content)
    else:
        raise ValueError("仅支持 txt、log、csv、xlsx 或 xlsm 文件")

    cleaned = [item.strip() for item in conversations if item and item.strip()]
    if not cleaned:
        raise ValueError("文件中没有可分析会话，请检查导出内容")
    if len(cleaned) > limit:
        raise ValueError(f"单次最多分析 {limit} 条，请拆分文件后重试")
    return cleaned


def _split_batch_text(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    for separator in ("\n---\n", "\n===\n"):
        if separator in normalized:
            return normalized.split(separator)
    return [normalized]


def _extract_batch_csv(content: bytes) -> list[str]:
    decoded = _decode_text(content)
    reader = csv.DictReader(StringIO(decoded))
    rows: list[str] = []
    for row in reader:
        conversation = _first_value(row, BATCH_TEXT_KEYS)
        if conversation:
            rows.append(conversation)
    if rows:
        return rows
    return _split_batch_text(decoded)


def _extract_batch_xlsx(content: bytes) -> list[str]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    conversation_index = _first_index(headers, BATCH_TEXT_KEYS)
    conversations: list[str] = []

    for row in rows[1:]:
        values = ["" if value is None else str(value).strip() for value in row]
        if conversation_index is not None and conversation_index < len(values):
            conversations.append(values[conversation_index])
        else:
            line = " ".join(value for value in values if value)
            conversations.append(line)
    return conversations
```

- [ ] **Step 4: Run batch extraction tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_ingestion.py -q
```

Expected: all ingestion tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/ingestion.py tests/test_ingestion.py
git commit -m "feat: split batch conversation uploads"
```

## Task 2: Feedback Storage

**Files:**
- Modify: `src/customer_issue_agent/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Add failing feedback storage tests**

Append to `tests/test_storage.py`:

```python
def test_store_merges_latest_feedback_into_records(tmp_path):
    request = AnalysisRequest(platform="Other", conversation_text="Customer: not working")
    parsed = parse_conversation(request.platform, request.conversation_text)
    attribution = analyze_attribution(parsed)
    analysis = AnalysisResult(
        request=request,
        parsed=parsed,
        attribution=attribution,
        report=build_report(parsed, attribution),
    )
    store = AnalysisStore(tmp_path / "analyses.jsonl")
    record_id = store.save(analysis)

    feedback = store.save_feedback(
        record_id,
        {
            "accepted": False,
            "corrected_issue_category": "product_fault",
            "corrected_responsibility": "supply_chain_quality",
            "note": "用户明确提到设备完全失灵，需要质量侧复核。",
        },
    )
    records = store.list_records()

    assert feedback["accepted"] is False
    assert records[0]["feedback"]["corrected_issue_category"] == "product_fault"
    assert records[0]["feedback"]["corrected_responsibility"] == "supply_chain_quality"
    assert records[0]["feedback"]["note"] == "用户明确提到设备完全失灵，需要质量侧复核。"


def test_store_rejects_feedback_for_missing_record(tmp_path):
    store = AnalysisStore(tmp_path / "analyses.jsonl")

    try:
        store.save_feedback("missing", {"accepted": True})
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing record feedback should fail")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_storage.py::test_store_merges_latest_feedback_into_records tests/test_storage.py::test_store_rejects_feedback_for_missing_record -q
```

Expected: FAIL because `AnalysisStore.save_feedback` is not defined.

- [ ] **Step 3: Implement feedback storage**

Modify `src/customer_issue_agent/storage.py`:

```python
    def save_feedback(self, record_id: str, feedback: dict) -> dict:
        if not self.get_record(record_id):
            raise KeyError(record_id)

        cleaned = _clean_feedback(feedback)
        event = {
            "type": "feedback",
            "record_id": record_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "feedback": cleaned,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return cleaned

    def get_record(self, record_id: str) -> dict | None:
        for record in self.list_records():
            if record["id"] == record_id:
                return record
        return None
```

Replace `list_records()` with event-aware reading:

```python
    def list_records(self) -> list[dict]:
        if not self.path.exists():
            return []

        records: list[dict] = []
        feedback_by_record: dict[str, dict] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if payload.get("type") == "feedback":
                    feedback_by_record[payload["record_id"]] = payload["feedback"]
                else:
                    records.append(payload)

        for record in records:
            if record["id"] in feedback_by_record:
                record["feedback"] = feedback_by_record[record["id"]]
        return records
```

Add helper function:

```python
def _clean_feedback(feedback: dict) -> dict:
    return {
        "accepted": bool(feedback.get("accepted")),
        "corrected_issue_category": _optional_text(feedback.get("corrected_issue_category")),
        "corrected_responsibility": _optional_text(feedback.get("corrected_responsibility")),
        "note": _optional_text(feedback.get("note")),
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
```

- [ ] **Step 4: Run storage tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_storage.py -q
```

Expected: all storage tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/storage.py tests/test_storage.py
git commit -m "feat: store human feedback events"
```

## Task 3: Batch And Feedback API

**Files:**
- Modify: `src/customer_issue_agent/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add failing API tests**

Append to `tests/test_app.py`:

```python
def test_analyze_batch_file_returns_multiple_records(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze-batch-file",
        data={"platform": "Other overseas platform"},
        files={
            "file": (
                "batch.txt",
                "Customer: It will not connect\n\n---\n\nCustomer: Missing cable",
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["batch_id"]
    assert payload["count"] == 2
    assert len(payload["records"]) == 2
    assert payload["records"][0]["record_id"]
    assert payload["records"][1]["analysis"]["request"]["platform"] == "Other overseas platform"


def test_feedback_endpoint_updates_record_feedback(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    analysis_response = client.post(
        "/api/analyze",
        data={"platform": "Other", "conversation_text": "Customer: not working"},
    )
    record_id = analysis_response.json()["record_id"]

    response = client.post(
        f"/api/records/{record_id}/feedback",
        data={
            "accepted": "false",
            "corrected_issue_category": "product_fault",
            "corrected_responsibility": "supply_chain_quality",
            "note": "需要质量团队复核。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"] == record_id
    assert payload["feedback"]["accepted"] is False
    assert payload["feedback"]["corrected_issue_category"] == "product_fault"
    assert payload["feedback"]["corrected_responsibility"] == "supply_chain_quality"
    assert payload["feedback"]["note"] == "需要质量团队复核。"


def test_feedback_endpoint_returns_404_for_missing_record(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post("/api/records/missing/feedback", data={"accepted": "true"})

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_analyze_batch_file_returns_multiple_records tests/test_app.py::test_feedback_endpoint_updates_record_feedback tests/test_app.py::test_feedback_endpoint_returns_404_for_missing_record -q
```

Expected: FAIL because the new endpoints do not exist.

- [ ] **Step 3: Implement API endpoints**

Modify imports in `src/customer_issue_agent/app.py`:

```python
from uuid import uuid4

from customer_issue_agent.ingestion import extract_batch_conversation_texts, extract_conversation_text
```

Add endpoint inside `create_app()`:

```python
    @app.post("/api/analyze-batch-file")
    async def analyze_batch_file(
        platform: str = Form(default="Other overseas platform"),
        file: UploadFile | None = None,
    ) -> dict:
        if file is None:
            raise HTTPException(status_code=422, detail="请上传批量客服会话文件")
        content = await file.read()
        try:
            conversations = extract_batch_conversation_texts(file.filename or "batch.txt", content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        records = [
            _run_analysis(store, platform=platform, conversation_text=conversation)
            for conversation in conversations
        ]
        return {"batch_id": str(uuid4()), "count": len(records), "records": records}

    @app.post("/api/records/{record_id}/feedback")
    async def save_feedback(
        record_id: str,
        accepted: bool = Form(default=True),
        corrected_issue_category: str = Form(default=""),
        corrected_responsibility: str = Form(default=""),
        note: str = Form(default=""),
    ) -> dict:
        try:
            feedback = store.save_feedback(
                record_id,
                {
                    "accepted": accepted,
                    "corrected_issue_category": corrected_issue_category,
                    "corrected_responsibility": corrected_responsibility,
                    "note": note,
                },
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="记录不存在或已被清理，请刷新页面后重试") from exc
        return {"record_id": record_id, "feedback": feedback}
```

- [ ] **Step 4: Run API tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py -q
```

Expected: all app tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/app.py tests/test_app.py
git commit -m "feat: expose batch analysis and feedback APIs"
```

## Task 4: Workbench Batch And Feedback UI

**Files:**
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/app.js`
- Modify: `src/customer_issue_agent/static/styles.css`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add failing UI hook tests**

Append to `tests/test_app.py`:

```python
def test_index_contains_batch_upload_and_feedback_controls(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-tab-target="batch-panel"' in html
    assert 'id="batch-form"' in html
    assert 'data-endpoint="/api/analyze-batch-file"' in html
    assert 'id="batch-results"' in html
    assert 'data-feedback-template' in html


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_batch_upload_and_feedback_controls tests/test_app.py::test_static_app_js_contains_batch_and_feedback_hooks -q
```

Expected: FAIL because the page and script do not include batch/feedback hooks.

- [ ] **Step 3: Add template hooks**

Modify `src/customer_issue_agent/templates/index.html`:

```html
<button class="tab" type="button" data-tab-target="batch-panel" role="tab" aria-selected="false">批量上传</button>

<section id="batch-panel" class="tab-panel" role="tabpanel" hidden>
  <form id="batch-form" class="panel analysis-form" data-endpoint="/api/analyze-batch-file" method="post" action="/api/analyze-batch-file" enctype="multipart/form-data">
    <label for="batch-platform">平台来源</label>
    <input id="batch-platform" name="platform" value="Other overseas platform">

    <label for="batch-file">批量客服会话文件</label>
    <input id="batch-file" name="file" type="file" accept=".txt,.log,.csv,.xlsx,.xlsm">
    <p class="hint">支持 txt、log、csv、xlsx、xlsm。文本文件可用单独一行 --- 或 === 分隔多条会话，单次最多 50 条。</p>

    <button type="submit" data-loading-label="批量分析中...">上传并批量分析</button>
    <p id="batch-error" class="form-message" role="alert"></p>
  </form>
</section>

<section id="batch-results" class="batch-results" aria-label="批量分析结果"></section>

<template data-feedback-template>
  <form class="feedback-form">
    <label>
      复核结论
      <select name="accepted">
        <option value="true">认可系统判断</option>
        <option value="false">需要修正</option>
      </select>
    </label>
    <label>
      修正问题类型
      <input name="corrected_issue_category" placeholder="例如 product_fault">
    </label>
    <label>
      修正责任方
      <input name="corrected_responsibility" placeholder="例如 supply_chain_quality">
    </label>
    <label>
      备注
      <textarea name="note" rows="3" placeholder="记录人工判断依据"></textarea>
    </label>
    <button type="submit" data-loading-label="保存中...">保存反馈</button>
    <p class="form-message" role="alert"></p>
  </form>
</template>
```

Also update recent record cards to render feedback status:

```html
{% if record.feedback %}
  <span class="feedback-pill">{{ "已认可" if record.feedback.accepted else "已修正" }}</span>
{% endif %}
```

- [ ] **Step 4: Add JavaScript behavior**

Modify `src/customer_issue_agent/static/app.js`:

```javascript
document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindAnalysisForm("paste-form", "paste-error");
  bindAnalysisForm("upload-form", "upload-error");
  bindBatchForm();
  bindFeedbackForms(document);
});

function bindBatchForm() {
  const form = document.getElementById("batch-form");
  if (!form) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitBatchForm(form, document.getElementById("batch-error"));
  });
}

async function submitBatchForm(form, errorBox) {
  const button = form.querySelector("button[type='submit']");
  const originalLabel = button.textContent;
  clearError(errorBox);
  setLoading(button, true);

  try {
    const response = await fetch(form.dataset.endpoint, {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderBatchResults(payload);
    payload.records.forEach((record) => prependRecentRecord(record));
    form.reset();
  } catch (error) {
    showError(errorBox, error.message || "批量分析失败，请检查文件后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}

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
    <div class="batch-list"></div>
  `;
  const list = container.querySelector(".batch-list");
  payload.records.forEach((record) => {
    list.appendChild(buildRecordCard(record));
  });
  bindFeedbackForms(container);
}

function buildRecordCard(payload) {
  const article = document.createElement("article");
  article.className = "record result-record";
  article.dataset.recordId = payload.record_id;
  article.innerHTML = `
    <div class="record-meta">
      <strong>${escapeHtml(payload.analysis.request.platform)}</strong>
      <span>${labelFor("issue_category", payload.analysis.attribution.issue_category)}</span>
      <span>${labelFor("responsibility", payload.analysis.attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", payload.analysis.attribution.evidence_strength)}</span>
    </div>
    <p>${escapeHtml(payload.analysis.report)}</p>
  `;
  article.appendChild(createFeedbackForm(payload.record_id));
  return article;
}

function createFeedbackForm(recordId) {
  const template = document.querySelector("[data-feedback-template]");
  const fragment = template.content.cloneNode(true);
  const form = fragment.querySelector("form");
  form.dataset.endpoint = `/api/records/${recordId}/feedback`;
  return fragment;
}

function bindFeedbackForms(root) {
  root.querySelectorAll(".feedback-form").forEach((form) => {
    if (form.dataset.bound === "true") {
      return;
    }
    form.dataset.bound = "true";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitFeedbackForm(form);
    });
  });
}

async function submitFeedbackForm(form) {
  const button = form.querySelector("button[type='submit']");
  const message = form.querySelector(".form-message");
  const originalLabel = button.textContent;
  clearError(message);
  setLoading(button, true);

  try {
    const response = await fetch(form.dataset.endpoint, {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    message.textContent = payload.feedback.accepted ? "已保存：认可系统判断。" : "已保存：人工修正已记录。";
    message.classList.add("is-visible", "is-success");
  } catch (error) {
    showError(message, error.message || "反馈保存失败，请稍后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}
```

- [ ] **Step 5: Add CSS for batch and feedback UI**

Modify `src/customer_issue_agent/static/styles.css`:

```css
.batch-results {
  margin-top: 24px;
}

.batch-list {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.result-record {
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px;
}

.feedback-form {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.feedback-form select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  color: var(--ink);
  font: inherit;
}

.feedback-pill {
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.12);
  color: var(--accent-strong);
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 700;
}

.form-message.is-success {
  color: var(--accent-strong);
}
```

- [ ] **Step 6: Run UI hook tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_batch_upload_and_feedback_controls tests/test_app.py::test_static_app_js_contains_batch_and_feedback_hooks -q
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
git commit -m "feat: add batch review workbench UI"
```

## Task 5: Documentation And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with batch and feedback usage**

Append to `README.md`:

```markdown
## 批量分析与人工复核

工作台支持批量上传客服会话文件。文本文件可以使用单独一行 `---` 或 `===` 分隔多条会话；CSV 或 Excel 文件可使用 `conversation`、`conversation_text`、`message`、`内容` 等列存放每条会话。单次最多分析 50 条。

批量分析完成后，每条结果都可以保存人工反馈：

- `认可系统判断`：表示当前问题类型、责任方和建议可以进入后续处理。
- `需要修正`：可以补充修正后的问题类型、责任方和人工备注。

反馈以追加事件写入本地 JSONL，不覆盖原始分析记录，便于后续复盘。
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
git commit -m "docs: document batch review workflow"
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

- Spec coverage: batch file analysis, 50-record limit, feedback API, append-only feedback events, single-page UI, recent record feedback status, and README documentation are covered.
- Deferred items: queueing, login, model calls, exports, trend dashboards, and database migration are intentionally excluded.
- Placeholder scan: this plan contains no placeholder tasks and no unspecified implementation steps.
- Type consistency: `extract_batch_conversation_texts`, `save_feedback`, `get_record`, `/api/analyze-batch-file`, and `/api/records/{record_id}/feedback` are named consistently across tests and implementation steps.
