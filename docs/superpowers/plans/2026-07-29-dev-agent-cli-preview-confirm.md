# CLI 执行预览与确认 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `run --plan-file` 增加可审阅预览和显式确认闸门，确保本地结构化计划只有在用户确认后才会写入文件。

**Architecture:** 在 `dev_agent.execution` 层扩展预览数据模型和 `ExecutionPlanApplier.preview()`，集中复用路径安全、操作冲突和目标状态判断。CLI 读取计划后先生成预览，输出 `preview_changes`，并在 `--apply` 时要求 `--yes` 或交互式确认，再调用现有 runner apply 流程。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、argparse、json、pytest、Windows PowerShell、UTF-8 文本读写。

---

## Scope Check

本计划覆盖已批准 spec 中的 CLI 执行预览与确认 v1：执行计划预览摘要、`--preview`、`--apply --yes`、未确认拒绝写入、预览失败不写入、UTF-8 中文可读和最终 smoke。

本计划不实现真实 provider 输出解析、Web 写文件、Web 审批视图、Git 写操作、删除/移动文件、完整 unified diff 或事务回滚。

## File Structure

- Modify: `src/dev_agent/execution/models.py`，新增 `ExecutionPreviewChange`，让 `ExecutionResult` 携带 preview changes。
- Modify: `src/dev_agent/execution/applier.py`，让 `preview()` 做完整预校验并返回目标状态和风险标签。
- Modify: `src/dev_agent/cli.py`，新增 `--preview`、`--yes`、预览失败错误处理和 apply 确认逻辑。
- Modify: `tests/test_execution_applier.py`，覆盖预览模型、风险标签和预览失败不写入。
- Modify: `tests/test_cli.py`，覆盖 CLI 预览、未确认 apply 拒绝、`--apply --yes` 成功和预览失败返回 2。

---

### Task 1: Execution Preview Model and Applier Preview

**Files:**
- Modify: `src/dev_agent/execution/models.py`
- Modify: `src/dev_agent/execution/applier.py`
- Modify: `tests/test_execution_applier.py`

- [ ] **Step 1: Write failing preview tests**

Append to `tests/test_execution_applier.py`:

```python
def test_applier_preview_reports_target_state_bytes_and_risk(tmp_path) -> None:
    write_text_utf8(tmp_path / "existing.md", "旧内容\n")
    plan = ExecutionPlan(
        summary="预览",
        operations=[
            ExecutionOperation("create_text", "docs/new.md", "# 新文件\n"),
            ExecutionOperation("overwrite_text", "existing.md", "新内容\n"),
            ExecutionOperation("append_text", "logs/new.md", "追加\n"),
            ExecutionOperation("append_text", "existing.md", "继续追加\n"),
        ],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    assert result.applied is False
    assert result.preview_changes_as_dicts() == [
        {
            "action": "create_text",
            "path": "docs/new.md",
            "exists": False,
            "content_bytes": len("# 新文件\n".encode("utf-8")),
            "risk": "create",
        },
        {
            "action": "overwrite_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("新内容\n".encode("utf-8")),
            "risk": "overwrite",
        },
        {
            "action": "append_text",
            "path": "logs/new.md",
            "exists": False,
            "content_bytes": len("追加\n".encode("utf-8")),
            "risk": "append_create",
        },
        {
            "action": "append_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("继续追加\n".encode("utf-8")),
            "risk": "append",
        },
    ]
    assert not (tmp_path / "docs" / "new.md").exists()
    assert read_text_utf8(tmp_path / "existing.md") == "旧内容\n"


def test_applier_preview_rejects_create_conflict_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    plan = ExecutionPlan(
        summary="冲突",
        operations=[
            ExecutionOperation("create_text", "docs/first.md", "first\n"),
            ExecutionOperation("create_text", "README.md", "# new\n"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).preview(plan)

    assert not (tmp_path / "docs" / "first.md").exists()
    assert read_text_utf8(tmp_path / "README.md") == "# existing\n"
```

- [ ] **Step 2: Run preview tests to verify failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest tests/test_execution_applier.py -v
```

Expected: FAIL because `ExecutionResult` has no `preview_changes_as_dicts()` and `preview()` does not return preview details.

- [ ] **Step 3: Add preview model**

Modify `src/dev_agent/execution/models.py`:

```python
@dataclass(frozen=True)
class ExecutionPreviewChange:
    action: str
    path: str
    exists: bool
    content_bytes: int
    risk: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Modify `ExecutionResult`:

```python
@dataclass(frozen=True)
class ExecutionResult:
    applied: bool
    planned_changes: list[dict[str, object]]
    preview_changes: list[ExecutionPreviewChange] = field(default_factory=list)
    changes: list[ExecutionChange] = field(default_factory=list)
    diff_stat: str = ""
    error: str | None = None

    def preview_changes_as_dicts(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.preview_changes]

    def changes_as_dicts(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.changes]
```

- [ ] **Step 4: Implement applier preview details**

Modify imports in `src/dev_agent/execution/applier.py`:

```python
from dev_agent.execution.models import ExecutionChange, ExecutionPlan, ExecutionPreviewChange, ExecutionResult
```

Replace `preview()` and add helpers:

```python
    def preview(self, plan: ExecutionPlan) -> ExecutionResult:
        preview_changes = self._preview_changes(plan)
        return ExecutionResult(
            applied=False,
            planned_changes=self.planned_changes(plan),
            preview_changes=preview_changes,
        )

    def _preview_changes(self, plan: ExecutionPlan) -> list[ExecutionPreviewChange]:
        self._validate_operations(plan)
        return [
            ExecutionPreviewChange(
                action=operation.action,
                path=operation.path,
                exists=self._resolve_target(operation.path).exists(),
                content_bytes=len(operation.content.encode(UTF8)),
                risk=self._risk_for_operation(operation),
            )
            for operation in plan.operations
        ]

    def _risk_for_operation(self, operation: ExecutionOperation) -> str:
        target_exists = self._resolve_target(operation.path).exists()
        if operation.action == "create_text":
            return "create"
        if operation.action == "overwrite_text":
            return "overwrite"
        if operation.action == "append_text" and target_exists:
            return "append"
        if operation.action == "append_text":
            return "append_create"
        raise ExecutionPlanError(f"unsupported action: {operation.action}")
```

Also add `ExecutionOperation` to the imports from `dev_agent.execution.models`.

- [ ] **Step 5: Run applier tests**

Run:

```powershell
python -m pytest tests/test_execution_applier.py -v
```

Expected: all applier tests pass.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit preview model and applier**

Run:

```powershell
git add src/dev_agent/execution/models.py src/dev_agent/execution/applier.py tests/test_execution_applier.py
git commit -m "feat: preview execution plan changes"
```

Expected: commit succeeds.

---

### Task 2: CLI Preview Output

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI preview tests**

Append to `tests/test_cli.py`:

```python
def test_run_preview_outputs_preview_changes_without_writing(tmp_path: Path) -> None:
    write_target = tmp_path / "docs" / "preview.md"
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "预览中文\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览计划",
        "--fake-response",
        "计划：只预览。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["preview_changes"] == [
        {
            "action": "create_text",
            "path": "docs/preview.md",
            "exists": False,
            "content_bytes": len("预览中文\n".encode("utf-8")),
            "risk": "create",
        }
    ]
    assert payload["applied_changes"] == []
    assert not write_target.exists()
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_preview_outputs_preview_changes_without_writing -v
```

Expected: FAIL because `run` does not accept `--preview`.

- [ ] **Step 3: Add CLI preview support**

Modify imports in `src/dev_agent/cli.py`:

```python
from dev_agent.execution.applier import ExecutionPlanApplier
```

Add helper above `run_command`:

```python
def _preview_execution_plan(plan):
    if plan is None:
        return []
    return ExecutionPlanApplier(Path.cwd()).preview(plan).preview_changes_as_dicts()
```

Modify `run_command()` after loading `execution_plan`:

```python
    try:
        preview_changes = _preview_execution_plan(execution_plan)
    except ExecutionPlanError as exc:
        sys.stderr.write(f"执行计划预览失败：{exc}\n")
        return 2
```

Add `preview_changes` to the output payload:

```python
        "preview_changes": preview_changes,
```

Register parser argument:

```python
    run_parser.add_argument("--preview", action="store_true")
```

The first implementation does not need special branching for `args.preview`; because `--plan-file` without `--apply` already previews without writing. The flag exists to make the intent explicit and stable for scripts.

- [ ] **Step 4: Run CLI preview test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_preview_outputs_preview_changes_without_writing -v
```

Expected: PASS.

- [ ] **Step 5: Update existing non-apply preview assertion**

Modify `test_run_previews_plan_file_without_apply` in `tests/test_cli.py` to also assert preview details:

```python
    assert payload["planned_changes"][0]["path"] == "docs/preview.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["preview_changes"][0]["content_bytes"] == len("只预览\n".encode("utf-8"))
    assert payload["applied_changes"] == []
```

- [ ] **Step 6: Run all CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass except the old direct apply behavior still passes until Task 3 changes it.

- [ ] **Step 7: Run all tests and commit CLI preview**

Run:

```powershell
python -m pytest -v
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: show CLI execution plan previews"
```

Expected: tests pass and commit succeeds.

---

### Task 3: CLI Apply Confirmation Gate

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Replace old direct apply success test with failing confirmation tests**

Modify `test_run_applies_plan_file_and_reports_changes` so it includes `--yes`:

```python
    result = run_cli(
        tmp_path,
        "run",
        "创建说明",
        "--fake-response",
        "计划：创建说明文件。",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--yes",
    )
```

Append this new test to `tests/test_cli.py`:

```python
def test_run_apply_without_confirmation_rejects_and_does_not_write(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "需要确认",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/needs-confirmation.md",
                        "content": "不应写入\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "未确认执行",
        "--fake-response",
        "计划：需要确认。",
        "--plan-file",
        str(plan_file),
        "--apply",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert not (tmp_path / "docs" / "needs-confirmation.md").exists()
```

- [ ] **Step 2: Run confirmation tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_apply_without_confirmation_rejects_and_does_not_write tests/test_cli.py::test_run_applies_plan_file_and_reports_changes -v
```

Expected: the new unconfirmed apply test FAILS because current CLI writes without confirmation; the updated `--yes` test FAILS because `--yes` is not registered.

- [ ] **Step 3: Implement confirmation helpers**

Add helper functions above `run_command` in `src/dev_agent/cli.py`:

```python
def _confirm_apply(args: Namespace) -> bool:
    if not args.apply:
        return True
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    sys.stderr.write("应用执行计划需要确认。输入 yes 继续：")
    answer = sys.stdin.readline().strip()
    return answer == "yes"
```

Modify `run_command()` after successful preview:

```python
    if not _confirm_apply(args):
        sys.stderr.write("应用执行计划需要确认；请传入 --yes 或在交互式终端输入 yes。\n")
        return 2
```

Register parser argument:

```python
    run_parser.add_argument("--yes", action="store_true")
```

- [ ] **Step 4: Run confirmation tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_apply_without_confirmation_rejects_and_does_not_write tests/test_cli.py::test_run_applies_plan_file_and_reports_changes -v
```

Expected: both tests pass.

- [ ] **Step 5: Run all CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 6: Run all tests and commit confirmation gate**

Run:

```powershell
python -m pytest -v
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: require confirmation before applying plans"
```

Expected: tests pass and commit succeeds.

---

### Task 4: Preview Failure Handling and Final Verification

**Files:**
- Modify: `tests/test_cli.py`
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Add failing CLI preview failure test**

Append to `tests/test_cli.py`:

```python
def test_run_preview_rejects_create_conflict_without_writing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# existing\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "冲突预览",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "README.md",
                        "content": "# new\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览冲突",
        "--fake-response",
        "计划：冲突。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 2
    assert "执行计划预览失败" in result.stderr
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# existing\n"
```

- [ ] **Step 2: Run preview failure test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_run_preview_rejects_create_conflict_without_writing -v
```

Expected: PASS if Task 2 already routes preview validation errors to CLI error; if it fails, adjust only the `except ExecutionPlanError` block in `run_command()`.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Run CLI smoke with current source path**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

Expected: each command exits 0; `doctor` reports runtime and web capabilities; `serve --check` prints a local URL.

- [ ] **Step 5: Run temporary repository preview/apply smoke**

Run:

```powershell
$smoke = Join-Path $env:TEMP ('dev-agent-preview-smoke-' + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $smoke | Out-Null
Set-Content -LiteralPath (Join-Path $smoke 'pyproject.toml') -Value "[project]`nname = `"sample`"`n" -Encoding UTF8
$planPath = Join-Path $smoke 'plan.json'
$planJson = @{
  summary = '创建 CLI 预览确认 smoke 文件'
  operations = @(
    @{
      action = 'create_text'
      path = 'docs/preview-smoke.md'
      content = "CLI 预览确认 smoke`n"
    }
  )
} | ConvertTo-Json -Depth 5
Set-Content -LiteralPath $planPath -Value $planJson -Encoding UTF8
Push-Location $smoke
python -m dev_agent.cli run "预览执行计划" --fake-response "计划：只预览。" --plan-file $planPath --preview
python -m dev_agent.cli run "未确认执行计划" --fake-response "计划：不应写入。" --plan-file $planPath --apply
python -m dev_agent.cli run "确认执行计划" --fake-response "计划：写入。" --plan-file $planPath --apply --yes
Pop-Location
```

Expected:

- Preview command exits 0 and includes `preview_changes`.
- Unconfirmed apply exits 2 and does not create `docs/preview-smoke.md`.
- Confirmed apply exits 0 and creates `docs/preview-smoke.md`.

- [ ] **Step 6: Check repository status and commit final test if needed**

Run:

```powershell
git status --short
git log --oneline --decorate -6
```

Expected: worktree is clean after commits; recent commits include design, preview model, CLI preview output, and confirmation gate. If Task 4 added only tests after Task 3 commit, commit them:

```powershell
git add tests/test_cli.py
git commit -m "test: cover CLI preview conflicts"
```

---

## Self-Review

**Spec coverage:** Tasks cover preview data, CLI `--preview`, unconfirmed apply rejection, `--apply --yes`, preview failure errors, UTF-8 byte counts, and final smoke.

**Scope control:** No task calls real providers, opens Web write access, performs Git writes from runtime, adds delete/move operations, or introduces full diff rendering.

**Placeholder scan:** The plan contains concrete paths, tests, implementation snippets, commands, expected failures, expected passes, and commit commands. It contains no unfinished markers.

**Type consistency:** `ExecutionPreviewChange`, `ExecutionResult.preview_changes`, `preview_changes_as_dicts()`, `ExecutionPlanApplier.preview()`, CLI `preview_changes`, `--preview`, and `--yes` are defined before later tasks rely on them.
