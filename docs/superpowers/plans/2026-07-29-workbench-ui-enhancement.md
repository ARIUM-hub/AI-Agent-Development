# Workbench UI Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing single-page FastAPI workbench so users can paste or upload conversations and view structured Chinese analysis results directly on the page.

**Architecture:** Keep the current FastAPI and Jinja page. Add progressive enhancement with one static JavaScript file, expand the existing template and CSS, and reuse `/api/analyze` plus `/api/analyze-file` without adding a frontend framework or model-provider calls.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, Pydantic, vanilla HTML/CSS/JavaScript, pytest, FastAPI TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-workbench-ui-enhancement-design.md`

## Scope Check

This plan covers one cohesive UI usability enhancement on top of the existing MVP. It does not implement batch analysis, user login, artificial intelligence provider integration, multi-page administration, or manual correction workflows.

## File Structure

- Modify: `src/customer_issue_agent/app.py`
- Modify: `src/customer_issue_agent/templates/index.html`
- Modify: `src/customer_issue_agent/static/styles.css`
- Create: `src/customer_issue_agent/static/app.js`
- Modify: `tests/test_app.py`
- Modify: `README.md`

## Task 1: API Surface for UI Rendering

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/app.py`

- [ ] **Step 1: Write failing tests for file upload and structured UI fields**

Append these tests to `tests/test_app.py`:

```python
def test_analyze_text_response_exposes_fields_for_ui(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        data={
            "platform": "Other overseas platform",
            "conversation_text": (
                "Customer: I followed the instructions but it still will not connect.\n"
                "Agent: Please try again later."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    attribution = payload["analysis"]["attribution"]
    assert payload["record_id"]
    assert attribution["customer_problem"]
    assert attribution["issue_category"] == "function_use"
    assert attribution["primary_responsibility"] == "customer_service_training"
    assert attribution["evidence_strength"] == "likely"
    assert attribution["recommended_actions"]
    assert attribution["missing_information"]


def test_analyze_file_upload_returns_report(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze-file",
        data={"platform": "Other overseas platform"},
        files={
            "file": (
                "conversation.txt",
                (
                    "Customer: I followed the instructions but it still will not connect.\n"
                    "Agent: Please try again later."
                ),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"]
    assert "客户问题" in payload["analysis"]["report"]
    assert payload["analysis"]["request"]["platform"] == "Other overseas platform"
```

- [ ] **Step 2: Run tests to verify current behavior**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_analyze_text_response_exposes_fields_for_ui tests/test_app.py::test_analyze_file_upload_returns_report -q
```

Expected: One of two outcomes is acceptable. If both tests pass, the existing API already satisfies this task and no production code is needed. If a test fails, it must fail because response fields or file upload behavior are missing.

- [ ] **Step 3: If tests fail, update API response only**

If `test_analyze_text_response_exposes_fields_for_ui` fails because enum values are not JSON strings, update `_run_analysis` in `src/customer_issue_agent/app.py`:

```python
def _run_analysis(store: AnalysisStore, platform: str, conversation_text: str) -> dict:
    try:
        request = AnalysisRequest(platform=platform, conversation_text=conversation_text)
    except ValidationError as exc:
        detail = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
        raise HTTPException(status_code=422, detail=detail) from exc

    parsed = parse_conversation(request.platform, request.conversation_text)
    attribution = analyze_attribution(parsed)
    result = AnalysisResult(
        request=request,
        parsed=parsed,
        attribution=attribution,
        report=build_report(parsed, attribution),
    )
    record_id = store.save(result)
    return {"record_id": record_id, "analysis": result.model_dump(mode="json")}
```

If `test_analyze_file_upload_returns_report` fails because upload errors are not returned as 422 JSON, update only `analyze_file` in `src/customer_issue_agent/app.py`:

```python
    @app.post("/api/analyze-file")
    async def analyze_file(
        platform: str = Form(default="Other overseas platform"),
        file: UploadFile | None = None,
    ) -> dict:
        if file is None:
            raise HTTPException(status_code=422, detail="请上传客服会话文件")
        content = await file.read()
        try:
            text = extract_conversation_text(file.filename or "conversation.txt", content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _run_analysis(store, platform=platform, conversation_text=text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_analyze_text_response_exposes_fields_for_ui tests/test_app.py::test_analyze_file_upload_returns_report -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_app.py src/customer_issue_agent/app.py
git commit -m "test: cover UI analysis API fields"
```

If no production code changed, commit only `tests/test_app.py` with the same message.

## Task 2: Workbench HTML Structure

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write failing UI structure test**

Append this test to `tests/test_app.py`:

```python
def test_index_contains_tabs_forms_result_region_and_script(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-tab-target="paste-panel"' in html
    assert 'data-tab-target="upload-panel"' in html
    assert 'id="paste-form"' in html
    assert 'id="upload-form"' in html
    assert 'id="analysis-result"' in html
    assert 'id="recent-records"' in html
    assert 'role="alert"' in html
    assert '<script src="/static/app.js" defer></script>' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_index_contains_tabs_forms_result_region_and_script -q
```

Expected: FAIL because the current template does not contain upload tabs, result region, or the JavaScript file reference.

- [ ] **Step 3: Replace template with enhanced workbench markup**

Replace `src/customer_issue_agent/templates/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>客户使用问题归因智能体</title>
    <link rel="stylesheet" href="/static/styles.css">
    <script src="/static/app.js" defer></script>
  </head>
  <body>
    <main class="shell">
      <section class="workbench">
        <header class="topbar">
          <div>
            <p class="eyebrow">海外电商 · 客服会话分析</p>
            <h1>客户使用问题归因智能体</h1>
            <p class="subtitle">粘贴或上传客服会话，生成客户问题、业务原因、责任方和下一步建议。</p>
          </div>
          <span class="status">本地规则模式</span>
        </header>

        <section class="workspace-grid">
          <div class="input-stack">
            <div class="tabs" role="tablist" aria-label="输入方式">
              <button class="tab is-active" type="button" role="tab" aria-selected="true" aria-controls="paste-panel" data-tab-target="paste-panel">粘贴会话</button>
              <button class="tab" type="button" role="tab" aria-selected="false" aria-controls="upload-panel" data-tab-target="upload-panel">上传文件</button>
            </div>

            <form id="paste-form" class="panel input-panel" method="post" action="/api/analyze" data-endpoint="/api/analyze">
              <div class="field">
                <label for="paste-platform">平台来源</label>
                <input id="paste-platform" name="platform" value="Other overseas platform">
              </div>

              <div id="paste-panel" class="tab-panel" role="tabpanel">
                <div class="field">
                  <label for="conversation_text">客服会话</label>
                  <textarea id="conversation_text" name="conversation_text" rows="12" placeholder="Customer: I followed the instructions but it still will not connect.&#10;Agent: Please try again later."></textarea>
                </div>
                <p id="paste-error" class="form-message" role="alert" aria-live="polite"></p>
                <button class="primary-action" type="submit" data-loading-label="分析中...">分析会话</button>
              </div>
            </form>

            <form id="upload-form" class="panel input-panel is-hidden" method="post" action="/api/analyze-file" enctype="multipart/form-data" data-endpoint="/api/analyze-file">
              <div class="field">
                <label for="upload-platform">平台来源</label>
                <input id="upload-platform" name="platform" value="Other overseas platform">
              </div>

              <div id="upload-panel" class="tab-panel" role="tabpanel" hidden>
                <div class="field">
                  <label for="conversation-file">客服会话文件</label>
                  <input id="conversation-file" name="file" type="file" accept=".txt,.log,.csv,.xlsx,.xlsm">
                  <p class="helper">支持 txt、log、csv、xlsx、xlsm。</p>
                </div>
                <p id="upload-error" class="form-message" role="alert" aria-live="polite"></p>
                <button class="primary-action" type="submit" data-loading-label="上传分析中...">上传并分析</button>
              </div>
            </form>
          </div>

          <section id="analysis-result" class="panel result-panel" aria-live="polite">
            <div class="result-empty">
              <p class="eyebrow">等待分析</p>
              <h2>结果会显示在这里</h2>
              <p>提交会话后，系统会拆出客户问题、业务原因、责任方、下一步建议和需要补充的信息。</p>
            </div>
          </section>
        </section>

        <section class="history" aria-label="最近分析记录">
          <div class="section-heading">
            <h2>最近记录</h2>
            <span>{{ records|length }} 条</span>
          </div>
          <div id="recent-records" class="record-list">
            {% if records %}
              {% for record in records|reverse %}
                <article class="record" data-record-id="{{ record.id }}">
                  <div class="record-meta">
                    <strong>{{ record.analysis.request.platform }}</strong>
                    <span>{{ record.analysis.attribution.issue_category }}</span>
                    <span>{{ record.analysis.attribution.primary_responsibility }}</span>
                    <span>{{ record.analysis.attribution.evidence_strength }}</span>
                  </div>
                  <p>{{ record.analysis.report }}</p>
                </article>
              {% endfor %}
            {% else %}
              <p class="empty">还没有分析记录。</p>
            {% endif %}
          </div>
        </section>
      </section>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_index_contains_tabs_forms_result_region_and_script -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html tests/test_app.py
git commit -m "feat: add workbench UI structure"
```

## Task 3: Progressive Enhancement JavaScript

**Files:**
- Modify: `tests/test_app.py`
- Create: `src/customer_issue_agent/static/app.js`

- [ ] **Step 1: Write failing static JavaScript test**

Append this test to `tests/test_app.py`:

```python
def test_static_app_js_contains_progressive_enhancement_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindTabs" in script
    assert "submitAnalysisForm" in script
    assert "renderAnalysisResult" in script
    assert "prependRecentRecord" in script
    assert "fetch(form.dataset.endpoint" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_static_app_js_contains_progressive_enhancement_hooks -q
```

Expected: FAIL with `404` because `src/customer_issue_agent/static/app.js` does not exist.

- [ ] **Step 3: Create JavaScript file**

Create `src/customer_issue_agent/static/app.js`:

```javascript
const labels = {
  issue_category: {
    installation: "安装、开箱或组装问题",
    function_use: "功能不会用或设置失败",
    expectation_gap: "功能表现未达到预期",
    product_fault: "产品异常、失灵或疑似质量问题",
    compatibility: "兼容性问题",
    accessory: "配件缺失或条件不满足",
    non_usage: "非产品使用问题",
    unclear: "信息不足",
  },
  responsibility: {
    operations: "运营",
    customer_service_training: "客服培训",
    product: "产品",
    supply_chain_quality: "供应链或质量",
    need_more_information: "需要补充信息",
  },
  evidence: {
    clear: "较明确",
    likely: "倾向于",
    insufficient: "信息不足",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindAnalysisForm("paste-form", "paste-error");
  bindAnalysisForm("upload-form", "upload-error");
});

function bindTabs() {
  const tabs = Array.from(document.querySelectorAll("[data-tab-target]"));
  const forms = {
    "paste-panel": document.getElementById("paste-form"),
    "upload-panel": document.getElementById("upload-form"),
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tabTarget;
      tabs.forEach((item) => {
        const selected = item === tab;
        item.classList.toggle("is-active", selected);
        item.setAttribute("aria-selected", String(selected));
      });

      Object.entries(forms).forEach(([panelId, form]) => {
        const panel = document.getElementById(panelId);
        const active = panelId === target;
        form.classList.toggle("is-hidden", !active);
        panel.hidden = !active;
      });
    });
  });
}

function bindAnalysisForm(formId, errorId) {
  const form = document.getElementById(formId);
  if (!form) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAnalysisForm(form, document.getElementById(errorId));
  });
}

async function submitAnalysisForm(form, errorBox) {
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
    renderAnalysisResult(payload);
    prependRecentRecord(payload);
    form.reset();
  } catch (error) {
    showError(errorBox, error.message || "分析失败，请检查输入后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}

function renderAnalysisResult(payload) {
  const result = document.getElementById("analysis-result");
  const analysis = payload.analysis;
  const attribution = analysis.attribution;
  result.innerHTML = `
    <div class="result-header">
      <div>
        <p class="eyebrow">分析完成</p>
        <h2>${escapeHtml(analysis.request.platform)}</h2>
      </div>
      <span class="record-id">#${escapeHtml(payload.record_id.slice(0, 8))}</span>
    </div>
    <div class="summary-strip">
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <div class="result-grid">
      ${resultCard("客户问题", attribution.customer_problem)}
      ${resultCard("业务原因", attribution.root_causes.map((item) => labelFor("rootCause", item)).join(" + ") || analysis.report)}
      ${resultCard("优先责任方", labelFor("responsibility", attribution.primary_responsibility))}
      ${resultCard("下一步建议", attribution.recommended_actions.join("；"))}
      ${resultCard("需要补充", attribution.missing_information.join("；") || "暂无必须补充的信息。")}
    </div>
  `;
}

function prependRecentRecord(payload) {
  const list = document.getElementById("recent-records");
  const analysis = payload.analysis;
  const attribution = analysis.attribution;
  const empty = list.querySelector(".empty");
  if (empty) {
    empty.remove();
  }

  const article = document.createElement("article");
  article.className = "record";
  article.dataset.recordId = payload.record_id;
  article.innerHTML = `
    <div class="record-meta">
      <strong>${escapeHtml(analysis.request.platform)}</strong>
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <p>${escapeHtml(analysis.report)}</p>
  `;
  list.prepend(article);
}

function resultCard(title, body) {
  return `
    <article class="result-card">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body || "暂无信息。")}</p>
    </article>
  `;
}

function labelFor(group, value) {
  if (group === "rootCause") {
    return rootCauseLabel(value);
  }
  return labels[group]?.[value] || value || "未知";
}

function rootCauseLabel(value) {
  const rootCauses = {
    unclear_instructions: "说明或引导不清",
    expectation_mismatch: "预期与实际体验有落差",
    customer_service_gap: "客服排障引导不足",
    product_design: "产品设计容易误用",
    quality_signal: "疑似产品质量异常",
    compatibility_limit: "疑似兼容性限制",
    customer_operation: "客户操作或条件不足",
    insufficient_information: "信息不足",
    non_usage_issue: "非产品使用问题",
  };
  return rootCauses[value] || value || "未知";
}

function readError(payload) {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
    return payload.detail[0].msg;
  }
  return "分析失败，请检查输入后重试。";
}

function showError(errorBox, message) {
  errorBox.textContent = message;
  errorBox.classList.add("is-visible");
}

function clearError(errorBox) {
  errorBox.textContent = "";
  errorBox.classList.remove("is-visible");
}

function setLoading(button, loading) {
  button.disabled = loading;
  if (loading) {
    button.textContent = button.dataset.loadingLabel || "处理中...";
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_static_app_js_contains_progressive_enhancement_hooks -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/app.js tests/test_app.py
git commit -m "feat: add progressive workbench interactions"
```

## Task 4: Workbench Visual Polish

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/static/styles.css`

- [ ] **Step 1: Write failing CSS coverage test**

Append this test to `tests/test_app.py`:

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
    assert "@media (max-width: 720px)" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_styles_cover_enhanced_workbench_components -q
```

Expected: FAIL because the current CSS does not cover all enhanced workbench components.

- [ ] **Step 3: Replace CSS with enhanced responsive styles**

Replace `src/customer_issue_agent/static/styles.css`:

```css
:root {
  --ink: #17211f;
  --muted: #65716d;
  --paper: #f7f5ef;
  --panel: #ffffff;
  --line: #d9ded5;
  --accent: #0f766e;
  --accent-strong: #115e59;
  --signal: #d97706;
  --danger: #b91c1c;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  color: var(--ink);
  background:
    linear-gradient(135deg, rgba(15, 118, 110, 0.12), transparent 34%),
    linear-gradient(315deg, rgba(217, 119, 6, 0.12), transparent 30%),
    var(--paper);
  font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}

.shell {
  min-height: 100vh;
  padding: 32px;
}

.workbench {
  max-width: 1180px;
  margin: 0 auto;
}

.topbar,
.section-heading,
.result-header,
.record-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.topbar {
  align-items: end;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}

.eyebrow,
.helper,
.subtitle,
.empty,
.record p {
  color: var(--muted);
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent-strong);
  font-size: 14px;
  font-weight: 700;
}

.subtitle {
  max-width: 680px;
  margin: 10px 0 0;
}

h1,
h2,
h3,
p {
  letter-spacing: 0;
}

h1,
h2,
h3 {
  margin: 0;
}

h1 {
  font-size: 32px;
}

h2 {
  font-size: 18px;
}

h3 {
  font-size: 15px;
}

.status,
.record-id,
.summary-strip span,
.record-meta span {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.74);
  color: var(--muted);
}

.status,
.record-id,
.summary-strip span,
.record-meta span {
  padding: 8px 12px;
  border-radius: 6px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
  gap: 24px;
  margin-top: 24px;
}

.input-stack {
  min-width: 0;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tab {
  min-height: 44px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--muted);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.tab.is-active {
  background: var(--ink);
  color: white;
  border-color: var(--ink);
}

.panel,
.history {
  padding: 20px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}

.history {
  margin-top: 24px;
}

.is-hidden {
  display: none;
}

.field {
  margin-bottom: 16px;
}

label {
  display: block;
  margin-bottom: 8px;
  font-weight: 700;
}

input,
textarea {
  width: 100%;
  min-height: 44px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  color: var(--ink);
  font: inherit;
}

textarea {
  resize: vertical;
}

.helper {
  margin: 8px 0 0;
  font-size: 14px;
}

.primary-action {
  min-height: 44px;
  border: 0;
  border-radius: 6px;
  padding: 12px 18px;
  background: var(--accent);
  color: white;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.primary-action:hover,
.primary-action:focus-visible {
  background: var(--accent-strong);
}

.primary-action:disabled {
  cursor: wait;
  opacity: 0.68;
}

button:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 3px solid rgba(217, 119, 6, 0.45);
  outline-offset: 2px;
}

.form-message {
  display: none;
  margin: 0 0 12px;
  color: var(--danger);
  font-weight: 700;
}

.form-message.is-visible {
  display: block;
}

.result-panel {
  min-height: 420px;
}

.result-empty {
  display: grid;
  min-height: 330px;
  align-content: center;
  gap: 10px;
}

.summary-strip,
.result-grid {
  display: grid;
  gap: 12px;
}

.summary-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 16px 0;
}

.result-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.result-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  background: #fbfcf8;
}

.result-card p {
  margin: 8px 0 0;
  line-height: 1.65;
}

.record-list {
  margin-top: 16px;
}

.record {
  padding: 16px 0;
  border-top: 1px solid var(--line);
  white-space: pre-line;
}

.record p {
  margin-bottom: 0;
  line-height: 1.65;
}

.record-meta {
  flex-wrap: wrap;
  justify-content: flex-start;
}

@media (max-width: 900px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .shell {
    padding: 18px;
  }

  .topbar,
  .section-heading,
  .result-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .tabs,
  .summary-strip,
  .result-grid {
    grid-template-columns: 1fr;
  }

  .tabs {
    display: grid;
  }

  h1 {
    font-size: 24px;
  }
}
```

- [ ] **Step 4: Run style test and full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_styles_cover_enhanced_workbench_components -q
python -m pytest -q
```

Expected: style test passes, then all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "feat: polish enhanced workbench layout"
```

## Task 5: Documentation and Smoke Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README usage instructions**

Add this section to `README.md` after the local run instructions:

```markdown
## 工作台使用方式

打开首页后可以选择两种输入方式：

- `粘贴会话`：选择平台来源，粘贴单条客服会话，然后点击“分析会话”。
- `上传文件`：选择平台来源，上传 `txt`、`log`、`csv`、`xlsx` 或 `xlsm` 文件，然后点击“上传并分析”。

分析完成后，页面会直接显示客户问题、业务原因、优先责任方、下一步建议和需要补充的信息。最近记录会保留最近 10 条分析摘要。
```

- [ ] **Step 2: Run full automated verification**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Start local server**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m uvicorn customer_issue_agent.app:create_app --factory --host 127.0.0.1 --port 8000
```

Expected: output includes `Uvicorn running on http://127.0.0.1:8000`.

- [ ] **Step 4: Verify paste flow through API**

Run this separate smoke request while the server is running:

```powershell
$OutputEncoding = [Console]::OutputEncoding
Add-Type -AssemblyName System.Net.Http
$pairs = [System.Collections.Generic.List[System.Collections.Generic.KeyValuePair[string,string]]]::new()
$pairs.Add([System.Collections.Generic.KeyValuePair[string,string]]::new('platform','Other overseas platform'))
$pairs.Add([System.Collections.Generic.KeyValuePair[string,string]]::new('conversation_text',"Customer: I followed the instructions but it still will not connect.`nAgent: Please try again later."))
$client = [System.Net.Http.HttpClient]::new()
$content = [System.Net.Http.FormUrlEncodedContent]::new($pairs)
$response = $client.PostAsync('http://127.0.0.1:8000/api/analyze', $content).Result
$json = [System.Text.Encoding]::UTF8.GetString($response.Content.ReadAsByteArrayAsync().Result)
$payload = $json | ConvertFrom-Json
$report = $payload.analysis.report
if ($report -match '客户问题' -and $report -match '业务原因' -and $report -match '优先责任方' -and $report -match '下一步建议') { 'PASTE_SMOKE_OK' } else { throw 'Paste smoke failed' }
```

Expected: `PASTE_SMOKE_OK`.

- [ ] **Step 5: Verify upload flow through API**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
$sample = Join-Path $env:TEMP 'customer-issue-sample.txt'
Set-Content -LiteralPath $sample -Value "Customer: I followed the instructions but it still will not connect.`nAgent: Please try again later." -Encoding UTF8
$form = @{
  platform = 'Other overseas platform'
  file = Get-Item -LiteralPath $sample
}
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/analyze-file' -Method Post -Form $form
$json = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
$payload = $json | ConvertFrom-Json
if ($payload.analysis.report -match '客户问题') { 'UPLOAD_SMOKE_OK' } else { throw 'Upload smoke failed' }
```

Expected: `UPLOAD_SMOKE_OK`.

- [ ] **Step 6: Commit**

Run:

```powershell
git add README.md
git commit -m "docs: document enhanced workbench usage"
```

## Execution Notes

- Keep `.superpowers/`, `.pytest_cache/`, `data/`, `__pycache__/`, and egg-info files untracked.
- Do not add a frontend build step or package manager.
- Do not add model-provider calls.
- Preserve UTF-8 file encoding and write Chinese text directly, not as escaped Unicode.
- If the upload smoke script fails because the local PowerShell version lacks `-Form`, use the explicit `System.Net.Http.MultipartFormDataContent` API and keep UTF-8 decoding explicit.

## Self-Review Checklist

- Spec coverage: tabs, paste input, file upload input, direct page result display, recent records, JavaScript enhancement, form errors, responsive layout, accessibility labels, and smoke verification are covered by Tasks 1 through 5.
- Deferred scope: batch analysis, multi-page admin, auth, manual correction, and LLM provider integration are intentionally excluded.
- Placeholder scan: the plan uses concrete files, commands, test snippets, and code snippets for every implementation step.
- Type consistency: tests and JavaScript use existing API fields: `record_id`, `analysis.report`, `analysis.request.platform`, `analysis.attribution.issue_category`, `analysis.attribution.primary_responsibility`, `analysis.attribution.evidence_strength`, `analysis.attribution.customer_problem`, `analysis.attribution.root_causes`, `analysis.attribution.recommended_actions`, and `analysis.attribution.missing_information`.
