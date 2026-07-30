# Web 审批视图与执行确认 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为本地 Web 控制台增加两步式 provider plan 预览与确认执行能力，让浏览器入口复用现有结构化执行计划安全边界。

**Architecture:** 后端在 `dev_agent.web.api` 中新增 provider plan preview/apply helper，纯 preview 不创建 runner、不写历史，apply 在重新 preview 后调用 `LocalTaskRunner` 执行。HTTP server 增加 `/api/provider-plan/preview` 和 `/api/provider-plan/apply` 路由，前端在现有无框架页面中增加一个两步状态机：生成预览后才启用确认执行。

**Tech Stack:** Python 3.11+、标准库 `http.server`、JSON、pytest、无框架 HTML/CSS/JavaScript、Windows PowerShell、UTF-8。

---

## Scope Check

本计划实现已批准规格 `docs/superpowers/specs/2026-07-29-dev-agent-web-approval-flow-design.md` 中的 Web 两步审批流 v1。

本计划不接真实云端 provider，不做批量模型请求、健康探测、并发子智能体、Git 写操作、删除/移动/重命名文件、Markdown fenced JSON 解析、完整 unified diff、审批 token 或多用户权限。

## File Structure

- Modify: `src/dev_agent/web/api.py`，新增 provider plan preview/apply helper，集中组合 Web payload。
- Modify: `src/dev_agent/web/server.py`，新增两个 POST 路由，把 helper 错误映射为 HTTP 400。
- Modify: `src/dev_agent/web/static/index.html`，增加 Provider plan 审批表单、确认按钮、预览/结果区域。
- Modify: `src/dev_agent/web/static/app.js`，增加 preview/apply fetch、状态切换、错误展示、历史刷新。
- Modify: `src/dev_agent/web/static/styles.css`，补充双表单、风险卡片、按钮禁用和错误区域样式，保持现有视觉方向。
- Modify: `tests/test_web_api.py`，覆盖 Web API helper 成功、失败和无副作用。
- Modify: `tests/test_web_server.py`，覆盖新 HTTP 路由和静态资源交互文本。

---

### Task 1: Web API Provider Plan Preview

**Files:**
- Modify: `src/dev_agent/web/api.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 1: Write failing Web API preview tests**

Update imports at the top of `tests/test_web_api.py`:

```python
import json
import subprocess

import pytest

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.web.api import (
    apply_provider_plan_task,
    build_context_payload,
    build_health_payload,
    build_history_payload,
    preview_provider_plan_task,
    run_dry_run_task,
)
```

Append these tests to `tests/test_web_api.py`:

```python
def provider_plan_json(path: str = "docs/from-web-provider.md", content: str = "来自 Web provider\n") -> str:
    return json.dumps(
        {
            "summary": "创建 Web provider 文件",
            "operations": [
                {
                    "action": "create_text",
                    "path": path,
                    "content": content,
                }
            ],
        },
        ensure_ascii=False,
    )


def test_preview_provider_plan_task_returns_preview_without_side_effects(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = preview_provider_plan_task(
        repo_root=tmp_path,
        request_text="预览 Web provider plan",
        fake_response=provider_plan_json(),
    )

    assert payload["ok"] is True
    assert payload["task_id"] is None
    assert payload["dry_run"] is True
    assert payload["planned_changes"][0]["path"] == "docs/from-web-provider.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["applied_changes"] == []
    assert payload["diff_stat"] == ""
    assert payload["execution_error"] is None
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "from-web-provider.md").exists()


def test_preview_provider_plan_task_rejects_malformed_json_without_writing(tmp_path) -> None:
    with pytest.raises(ValueError, match="无法解析 provider 执行计划"):
        preview_provider_plan_task(
            repo_root=tmp_path,
            request_text="坏 provider plan",
            fake_response='{"summary":',
        )

    assert not (tmp_path / ".agent").exists()


def test_preview_provider_plan_task_rejects_dangerous_path_without_writing(tmp_path) -> None:
    with pytest.raises(ValueError, match="执行计划预览失败"):
        preview_provider_plan_task(
            repo_root=tmp_path,
            request_text="危险 provider plan",
            fake_response=provider_plan_json(path="../escape.md"),
        )

    assert not (tmp_path.parent / "escape.md").exists()
```

- [ ] **Step 2: Run preview tests to verify failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_api.py::test_preview_provider_plan_task_returns_preview_without_side_effects tests/test_web_api.py::test_preview_provider_plan_task_rejects_malformed_json_without_writing tests/test_web_api.py::test_preview_provider_plan_task_rejects_dangerous_path_without_writing -v
```

Expected: FAIL with `ImportError` for `preview_provider_plan_task`.

- [ ] **Step 3: Implement provider plan preview helper**

Modify imports in `src/dev_agent/web/api.py`:

```python
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.provider_plan import parse_provider_execution_plan
```

Add these helper functions above `run_dry_run_task()`:

```python
def _planned_changes(plan: ExecutionPlan) -> list[dict[str, object]]:
    return [operation.to_dict() for operation in plan.operations]


def _provider_preview(repo_root: Path, fake_response: str) -> tuple[ExecutionPlan, ExecutionResult]:
    try:
        plan = parse_provider_execution_plan(fake_response)
        preview = ExecutionPlanApplier(repo_root).preview(plan)
    except ExecutionPlanError as exc:
        message = str(exc)
        if message.startswith("无法解析 provider 执行计划"):
            raise ValueError(message) from exc
        raise ValueError(f"执行计划预览失败：{message}") from exc
    return plan, preview


def _provider_plan_payload(
    *,
    ok: bool,
    task_id: str | None,
    plan_text: str,
    dry_run: bool,
    planned_changes: list[dict[str, object]],
    preview_result: ExecutionResult,
    applied_changes: list[dict[str, object]] | None = None,
    diff_stat: str = "",
    execution_error: str | None = None,
) -> dict[str, object]:
    return {
        "ok": ok,
        "task_id": task_id,
        "plan_text": plan_text,
        "dry_run": dry_run,
        "planned_changes": planned_changes,
        "preview_changes": preview_result.preview_changes_as_dicts(),
        "applied_changes": applied_changes or [],
        "diff_stat": diff_stat,
        "execution_error": execution_error,
    }


def preview_provider_plan_task(repo_root: Path, request_text: str, fake_response: str) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for provider plan preview")
    plan, preview = _provider_preview(repo_root, fake_response)
    return _provider_plan_payload(
        ok=True,
        task_id=None,
        plan_text="",
        dry_run=True,
        planned_changes=_planned_changes(plan),
        preview_result=preview,
    )
```

- [ ] **Step 4: Run preview tests to verify pass**

Run:

```powershell
python -m pytest tests/test_web_api.py::test_preview_provider_plan_task_returns_preview_without_side_effects tests/test_web_api.py::test_preview_provider_plan_task_rejects_malformed_json_without_writing tests/test_web_api.py::test_preview_provider_plan_task_rejects_dangerous_path_without_writing -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Run Web API tests**

Run:

```powershell
python -m pytest tests/test_web_api.py -v
```

Expected: all Web API tests pass.

- [ ] **Step 6: Commit Web API preview**

Run:

```powershell
git add src/dev_agent/web/api.py tests/test_web_api.py
git commit -m "feat: preview provider plans in web api"
```

Expected: commit succeeds.

---

### Task 2: Web API Provider Plan Apply and HTTP Routes

**Files:**
- Modify: `src/dev_agent/web/api.py`
- Modify: `src/dev_agent/web/server.py`
- Modify: `tests/test_web_api.py`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Write failing Web API apply tests**

Append these tests to `tests/test_web_api.py`:

```python
def test_apply_provider_plan_task_writes_file_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = apply_provider_plan_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="确认 Web provider plan",
        fake_response=provider_plan_json(content="确认写入\n"),
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["task_id"]
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["applied_changes"][0]["path"] == "docs/from-web-provider.md"
    assert (tmp_path / "docs" / "from-web-provider.md").read_text(encoding="utf-8") == "确认写入\n"
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "确认 Web provider plan" in history


def test_apply_provider_plan_task_rechecks_preview_before_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "docs" / "from-web-provider.md", "已存在\n")

    with pytest.raises(ValueError, match="执行计划预览失败"):
        apply_provider_plan_task(
            repo_root=tmp_path,
            home_dir=tmp_path,
            request_text="确认 Web provider plan",
            fake_response=provider_plan_json(),
        )

    assert (tmp_path / "docs" / "from-web-provider.md").read_text(encoding="utf-8") == "已存在\n"
    assert not (tmp_path / ".agent").exists()
```

- [ ] **Step 2: Write failing HTTP route tests**

Append these tests to `tests/test_web_server.py`:

```python
def provider_plan_payload(path="docs/from-web-route.md", content="来自 Web route\n"):
    return {
        "request": "Web provider route",
        "fake_response": json.dumps(
            {
                "summary": "创建 Web route 文件",
                "operations": [
                    {
                        "action": "create_text",
                        "path": path,
                        "content": content,
                    }
                ],
            },
            ensure_ascii=False,
        ),
    }


def test_provider_plan_preview_route_returns_preview_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/preview",
            provider_plan_payload(),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is True
    assert payload["preview_changes"][0]["path"] == "docs/from-web-route.md"
    assert not (tmp_path / "docs" / "from-web-route.md").exists()
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_apply_route_writes_file_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            provider_plan_payload(content="确认 route 写入\n"),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is True
    assert payload["applied_changes"][0]["path"] == "docs/from-web-route.md"
    assert (tmp_path / "docs" / "from-web-route.md").read_text(encoding="utf-8") == "确认 route 写入\n"
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "Web provider route" in history


def test_provider_plan_preview_route_rejects_bad_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/preview",
            {"request": "坏 Web provider route", "fake_response": '{"summary":'},
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "无法解析 provider 执行计划" in payload["error"]
```

- [ ] **Step 3: Run apply and route tests to verify failure**

Run:

```powershell
python -m pytest tests/test_web_api.py::test_apply_provider_plan_task_writes_file_and_records_history tests/test_web_api.py::test_apply_provider_plan_task_rechecks_preview_before_writing tests/test_web_server.py::test_provider_plan_preview_route_returns_preview_without_writing tests/test_web_server.py::test_provider_plan_apply_route_writes_file_and_records_history tests/test_web_server.py::test_provider_plan_preview_route_rejects_bad_json -v
```

Expected: tests fail because `apply_provider_plan_task` and routes do not exist.

- [ ] **Step 4: Implement apply helper**

Append this function to `src/dev_agent/web/api.py` after `preview_provider_plan_task()`:

```python
def apply_provider_plan_task(
    repo_root: Path,
    home_dir: Path,
    request_text: str,
    fake_response: str,
) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for provider plan apply")
    plan, preview = _provider_preview(repo_root, fake_response)
    runner = LocalTaskRunner(
        repo_root=repo_root,
        home_dir=home_dir,
        provider=FakeProvider(name="fake-web-provider-plan", responses=[fake_response]),
    )
    result = runner.run(
        request_text,
        TaskRunOptions(
            dry_run=False,
            run_verification=False,
            apply_changes=True,
            execution_plan=plan,
        ),
    )
    return _provider_plan_payload(
        ok=True,
        task_id=result.task_id,
        plan_text=result.plan_text,
        dry_run=result.dry_run,
        planned_changes=result.planned_changes,
        preview_result=preview,
        applied_changes=result.applied_changes,
        diff_stat=result.diff_stat,
        execution_error=result.execution_error,
    )
```

- [ ] **Step 5: Implement HTTP routes**

Modify imports in `src/dev_agent/web/server.py`:

```python
from dev_agent.web.api import (
    apply_provider_plan_task,
    build_context_payload,
    build_health_payload,
    build_history_payload,
    preview_provider_plan_task,
    run_dry_run_task,
)
```

Add these branches in `DevAgentHttpHandler.handle_request()` before the `elif path == "/"` branch:

```python
            elif path == "/api/provider-plan/preview" and self.command == "POST":
                body = self._read_json_body()
                payload = preview_provider_plan_task(
                    repo_root=self.repo_root,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
            elif path == "/api/provider-plan/apply" and self.command == "POST":
                body = self._read_json_body()
                payload = apply_provider_plan_task(
                    repo_root=self.repo_root,
                    home_dir=self.home_dir,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
```

- [ ] **Step 6: Run apply and route tests**

Run:

```powershell
python -m pytest tests/test_web_api.py::test_apply_provider_plan_task_writes_file_and_records_history tests/test_web_api.py::test_apply_provider_plan_task_rechecks_preview_before_writing tests/test_web_server.py::test_provider_plan_preview_route_returns_preview_without_writing tests/test_web_server.py::test_provider_plan_apply_route_writes_file_and_records_history tests/test_web_server.py::test_provider_plan_preview_route_rejects_bad_json -v
```

Expected: all 5 tests pass.

- [ ] **Step 7: Run Web tests**

Run:

```powershell
python -m pytest tests/test_web_api.py tests/test_web_server.py -v
```

Expected: all Web tests pass.

- [ ] **Step 8: Commit Web apply routes**

Run:

```powershell
git add src/dev_agent/web/api.py src/dev_agent/web/server.py tests/test_web_api.py tests/test_web_server.py
git commit -m "feat: apply provider plans from web"
```

Expected: commit succeeds.

---

### Task 3: Web UI Two-Step Approval Flow

**Files:**
- Modify: `src/dev_agent/web/static/index.html`
- Modify: `src/dev_agent/web/static/app.js`
- Modify: `src/dev_agent/web/static/styles.css`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Write failing static asset test**

Modify `test_static_assets_include_console_interactions()` in `tests/test_web_server.py` to include these assertions:

```python
    index_status, index_type, index_body = get_text(f"{base_url}/")
```

The complete test should become:

```python
def test_static_assets_include_console_interactions(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        index_status, index_type, index_body = get_text(f"{base_url}/")
        css_status, css_type, css_body = get_text(f"{base_url}/static/styles.css")
        js_status, js_type, js_body = get_text(f"{base_url}/static/app.js")
    finally:
        server.shutdown()
        server.server_close()

    assert index_status == HTTPStatus.OK
    assert index_type == "text/html; charset=utf-8"
    assert "Provider plan 审批" in index_body
    assert "provider-plan-form" in index_body
    assert "confirm-provider-apply" in index_body
    assert css_status == HTTPStatus.OK
    assert css_type == "text/css; charset=utf-8"
    assert "--ink" in css_body
    assert "@media" in css_body
    assert ".approval-layout" in css_body
    assert ".danger" in css_body
    assert js_status == HTTPStatus.OK
    assert js_type == "text/javascript; charset=utf-8"
    assert "loadContext" in js_body
    assert "submitRun" in js_body
    assert "submitProviderPreview" in js_body
    assert "submitProviderApply" in js_body
    assert "/api/provider-plan/preview" in js_body
    assert "/api/provider-plan/apply" in js_body
```

- [ ] **Step 2: Run static asset test to verify failure**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because static files do not include provider plan approval UI.

- [ ] **Step 3: Update HTML with provider approval section**

Modify `src/dev_agent/web/static/index.html`. Replace the existing run panel article with this structure:

```html
        <article class="panel run-panel">
          <h2>提交 dry-run</h2>
          <form id="run-form">
            <label for="request">任务</label>
            <textarea id="request" name="request" required>整理当前项目状态，并给出下一步开发计划。</textarea>
            <label for="fake-response">Fake response</label>
            <textarea id="fake-response" name="fake_response" required>计划：读取上下文、检查历史、运行测试。</textarea>
            <button type="submit">生成计划</button>
          </form>
          <pre id="run-result" aria-live="polite">等待提交...</pre>
        </article>
        <article class="panel run-panel">
          <h2>Provider plan 审批</h2>
          <p class="helper">两步式安全流程：先生成预览，不写文件；确认执行后才应用结构化计划。</p>
          <form id="provider-plan-form">
            <div class="approval-layout">
              <div>
                <label for="provider-request">任务</label>
                <textarea id="provider-request" name="request" required>创建 Web provider 说明文件。</textarea>
                <label for="provider-fake-response">严格 JSON provider plan</label>
                <textarea id="provider-fake-response" name="fake_response" required>{
  "summary": "创建 Web provider 说明",
  "operations": [
    {
      "action": "create_text",
      "path": "docs/web-provider.md",
      "content": "来自 Web provider plan\n"
    }
  ]
}</textarea>
                <div class="button-row">
                  <button id="preview-provider-plan" type="submit">生成预览</button>
                  <button id="confirm-provider-apply" type="button" disabled>确认执行</button>
                </div>
              </div>
              <div>
                <h3>审批状态</h3>
                <p id="provider-status" class="status-pill">等待预览</p>
                <pre id="provider-preview-result" aria-live="polite">等待 provider plan 预览...</pre>
                <pre id="provider-apply-result" aria-live="polite">确认执行后显示结果。</pre>
                <p id="provider-error" class="danger" role="alert" hidden></p>
              </div>
            </div>
          </form>
        </article>
```

- [ ] **Step 4: Update JavaScript with two-step state**

Append these functions to `src/dev_agent/web/static/app.js` after `submitRun()`:

```javascript
let lastProviderPreview = null;

const providerForm = () => document.getElementById("provider-plan-form");
const providerPreviewButton = () => document.getElementById("preview-provider-plan");
const providerApplyButton = () => document.getElementById("confirm-provider-apply");
const providerStatus = () => document.getElementById("provider-status");
const providerError = () => document.getElementById("provider-error");

const setProviderBusy = (busy) => {
  providerPreviewButton().disabled = busy;
  providerApplyButton().disabled = busy || lastProviderPreview === null;
};

const showProviderError = (message) => {
  providerError().hidden = false;
  providerError().textContent = message;
};

const clearProviderError = () => {
  providerError().hidden = true;
  providerError().textContent = "";
};

const postJson = async (path, payload) => {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "请求失败，请检查本地服务是否仍在运行。");
  }
  return body;
};

async function submitProviderPreview(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearProviderError();
  lastProviderPreview = null;
  providerStatus().textContent = "正在生成预览";
  renderJson("provider-apply-result", "确认执行后显示结果。");
  setProviderBusy(true);
  try {
    const payload = await postJson("/api/provider-plan/preview", {
      request: form.elements.request.value,
      fake_response: form.elements.fake_response.value,
    });
    lastProviderPreview = payload;
    renderJson("provider-preview-result", payload);
    providerStatus().textContent = "预览通过，可以确认执行";
  } catch (error) {
    renderJson("provider-preview-result", "预览失败。");
    providerStatus().textContent = "预览失败";
    showProviderError(error.message);
  } finally {
    setProviderBusy(false);
  }
}

async function submitProviderApply() {
  const form = providerForm();
  clearProviderError();
  providerStatus().textContent = "正在执行";
  setProviderBusy(true);
  try {
    const payload = await postJson("/api/provider-plan/apply", {
      request: form.elements.request.value,
      fake_response: form.elements.fake_response.value,
    });
    renderJson("provider-apply-result", payload);
    providerStatus().textContent = payload.execution_error ? "执行失败" : "执行完成";
    await loadHistory();
  } catch (error) {
    renderJson("provider-apply-result", "执行失败。");
    providerStatus().textContent = "执行失败";
    showProviderError(error.message);
  } finally {
    setProviderBusy(false);
  }
}
```

Update event listeners at the bottom of `app.js`:

```javascript
document.getElementById("run-form").addEventListener("submit", submitRun);
providerForm().addEventListener("submit", submitProviderPreview);
providerApplyButton().addEventListener("click", submitProviderApply);
loadHealth();
loadContext();
loadHistory();
```

- [ ] **Step 5: Update CSS for approval UI**

Append to `src/dev_agent/web/static/styles.css` before `@keyframes rise-in`:

```css
.helper {
  margin: 12px 0 0;
  color: var(--muted);
  line-height: 1.7;
}

.approval-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.9fr);
  gap: 18px;
  align-items: start;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.48;
  transform: none;
  box-shadow: none;
}

.status-pill {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  margin: 14px 0 0;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 8px 12px;
  color: var(--moss);
  background: rgba(255, 255, 255, 0.48);
  font-weight: 800;
}

.danger {
  margin: 12px 0 0;
  border: 1px solid rgba(154, 55, 45, 0.36);
  border-radius: 14px;
  padding: 12px;
  color: #7a251d;
  background: rgba(255, 238, 232, 0.86);
  line-height: 1.6;
}
```

Inside the existing `@media (max-width: 860px)` block, add:

```css
  .approval-layout {
    grid-template-columns: 1fr;
  }

  .button-row {
    flex-direction: column;
  }
```

- [ ] **Step 6: Run static asset test**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: test passes.

- [ ] **Step 7: Run Web server tests**

Run:

```powershell
python -m pytest tests/test_web_server.py -v
```

Expected: all Web server tests pass.

- [ ] **Step 8: Commit Web UI**

Run:

```powershell
git add src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css tests/test_web_server.py
git commit -m "feat: add web provider plan approval UI"
```

Expected: commit succeeds.

---

### Task 4: Final Verification and Smoke

**Files:**
- Verify: full test suite and Web smoke commands.

- [ ] **Step 1: Run final full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI capability smoke**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

Expected: each command exits 0; `serve --check` prints a local URL.

- [ ] **Step 3: Run temporary Web API smoke**

Run this PowerShell command. It writes a UTF-8 no-BOM temporary Python script to avoid PowerShell JSON argv quoting issues:

```powershell
$script = @'
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

repo = Path.cwd()
smoke = Path(tempfile.mkdtemp(prefix="dev-agent-web-approval-smoke-"))
(smoke / "pyproject.toml").write_text('[project]\nname = "sample"\n', encoding="utf-8")
env = os.environ.copy()
env["PYTHONPATH"] = str(repo / "src")
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
sys.path.insert(0, str(repo / "src"))

from dev_agent.web.server import create_server

server = create_server(repo_root=smoke, home_dir=smoke, host="127.0.0.1", port=0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
host, port = server.server_address
base = f"http://{host}:{port}"

def post(path, payload):
    request = Request(
        base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))

provider_plan = json.dumps(
    {
        "summary": "创建 Web smoke 文件",
        "operations": [
            {
                "action": "create_text",
                "path": "docs/web-smoke.md",
                "content": "Web approval smoke\n",
            }
        ],
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
payload = {"request": "Web approval smoke", "fake_response": provider_plan}
preview_status, preview_body = post("/api/provider-plan/preview", payload)
preview_file_exists = (smoke / "docs" / "web-smoke.md").exists()
preview_agent_exists = (smoke / ".agent").exists()
apply_status, apply_body = post("/api/provider-plan/apply", payload)
apply_content = (smoke / "docs" / "web-smoke.md").read_text(encoding="utf-8")
history_status, history_body = post("/api/provider-plan/preview", {"request": "bad", "fake_response": '{"summary":'})

server.shutdown()
server.server_close()

summary = {
    "smoke_dir": str(smoke),
    "preview_status": preview_status,
    "preview_has_preview_changes": bool(preview_body.get("preview_changes")),
    "preview_created_file": preview_file_exists,
    "preview_created_agent_dir": preview_agent_exists,
    "apply_status": apply_status,
    "apply_has_applied_changes": bool(apply_body.get("applied_changes")),
    "apply_content": apply_content,
    "bad_json_status": history_status,
    "bad_json_error": history_body.get("error"),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
assert preview_status == 200
assert preview_body["ok"] is True
assert preview_body["preview_changes"]
assert not preview_file_exists
assert not preview_agent_exists
assert apply_status == 200
assert apply_body["ok"] is True
assert apply_body["applied_changes"]
assert apply_content == "Web approval smoke\n"
assert history_status == 400
assert "无法解析 provider 执行计划" in history_body["error"]
'@
$scriptPath = Join-Path $env:TEMP ('dev-agent-web-approval-smoke-' + [System.Guid]::NewGuid().ToString('N') + '.py')
[System.IO.File]::WriteAllText($scriptPath, $script, [System.Text.UTF8Encoding]::new($false))
python $scriptPath
```

Expected:

- Preview returns 200 and includes `preview_changes`.
- Preview does not create `.agent` and does not write `docs/web-smoke.md`.
- Apply returns 200, writes `docs/web-smoke.md`, and returns `applied_changes`.
- Malformed provider JSON returns 400.

- [ ] **Step 4: Optional browser smoke**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
python -m dev_agent.cli serve --port 8765
```

Expected: open `http://127.0.0.1:8765/`, confirm the page includes “Provider plan 审批”, generate preview with the default JSON, then confirm execution in a temporary repository only. Do not run this smoke against the development repository unless you intentionally want the sample file written.

- [ ] **Step 5: Check final git status and recent commits**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -8
```

Expected: worktree is clean; recent commits include design, Web API preview, Web apply routes, and Web UI.

---

## Self-Review

**Spec coverage:** Tasks cover preview endpoint, apply endpoint, apply-before-write re-preview, HTTP routing, front-end two-step state, error display, dry-run compatibility, final tests and temporary Web API smoke.

**Scope control:** No task introduces real model calls, provider probing, batch retry, Git write automation, delete/move operations, Markdown extraction, approval token persistence, or multi-user queueing.

**Placeholder scan:** The plan contains concrete paths, helper names, test names, code snippets, commands, expected failures and expected passes. It contains no unfinished marker patterns.

**Type consistency:** `preview_provider_plan_task()`, `apply_provider_plan_task()`, `_provider_preview()`, `_provider_plan_payload()`, `planned_changes`, `preview_changes`, `applied_changes`, `diff_stat`, `execution_error`, `/api/provider-plan/preview`, and `/api/provider-plan/apply` are defined before later tasks depend on them.
