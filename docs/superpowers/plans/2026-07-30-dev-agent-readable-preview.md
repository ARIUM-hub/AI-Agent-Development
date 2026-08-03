# Human-Readable Execution Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded human-readable text snippets to execution preview payloads so CLI and Web approvals show what content will be created, overwritten, or appended.

**Architecture:** Extend the execution preview model at the source of truth: `ExecutionPreviewChange`. `ExecutionPlanApplier` generates a small deterministic content preview from `ExecutionOperation.content`, and existing CLI/Web JSON paths inherit the new fields through `preview_changes_as_dicts()`.

**Tech Stack:** Python 3.13, dataclasses, pytest, local fake provider plan tests, PowerShell UTF-8 command setup.

---

## File Structure

- Modify: `src/dev_agent/execution/models.py`
  - Add `content_preview`, `content_preview_truncated`, `content_preview_line_count`, and `content_preview_char_count` fields to `ExecutionPreviewChange`.
- Modify: `src/dev_agent/execution/applier.py`
  - Add preview limits and a focused helper that derives bounded text preview metadata from operation content.
- Modify: `tests/test_execution_applier.py`
  - Update the existing preview payload assertion.
  - Add focused tests for line truncation, character truncation, empty content, and Chinese readability.
- Modify: `tests/test_cli.py`
  - Assert CLI preview JSON includes the new content preview fields for plan-file and provider-plan paths.
- Modify: `tests/test_web_api.py`
  - Assert Web preview/apply payloads include the new content preview fields.

## Task 1: Add Failing Execution Preview Tests

**Files:**
- Modify: `tests/test_execution_applier.py`
- Test: `tests/test_execution_applier.py`

- [ ] **Step 1: Update the existing preview payload test with expected preview fields**

In `tests/test_execution_applier.py`, replace the expected dictionaries inside `test_applier_preview_reports_target_state_bytes_and_risk` so each preview change includes content preview metadata:

```python
    assert result.preview_changes_as_dicts() == [
        {
            "action": "create_text",
            "path": "docs/new.md",
            "exists": False,
            "content_bytes": len("# 新文件\n".encode("utf-8")),
            "risk": "create",
            "content_preview": "# 新文件\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("# 新文件\n"),
        },
        {
            "action": "overwrite_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("新内容\n".encode("utf-8")),
            "risk": "overwrite",
            "content_preview": "新内容\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("新内容\n"),
        },
        {
            "action": "append_text",
            "path": "logs/new.md",
            "exists": False,
            "content_bytes": len("追加\n".encode("utf-8")),
            "risk": "append_create",
            "content_preview": "追加\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("追加\n"),
        },
        {
            "action": "append_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("继续追加\n".encode("utf-8")),
            "risk": "append",
            "content_preview": "继续追加\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("继续追加\n"),
        },
    ]
```

- [ ] **Step 2: Add truncation and empty-content tests**

Append these tests after `test_applier_preview_reports_target_state_bytes_and_risk`:

```python
def test_applier_preview_truncates_content_preview_by_lines(tmp_path) -> None:
    content = "一\n二\n三\n四\n五\n六\n七\n"
    plan = ExecutionPlan(
        summary="按行截断",
        operations=[ExecutionOperation("create_text", "docs/lines.md", content)],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == "一\n二\n三\n四\n五\n六\n"
    assert preview["content_preview_truncated"] is True
    assert preview["content_preview_line_count"] == 7
    assert preview["content_preview_char_count"] == len(content)
    assert not (tmp_path / "docs" / "lines.md").exists()


def test_applier_preview_truncates_content_preview_by_characters(tmp_path) -> None:
    content = "中" * 601
    plan = ExecutionPlan(
        summary="按字符截断",
        operations=[ExecutionOperation("create_text", "docs/chars.md", content)],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == "中" * 600
    assert preview["content_preview_truncated"] is True
    assert preview["content_preview_line_count"] == 1
    assert preview["content_preview_char_count"] == 601
    assert not (tmp_path / "docs" / "chars.md").exists()


def test_applier_preview_reports_empty_content_preview(tmp_path) -> None:
    plan = ExecutionPlan(
        summary="空内容",
        operations=[ExecutionOperation("append_text", "empty.md", "")],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == ""
    assert preview["content_preview_truncated"] is False
    assert preview["content_preview_line_count"] == 0
    assert preview["content_preview_char_count"] == 0
```

- [ ] **Step 3: Run execution tests to verify they fail**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_execution_applier.py::test_applier_preview_reports_target_state_bytes_and_risk tests/test_execution_applier.py::test_applier_preview_truncates_content_preview_by_lines tests/test_execution_applier.py::test_applier_preview_truncates_content_preview_by_characters tests/test_execution_applier.py::test_applier_preview_reports_empty_content_preview -v
```

Expected: FAIL because `ExecutionPreviewChange` does not yet expose `content_preview`, `content_preview_truncated`, `content_preview_line_count`, or `content_preview_char_count`.

## Task 2: Implement Preview Fields in the Execution Layer

**Files:**
- Modify: `src/dev_agent/execution/models.py`
- Modify: `src/dev_agent/execution/applier.py`
- Test: `tests/test_execution_applier.py`

- [ ] **Step 1: Extend `ExecutionPreviewChange`**

In `src/dev_agent/execution/models.py`, update the dataclass:

```python
@dataclass(frozen=True)
class ExecutionPreviewChange:
    action: str
    path: str
    exists: bool
    content_bytes: int
    risk: str
    content_preview: str
    content_preview_truncated: bool
    content_preview_line_count: int
    content_preview_char_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

- [ ] **Step 2: Add bounded content preview generation**

In `src/dev_agent/execution/applier.py`, add constants near the existing supported action constants:

```python
CONTENT_PREVIEW_MAX_LINES = 6
CONTENT_PREVIEW_MAX_CHARS = 600
```

Add this private helper before `_preview_changes()`:

```python
    def _content_preview_for_operation(self, operation: ExecutionOperation) -> dict[str, object]:
        content = operation.content
        line_parts = content.splitlines(keepends=True)
        line_count = len(content.splitlines())
        line_limited = "".join(line_parts[:CONTENT_PREVIEW_MAX_LINES])
        truncated_by_lines = len(line_parts) > CONTENT_PREVIEW_MAX_LINES
        if len(line_limited) > CONTENT_PREVIEW_MAX_CHARS:
            preview = line_limited[:CONTENT_PREVIEW_MAX_CHARS]
            truncated_by_chars = True
        else:
            preview = line_limited
            truncated_by_chars = False
        return {
            "content_preview": preview,
            "content_preview_truncated": truncated_by_lines or truncated_by_chars,
            "content_preview_line_count": line_count,
            "content_preview_char_count": len(content),
        }
```

Update `_preview_changes()` to pass those fields into the model:

```python
    def _preview_changes(self, plan: ExecutionPlan) -> list[ExecutionPreviewChange]:
        self._validate_operations(plan)
        return [
            ExecutionPreviewChange(
                action=operation.action,
                path=operation.path,
                exists=self._resolve_target(operation.path).exists(),
                content_bytes=len(operation.content.encode(UTF8)),
                risk=self._risk_for_operation(operation),
                **self._content_preview_for_operation(operation),
            )
            for operation in plan.operations
        ]
```

- [ ] **Step 3: Run focused execution tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_execution_applier.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit execution-layer implementation**

Run:

```powershell
git add -- src/dev_agent/execution/models.py src/dev_agent/execution/applier.py tests/test_execution_applier.py
git commit -m "feat: add readable execution previews"
```

## Task 3: Add CLI JSON Contract Coverage

**Files:**
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Update plan-file preview assertion**

In `tests/test_cli.py::test_run_preview_outputs_preview_changes_without_writing`, update the expected `preview_changes` item:

```python
    assert payload["preview_changes"] == [
        {
            "action": "create_text",
            "path": "docs/preview.md",
            "exists": False,
            "content_bytes": len("预览中文\n".encode("utf-8")),
            "risk": "create",
            "content_preview": "预览中文\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("预览中文\n"),
        }
    ]
```

- [ ] **Step 2: Update provider-plan preview assertion**

In `tests/test_cli.py::test_run_use_provider_plan_previews_provider_json_without_side_effects`, add these assertions after the existing risk assertion:

```python
    assert payload["preview_changes"][0]["content_preview"] == "来自 provider\n"
    assert payload["preview_changes"][0]["content_preview_truncated"] is False
    assert payload["preview_changes"][0]["content_preview_line_count"] == 1
    assert payload["preview_changes"][0]["content_preview_char_count"] == len("来自 provider\n")
```

- [ ] **Step 3: Run focused CLI tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_cli.py::test_run_preview_outputs_preview_changes_without_writing tests/test_cli.py::test_run_use_provider_plan_previews_provider_json_without_side_effects -v
```

Expected: PASS.

- [ ] **Step 4: Commit CLI contract tests**

Run:

```powershell
git add -- tests/test_cli.py
git commit -m "test: cover readable preview in cli"
```

## Task 4: Add Web API JSON Contract Coverage

**Files:**
- Modify: `tests/test_web_api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Update Web preview assertions**

In `tests/test_web_api.py::test_preview_provider_plan_task_returns_preview_without_side_effects`, add these assertions after the existing risk assertion:

```python
    assert payload["preview_changes"][0]["content_preview"] == "来自 Web provider\n"
    assert payload["preview_changes"][0]["content_preview_truncated"] is False
    assert payload["preview_changes"][0]["content_preview_line_count"] == 1
    assert payload["preview_changes"][0]["content_preview_char_count"] == len("来自 Web provider\n")
```

- [ ] **Step 2: Update Web apply assertions**

In `tests/test_web_api.py::test_apply_provider_plan_task_writes_file_and_records_history`, add these assertions after the existing preview risk assertion:

```python
    assert payload["preview_changes"][0]["content_preview"] == "确认写入\n"
    assert payload["preview_changes"][0]["content_preview_truncated"] is False
    assert payload["preview_changes"][0]["content_preview_line_count"] == 1
    assert payload["preview_changes"][0]["content_preview_char_count"] == len("确认写入\n")
```

- [ ] **Step 3: Run focused Web API tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_web_api.py::test_preview_provider_plan_task_returns_preview_without_side_effects tests/test_web_api.py::test_apply_provider_plan_task_writes_file_and_records_history -v
```

Expected: PASS.

- [ ] **Step 4: Commit Web API contract tests**

Run:

```powershell
git add -- tests/test_web_api.py
git commit -m "test: cover readable preview in web api"
```

## Task 5: Full Verification and Branch Readiness

**Files:**
- No code files changed in this task.
- Verify: entire repository.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: PASS with all tests passing.

- [ ] **Step 2: Run CLI smoke checks**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

Expected: each command exits `0`; `doctor` reports UTF-8 and local capabilities; `serve --check` returns a local URL JSON payload.

- [ ] **Step 3: Run a local provider preview smoke without real model calls**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$smoke = Join-Path $env:TEMP ('dev-agent-readable-preview-smoke-' + [System.Guid]::NewGuid().ToString('N') + '.py')
@'
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path.cwd()
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
env["PYTHONPATH"] = str(repo / "src")
plan = json.dumps(
    {
        "summary": "创建可读预览 smoke",
        "operations": [
            {
                "action": "create_text",
                "path": "docs/readable-preview-smoke.md",
                "content": "第一行\n第二行\n",
            }
        ],
    },
    ensure_ascii=False,
)
with tempfile.TemporaryDirectory(prefix="dev-agent-readable-preview-smoke-") as tmp:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev_agent.cli",
            "run",
            "预览可读内容",
            "--fake-response",
            plan,
            "--use-provider-plan",
            "--preview",
        ],
        cwd=tmp,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    payload = json.loads(result.stdout)
    assert payload["preview_changes"][0]["content_preview"] == "第一行\n第二行\n"
    assert not (Path(tmp) / "docs" / "readable-preview-smoke.md").exists()
    print("provider-preview-smoke-ok")
'@ | Set-Content -LiteralPath $smoke -Encoding UTF8
python $smoke
$code = $LASTEXITCODE
if ($code -eq 0) {
  Remove-Item -LiteralPath $smoke -Force
}
else {
  Write-Error "Smoke script kept for debugging: $smoke"
}
exit $code
```

Expected: command exits `0`; JSON `preview_changes[0]` includes `"content_preview": "第一行\n第二行\n"` and prints `provider-preview-smoke-ok`.

- [ ] **Step 4: Inspect git status and recent commits**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected: working tree is clean on `codex/dev-agent-readable-preview`, with implementation and test commits above the design/plan commits.

## Self-Review Checklist

- Spec coverage: Tasks cover execution model fields, deterministic line and character truncation, no full diff, no existing-file reads, CLI JSON propagation, Web preview/apply propagation, UTF-8 Chinese readability, and no real provider calls.
- Placeholder scan: This plan contains concrete file paths, code snippets, commands, and expected outcomes for each implementation step.
- Type consistency: Field names are consistently `content_preview`, `content_preview_truncated`, `content_preview_line_count`, and `content_preview_char_count`; helper name is consistently `_content_preview_for_operation()`.
