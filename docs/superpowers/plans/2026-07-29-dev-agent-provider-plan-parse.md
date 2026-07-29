# Provider 计划解析 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 CLI 能在显式 `--use-provider-plan` 模式下把 fake/provider 返回的严格 JSON 文本解析为安全的结构化执行计划。

**Architecture:** 新增 `dev_agent.execution.provider_plan` 纯解析模块，把 provider 文本解析为现有 `ExecutionPlan`。CLI 在 `--use-provider-plan` 时从 `args.fake_response` 构建计划，并复用现有 preview payload、确认闸门和 runner apply 流程；`--plan-file` 与 `--use-provider-plan` 同时出现时直接拒绝。

**Tech Stack:** Python 3.11+、json、argparse、dataclasses、pytest、Windows PowerShell、UTF-8 文本处理。

---

## Scope Check

本计划覆盖已批准 spec 中的 provider 计划解析 v1：严格 JSON provider plan 解析、CLI `--use-provider-plan`、provider plan preview 无副作用、apply 继续要求确认、非法 provider plan 和危险路径安全失败、最终 smoke 验证。

本计划不接真实云端 provider，不做多模型探测、批量重试、Markdown fenced JSON 解析、自然语言抽取、Web 写文件、Git 写操作、删除/移动文件或自动修复 JSON。

## File Structure

- Create: `src/dev_agent/execution/provider_plan.py`，负责从 provider 文本严格解析 `ExecutionPlan`。
- Create: `tests/test_provider_plan.py`，覆盖 provider 文本解析成功和失败。
- Modify: `src/dev_agent/cli.py`，新增 `--use-provider-plan`，抽象 execution plan 来源，复用 preview 和确认逻辑。
- Modify: `tests/test_cli.py`，覆盖 CLI provider plan preview/apply/error 行为。

---

### Task 1: Provider Plan Parser

**Files:**
- Create: `src/dev_agent/execution/provider_plan.py`
- Create: `tests/test_provider_plan.py`

- [ ] **Step 1: Write failing provider plan parser tests**

Create `tests/test_provider_plan.py`:

```python
import pytest

from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.provider_plan import parse_provider_execution_plan


def test_parse_provider_execution_plan_accepts_strict_json_object() -> None:
    plan = parse_provider_execution_plan(
        '{"summary":"创建说明","operations":[{"action":"create_text","path":"docs/provider.md","content":"来自 provider\\n"}]}'
    )

    assert plan.summary == "创建说明"
    assert plan.operations[0].action == "create_text"
    assert plan.operations[0].path == "docs/provider.md"
    assert plan.operations[0].content == "来自 provider\n"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "计划：创建说明文件。",
        '[{"action":"create_text","path":"docs/provider.md","content":"x"}]',
        '"not an object"',
        '{"summary":"缺少 operations"}',
        '{"summary":"坏 action","operations":[{"action":"delete_file","path":"README.md","content":""}]}',
        '{"summary":',
    ],
)
def test_parse_provider_execution_plan_rejects_invalid_provider_text(text: str) -> None:
    with pytest.raises(ExecutionPlanError, match="无法解析 provider 执行计划"):
        parse_provider_execution_plan(text)
```

- [ ] **Step 2: Run parser tests to verify failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_provider_plan.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.execution.provider_plan`.

- [ ] **Step 3: Implement strict provider plan parser**

Create `src/dev_agent/execution/provider_plan.py`:

```python
import json

from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def parse_provider_execution_plan(text: str) -> ExecutionPlan:
    try:
        data = json.loads(text.strip())
        return parse_execution_plan(data)
    except (json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ExecutionPlanError(f"无法解析 provider 执行计划：{exc}") from exc
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m pytest tests/test_provider_plan.py -v
```

Expected: all provider plan parser tests pass.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit provider plan parser**

Run:

```powershell
git add src/dev_agent/execution/provider_plan.py tests/test_provider_plan.py
git commit -m "feat: parse provider execution plans"
```

Expected: commit succeeds.

---

### Task 2: CLI Provider Plan Preview

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI provider preview tests**

Append to `tests/test_cli.py`:

```python
def test_run_use_provider_plan_previews_provider_json_without_side_effects(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "创建 provider 说明",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider.md",
                    "content": "来自 provider\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览 provider 计划",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["task_id"] is None
    assert payload["planned_changes"][0]["path"] == "docs/provider.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "provider.md").exists()


def test_run_without_use_provider_plan_keeps_fake_response_as_plain_text(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")
    provider_plan = json.dumps(
        {
            "summary": "不应解析",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/plain.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "普通 dry-run",
        "--fake-response",
        provider_plan,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plan_text"] == provider_plan
    assert payload["planned_changes"] == []
    assert payload["preview_changes"] == []
    assert (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "plain.md").exists()
```

- [ ] **Step 2: Run CLI preview tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_use_provider_plan_previews_provider_json_without_side_effects tests/test_cli.py::test_run_without_use_provider_plan_keeps_fake_response_as_plain_text -v
```

Expected: first test FAILS because `--use-provider-plan` is not registered; second test may pass or fail depending on current `preview_changes` default, but must pass after implementation.

- [ ] **Step 3: Add provider plan source helpers**

Modify imports in `src/dev_agent/cli.py`:

```python
from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.provider_plan import parse_provider_execution_plan
```

Add helper above `run_command`:

```python
def _resolve_execution_plan(args: Namespace) -> ExecutionPlan | None:
    if args.plan_file and args.use_provider_plan:
        raise ValueError("--plan-file 不能与 --use-provider-plan 同时使用")
    if args.use_provider_plan:
        return parse_provider_execution_plan(args.fake_response)
    return _load_execution_plan(args.plan_file)
```

Modify `run_command()` to use the helper:

```python
    try:
        execution_plan = _resolve_execution_plan(args)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    except ExecutionPlanError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
```

Register parser argument:

```python
    run_parser.add_argument("--use-provider-plan", action="store_true")
```

Keep the existing non-apply behavior:

```python
    if execution_plan is not None and not args.apply:
        sys.stdout.write(_json(_preview_payload(args, execution_plan, preview_changes)))
        return 0
```

- [ ] **Step 4: Run CLI provider preview tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_use_provider_plan_previews_provider_json_without_side_effects tests/test_cli.py::test_run_without_use_provider_plan_keeps_fake_response_as_plain_text -v
```

Expected: both tests pass.

- [ ] **Step 5: Run all CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 6: Run all tests and commit CLI provider preview**

Run:

```powershell
python -m pytest -v
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: preview provider execution plans"
```

Expected: tests pass and commit succeeds.

---

### Task 3: CLI Provider Plan Apply and Error Boundaries

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/dev_agent/cli.py` only if a test exposes a missing error branch.

- [ ] **Step 1: Add failing provider apply and error tests**

Append to `tests/test_cli.py`:

```python
def test_run_use_provider_plan_apply_requires_confirmation(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "需要确认",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider-confirm.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "未确认 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--apply",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert not (tmp_path / "docs" / "provider-confirm.md").exists()


def test_run_use_provider_plan_apply_yes_writes_file(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "确认写入",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider-apply.md",
                    "content": "确认写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "确认 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--apply",
        "--yes",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["applied_changes"][0]["path"] == "docs/provider-apply.md"
    assert (tmp_path / "docs" / "provider-apply.md").read_text(encoding="utf-8") == "确认写入\n"


def test_run_use_provider_plan_rejects_malformed_json_without_writing(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "坏 provider plan",
        "--fake-response",
        '{"summary":',
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 2
    assert "无法解析 provider 执行计划" in result.stderr
    assert not (tmp_path / ".agent").exists()


def test_run_use_provider_plan_rejects_dangerous_path_without_writing(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "危险路径",
            "operations": [
                {
                    "action": "create_text",
                    "path": "../escape.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "危险 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 2
    assert "执行计划预览失败" in result.stderr
    assert not (tmp_path.parent / "escape.md").exists()


def test_run_rejects_plan_file_with_use_provider_plan(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "文件计划",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/file.md",
                        "content": "file\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "来源歧义",
        "--fake-response",
        "{}",
        "--plan-file",
        str(plan_file),
        "--use-provider-plan",
    )

    assert result.returncode == 2
    assert "--plan-file 不能与 --use-provider-plan 同时使用" in result.stderr
    assert not (tmp_path / "docs" / "file.md").exists()
```

- [ ] **Step 2: Run provider CLI boundary tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_use_provider_plan_apply_requires_confirmation tests/test_cli.py::test_run_use_provider_plan_apply_yes_writes_file tests/test_cli.py::test_run_use_provider_plan_rejects_malformed_json_without_writing tests/test_cli.py::test_run_use_provider_plan_rejects_dangerous_path_without_writing tests/test_cli.py::test_run_rejects_plan_file_with_use_provider_plan -v
```

Expected: tests pass if Task 2 implementation already covers all branches; if any fail, make the smallest `src/dev_agent/cli.py` adjustment needed.

- [ ] **Step 3: Run all CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 4: Run all tests and commit provider apply boundaries**

Run:

```powershell
python -m pytest -v
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "test: cover provider plan CLI boundaries"
```

Expected: tests pass and commit succeeds. If `src/dev_agent/cli.py` had no changes in this task, commit only `tests/test_cli.py`.

---

### Task 4: Final Verification and Smoke

**Files:**
- Verify: full test suite and CLI smoke commands.

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

Expected: each command exits 0; `doctor` reports runtime and web capabilities; `serve --check` prints a local URL.

- [ ] **Step 3: Run provider plan temporary repository smoke**

Run:

```powershell
$script = @'
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path.cwd()
smoke = Path(tempfile.mkdtemp(prefix="dev-agent-provider-plan-smoke-"))
(smoke / "pyproject.toml").write_text('[project]\nname = "sample"\n', encoding="utf-8")
provider_plan = json.dumps(
    {
        "summary": "创建 provider plan smoke 文件",
        "operations": [
            {
                "action": "create_text",
                "path": "docs/provider-smoke.md",
                "content": "Provider plan smoke\n",
            }
        ],
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
env = os.environ.copy()
env["PYTHONPATH"] = str(repo / "src")
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dev_agent.cli", *args],
        cwd=smoke,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )

preview = run_cli("run", "预览 provider plan", "--fake-response", provider_plan, "--use-provider-plan", "--preview")
preview_file_exists = (smoke / "docs" / "provider-smoke.md").exists()
preview_agent_exists = (smoke / ".agent").exists()
unconfirmed = run_cli("run", "未确认 provider plan", "--fake-response", provider_plan, "--use-provider-plan", "--apply")
unconfirmed_file_exists = (smoke / "docs" / "provider-smoke.md").exists()
confirmed = run_cli("run", "确认 provider plan", "--fake-response", provider_plan, "--use-provider-plan", "--apply", "--yes")
confirmed_path = smoke / "docs" / "provider-smoke.md"
confirmed_content = confirmed_path.read_text(encoding="utf-8") if confirmed_path.exists() else None

print(json.dumps(
    {
        "smoke_dir": str(smoke),
        "preview_exit": preview.returncode,
        "preview_has_preview_changes": bool(json.loads(preview.stdout)["preview_changes"]) if preview.returncode == 0 else False,
        "preview_created_file": preview_file_exists,
        "preview_created_agent_dir": preview_agent_exists,
        "unconfirmed_exit": unconfirmed.returncode,
        "unconfirmed_created_file": unconfirmed_file_exists,
        "unconfirmed_stderr": unconfirmed.stderr.strip(),
        "confirmed_exit": confirmed.returncode,
        "confirmed_content": confirmed_content,
    },
    ensure_ascii=False,
    indent=2,
))

assert preview.returncode == 0, preview.stderr
assert json.loads(preview.stdout)["preview_changes"]
assert not preview_file_exists
assert not preview_agent_exists
assert unconfirmed.returncode == 2, unconfirmed.stderr
assert not unconfirmed_file_exists
assert "应用执行计划需要确认" in unconfirmed.stderr
assert confirmed.returncode == 0, confirmed.stderr
assert confirmed_content == "Provider plan smoke\n"
'@
$scriptPath = Join-Path $env:TEMP ('dev-agent-provider-plan-smoke-harness-' + [System.Guid]::NewGuid().ToString('N') + '.py')
[System.IO.File]::WriteAllText($scriptPath, $script, [System.Text.UTF8Encoding]::new($false))
python $scriptPath
```

Expected:

- Preview command exits 0, includes `preview_changes`, does not create `.agent`, and does not write `docs/provider-smoke.md`.
- Unconfirmed apply exits 2 and does not write `docs/provider-smoke.md`.
- Confirmed apply exits 0 and writes `docs/provider-smoke.md`.

Note: Windows PowerShell 5.1 may strip JSON double quotes when passing `ConvertTo-Json`
output directly to a native command. The smoke uses Python `subprocess.run([...])`
so the provider plan is passed as one argv value without shell re-quoting.

- [ ] **Step 4: Check final git status and recent commits**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -8
```

Expected: worktree is clean; recent commits include design, parser, CLI preview, provider boundary tests.

---

## Self-Review

**Spec coverage:** Tasks cover strict provider JSON parsing, explicit `--use-provider-plan`, source ambiguity rejection, preview without side effects, confirmation-gated apply, malformed JSON, dangerous paths, and smoke validation.

**Scope control:** No task introduces real model calls, multiple provider attempts, Markdown extraction, Web write access, Git write automation, delete/move operations, or schema versions.

**Unfinished marker scan:** The plan contains concrete paths, tests, implementation snippets, commands, expected failures, expected passes, and commit commands. It contains no unfinished markers.

**Type consistency:** `parse_provider_execution_plan()`, `_resolve_execution_plan()`, `--use-provider-plan`, `ExecutionPlan`, `ExecutionPlanError`, `preview_changes`, and existing confirmation helpers are defined before later tasks rely on them.
