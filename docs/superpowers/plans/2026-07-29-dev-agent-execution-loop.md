# 本地执行闭环 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个安全的本地执行闭环，让 `run` 可以在显式结构化计划下应用小型 UTF-8 文本文件修改、运行验证并写入历史。

**Architecture:** 新增 `dev_agent.execution` 包，负责结构化计划解析、路径安全校验和文本写入。`LocalTaskRunner` 通过 `TaskRunOptions` 接收可选执行计划，只有 `apply_changes=True` 时才落盘；CLI 通过 `--plan-file --apply` 暴露该能力，Web `/api/run` 保持 fake-provider dry-run。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、json、argparse、pytest、Windows PowerShell、UTF-8 文本读写。

---

## Scope Check

本计划覆盖已批准 spec 中的“本地执行闭环 v1”：结构化执行计划、仓库内路径保护、UTF-8 文本创建/覆盖/追加、运行时 apply 集成、CLI plan-file 入口、Web dry-run 不写文件回归、完整验证。

本计划不实现真实模型输出解析、自动补丁生成、删除/移动文件、Git commit/push、Web 审批视图、并发执行或事务回滚。

## File Structure

- Create: `src/dev_agent/execution/__init__.py`，执行包说明。
- Create: `src/dev_agent/execution/models.py`，定义执行计划、操作、变更和结果模型。
- Create: `src/dev_agent/execution/plan.py`，从 JSON dict 解析并校验结构化计划。
- Create: `src/dev_agent/execution/applier.py`，执行路径安全校验和 UTF-8 文本操作。
- Modify: `src/dev_agent/runtime/models.py`，扩展 `TaskRunOptions` 和 `TaskRunResult`。
- Modify: `src/dev_agent/runtime/runner.py`，接入执行器、diff stat、失败历史。
- Modify: `src/dev_agent/cli.py`，新增 `--plan-file`、`--apply` 和输出字段。
- Modify: `src/dev_agent/web/api.py`，增加回归保护，确保 Web dry-run 不应用计划。
- Create: `tests/test_execution_plan.py`，覆盖计划解析。
- Create: `tests/test_execution_applier.py`，覆盖路径安全和文本写入。
- Modify: `tests/test_runtime_runner.py`，覆盖运行时 apply 成功与失败。
- Modify: `tests/test_cli.py`，覆盖 CLI plan-file apply 和错误输出。
- Modify: `tests/test_web_api.py`，覆盖 Web run 不写文件。

---

### Task 1: Execution Plan Models and Parser

**Files:**
- Create: `src/dev_agent/execution/__init__.py`
- Create: `src/dev_agent/execution/models.py`
- Create: `src/dev_agent/execution/plan.py`
- Test: `tests/test_execution_plan.py`

- [ ] **Step 1: Write failing plan parser tests**

Create `tests/test_execution_plan.py`:

```python
import pytest

from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def test_parse_execution_plan_accepts_text_operations() -> None:
    plan = parse_execution_plan(
        {
            "summary": "创建说明",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/local-execution.md",
                    "content": "# 本地执行\n",
                },
                {
                    "action": "append_text",
                    "path": "README.md",
                    "content": "补充说明\n",
                },
            ],
        }
    )

    assert plan.summary == "创建说明"
    assert plan.operations[0].action == "create_text"
    assert plan.operations[0].path == "docs/local-execution.md"
    assert plan.operations[0].content == "# 本地执行\n"
    assert plan.operations[1].action == "append_text"


def test_parse_execution_plan_rejects_missing_operations() -> None:
    with pytest.raises(ExecutionPlanError, match="operations"):
        parse_execution_plan({"summary": "缺少操作"})


def test_parse_execution_plan_rejects_unknown_action() -> None:
    with pytest.raises(ExecutionPlanError, match="unsupported action"):
        parse_execution_plan(
            {
                "summary": "危险操作",
                "operations": [
                    {
                        "action": "delete_file",
                        "path": "README.md",
                        "content": "",
                    }
                ],
            }
        )


def test_parse_execution_plan_rejects_non_string_content() -> None:
    with pytest.raises(ExecutionPlanError, match="content"):
        parse_execution_plan(
            {
                "summary": "内容类型错误",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "README.md",
                        "content": 123,
                    }
                ],
            }
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest tests/test_execution_plan.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.execution`.

- [ ] **Step 3: Implement execution models**

Create `src/dev_agent/execution/__init__.py`:

```python
"""Safe local execution plan support."""
```

Create `src/dev_agent/execution/models.py`:

```python
from dataclasses import asdict, dataclass, field


SUPPORTED_ACTIONS = {"create_text", "overwrite_text", "append_text"}


@dataclass(frozen=True)
class ExecutionOperation:
    action: str
    path: str
    content: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    summary: str
    operations: list[ExecutionOperation] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "operations": [operation.to_dict() for operation in self.operations],
        }


@dataclass(frozen=True)
class ExecutionChange:
    action: str
    path: str
    before_exists: bool
    after_exists: bool
    bytes_written: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionResult:
    applied: bool
    planned_changes: list[dict[str, object]]
    changes: list[ExecutionChange] = field(default_factory=list)
    diff_stat: str = ""
    error: str | None = None

    def changes_as_dicts(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.changes]
```

- [ ] **Step 4: Implement plan parser**

Create `src/dev_agent/execution/plan.py`:

```python
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan, SUPPORTED_ACTIONS


class ExecutionPlanError(ValueError):
    pass


def parse_execution_plan(data: dict[str, object]) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ExecutionPlanError("execution plan must be a JSON object")
    operations_data = data.get("operations")
    if not isinstance(operations_data, list) or not operations_data:
        raise ExecutionPlanError("operations must be a non-empty list")
    summary = data.get("summary", "")
    if not isinstance(summary, str):
        raise ExecutionPlanError("summary must be a string")
    operations = [_parse_operation(item) for item in operations_data]
    return ExecutionPlan(summary=summary, operations=operations)


def _parse_operation(data: object) -> ExecutionOperation:
    if not isinstance(data, dict):
        raise ExecutionPlanError("operation must be an object")
    action = data.get("action")
    path = data.get("path")
    content = data.get("content")
    if not isinstance(action, str):
        raise ExecutionPlanError("action must be a string")
    if action not in SUPPORTED_ACTIONS:
        raise ExecutionPlanError(f"unsupported action: {action}")
    if not isinstance(path, str):
        raise ExecutionPlanError("path must be a string")
    if not isinstance(content, str):
        raise ExecutionPlanError("content must be a string")
    return ExecutionOperation(action=action, path=path, content=content)
```

- [ ] **Step 5: Run plan parser tests**

Run:

```powershell
python -m pytest tests/test_execution_plan.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit execution plan parser**

Run:

```powershell
git add src/dev_agent/execution tests/test_execution_plan.py
git commit -m "feat: parse local execution plans"
```

Expected: commit succeeds.

---

### Task 2: Safe Text Plan Applier

**Files:**
- Create: `src/dev_agent/execution/applier.py`
- Test: `tests/test_execution_applier.py`

- [ ] **Step 1: Write failing applier tests**

Create `tests/test_execution_applier.py`:

```python
import pytest

from dev_agent.encoding import read_text_utf8, write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError


def test_applier_creates_overwrites_and_appends_utf8_text(tmp_path) -> None:
    write_text_utf8(tmp_path / "existing.md", "旧内容\n")
    plan = ExecutionPlan(
        summary="写入中文文本",
        operations=[
            ExecutionOperation("create_text", "docs/new.md", "# 新文件\n"),
            ExecutionOperation("overwrite_text", "existing.md", "新内容\n"),
            ExecutionOperation("append_text", "logs/run.md", "追加中文\n"),
        ],
    )

    result = ExecutionPlanApplier(tmp_path).apply(plan)

    assert result.applied is True
    assert [change.path for change in result.changes] == ["docs/new.md", "existing.md", "logs/run.md"]
    assert read_text_utf8(tmp_path / "docs" / "new.md") == "# 新文件\n"
    assert read_text_utf8(tmp_path / "existing.md") == "新内容\n"
    assert read_text_utf8(tmp_path / "logs" / "run.md") == "追加中文\n"


def test_applier_rejects_create_when_file_exists(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    plan = ExecutionPlan(
        summary="冲突",
        operations=[ExecutionOperation("create_text", "README.md", "# new\n")],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).apply(plan)

    assert read_text_utf8(tmp_path / "README.md") == "# existing\n"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        "../escape.md",
        ".git/config",
        ".worktrees/other/file.md",
        ".superpowers/cache.md",
    ],
)
def test_applier_rejects_unsafe_paths(tmp_path, unsafe_path: str) -> None:
    plan = ExecutionPlan(
        summary="拒绝危险路径",
        operations=[ExecutionOperation("overwrite_text", unsafe_path, "内容\n")],
    )

    with pytest.raises(ExecutionPlanError):
        ExecutionPlanApplier(tmp_path).apply(plan)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_execution_applier.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.execution.applier`.

- [ ] **Step 3: Implement safe applier**

Create `src/dev_agent/execution/applier.py`:

```python
from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8, write_text_utf8
from dev_agent.execution.models import ExecutionChange, ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.tools.git import GitReader


FORBIDDEN_ROOTS = {".git", ".worktrees", ".superpowers"}


class ExecutionPlanApplier:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def planned_changes(self, plan: ExecutionPlan) -> list[dict[str, object]]:
        return [operation.to_dict() for operation in plan.operations]

    def apply(self, plan: ExecutionPlan) -> ExecutionResult:
        changes: list[ExecutionChange] = []
        for operation in plan.operations:
            target = self._resolve_target(operation.path)
            before_exists = target.exists()
            if operation.action == "create_text":
                if before_exists:
                    raise ExecutionPlanError(f"path already exists: {operation.path}")
                write_text_utf8(target, operation.content)
            elif operation.action == "overwrite_text":
                write_text_utf8(target, operation.content)
            elif operation.action == "append_text":
                existing = read_text_utf8(target) if before_exists else ""
                write_text_utf8(target, existing + operation.content)
            else:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
            changes.append(
                ExecutionChange(
                    action=operation.action,
                    path=operation.path,
                    before_exists=before_exists,
                    after_exists=target.exists(),
                    bytes_written=len(operation.content.encode(UTF8)),
                )
            )
        diff_stat = GitReader(self.repo_root).snapshot().diff_stat
        return ExecutionResult(
            applied=True,
            planned_changes=self.planned_changes(plan),
            changes=changes,
            diff_stat=diff_stat,
        )

    def preview(self, plan: ExecutionPlan) -> ExecutionResult:
        return ExecutionResult(
            applied=False,
            planned_changes=self.planned_changes(plan),
        )

    def _resolve_target(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise ExecutionPlanError("path must not be empty")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ExecutionPlanError(f"path must be relative: {raw_path}")
        repo_root = self.repo_root.resolve()
        target = (repo_root / relative).resolve()
        try:
            target.relative_to(repo_root)
        except ValueError as exc:
            raise ExecutionPlanError(f"path escapes repository: {raw_path}") from exc
        relative_parts = target.relative_to(repo_root).parts
        if relative_parts and relative_parts[0] in FORBIDDEN_ROOTS:
            raise ExecutionPlanError(f"path is not allowed: {raw_path}")
        return target
```

- [ ] **Step 4: Run applier tests**

Run:

```powershell
python -m pytest tests/test_execution_applier.py -v
```

Expected: all applier tests pass.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit safe applier**

Run:

```powershell
git add src/dev_agent/execution/applier.py tests/test_execution_applier.py
git commit -m "feat: apply safe local text plans"
```

Expected: commit succeeds.

---

### Task 3: Runtime Execution Integration

**Files:**
- Modify: `src/dev_agent/runtime/models.py`
- Modify: `src/dev_agent/runtime/runner.py`
- Modify: `tests/test_runtime_runner.py`

- [ ] **Step 1: Add failing runtime apply tests**

Append to `tests/test_runtime_runner.py`:

```python
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.memory.store import MemoryStore


def test_local_task_runner_applies_execution_plan_and_records_diff(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    runner = LocalTaskRunner(
        repo_root=tmp_path,
        home_dir=tmp_path,
        provider=FakeProvider(name="fake-main", responses=["计划：创建说明文件。"]),
    )

    result = runner.run(
        "创建执行说明",
        TaskRunOptions(
            dry_run=True,
            run_verification=False,
            apply_changes=True,
            execution_plan=ExecutionPlan(
                summary="创建说明",
                operations=[ExecutionOperation("create_text", "docs/execution.md", "执行闭环\n")],
            ),
        ),
    )

    assert (tmp_path / "docs" / "execution.md").read_text(encoding="utf-8") == "执行闭环\n"
    assert result.applied_changes == [
        {
            "action": "create_text",
            "path": "docs/execution.md",
            "before_exists": False,
            "after_exists": True,
            "bytes_written": len("执行闭环\n".encode("utf-8")),
        }
    ]
    assert "execution_completed" in result.events
    history = MemoryStore(tmp_path).list_tasks()
    assert history[-1].status == "passed"
    assert "docs/execution.md" in history[-1].summary


def test_local_task_runner_records_execution_failure_without_writing_later_operations(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    runner = LocalTaskRunner(
        repo_root=tmp_path,
        home_dir=tmp_path,
        provider=FakeProvider(name="fake-main", responses=["计划：执行危险写入。"]),
    )

    result = runner.run(
        "执行失败计划",
        TaskRunOptions(
            dry_run=True,
            apply_changes=True,
            execution_plan=ExecutionPlan(
                summary="失败计划",
                operations=[
                    ExecutionOperation("create_text", "README.md", "# new\n"),
                    ExecutionOperation("create_text", "docs/after.md", "不应写入\n"),
                ],
            ),
        ),
    )

    assert result.execution_error is not None
    assert "already exists" in result.execution_error
    assert not (tmp_path / "docs" / "after.md").exists()
    history = MemoryStore(tmp_path).list_tasks()
    assert history[-1].status == "failed"
    assert "already exists" in history[-1].summary
```

- [ ] **Step 2: Run runtime tests to verify failure**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: FAIL because `TaskRunOptions` has no `apply_changes` and `TaskRunResult` has no execution fields.

- [ ] **Step 3: Extend runtime models**

Modify `src/dev_agent/runtime/models.py` imports:

```python
from dev_agent.execution.models import ExecutionPlan
```

Modify `TaskRunOptions` and `TaskRunResult`:

```python
@dataclass(frozen=True)
class TaskRunOptions:
    dry_run: bool = True
    run_verification: bool = False
    apply_changes: bool = False
    execution_plan: ExecutionPlan | None = None


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    plan_text: str
    dry_run: bool
    memory_hit_count: int
    verification_steps: list[list[str]]
    verification_result: VerificationResult | None = None
    events: list[str] = field(default_factory=list)
    planned_changes: list[dict[str, object]] = field(default_factory=list)
    applied_changes: list[dict[str, object]] = field(default_factory=list)
    diff_stat: str = ""
    execution_error: str | None = None
```

- [ ] **Step 4: Integrate execution in runner**

Modify `src/dev_agent/runtime/runner.py` imports:

```python
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.tools.git import GitReader
```

Replace `LocalTaskRunner.run()` with:

```python
    def run(self, user_request: str, options: TaskRunOptions) -> TaskRunResult:
        task = create_task(self.repo_root, user_request)
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "runtime_started")
        context = resolve_runtime_context(self.repo_root, self.home_dir, user_request)
        prompt = build_task_prompt(context)
        response = self.provider.complete(ModelRequest(prompt=prompt, task_id=task.task_id))
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "provider_completed")
        events = [*task.events]
        verification_result = None
        execution_result = self._execution_preview(options)
        execution_error = None

        if options.apply_changes:
            try:
                execution_result = self._apply_execution_plan(options)
                task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "execution_completed")
                events = [*task.events]
            except ExecutionPlanError as exc:
                execution_error = str(exc)
                task = update_task_status(self.repo_root, task.task_id, TaskStatus.FAILED, "execution_failed")
                self._record_history(
                    task_id=task.task_id,
                    title=user_request,
                    status=task.status.value,
                    summary=f"{response.text}\n\n执行失败：{execution_error}",
                    events=task.events,
                    verification=[" ".join(step.command) for step in context.verification_plan.steps],
                )
                return TaskRunResult(
                    task_id=task.task_id,
                    plan_text=response.text,
                    dry_run=options.dry_run,
                    memory_hit_count=len(context.memory_hits),
                    verification_steps=[step.command for step in context.verification_plan.steps],
                    events=task.events,
                    planned_changes=execution_result.planned_changes,
                    applied_changes=execution_result.changes_as_dicts(),
                    diff_stat=execution_result.diff_stat,
                    execution_error=execution_error,
                )

        if options.run_verification:
            verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
            task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "verification_completed")
            events = [*task.events]
        final_status = TaskStatus.PASSED if verification_result is None or verification_result.passed else TaskStatus.FAILED
        task = update_task_status(self.repo_root, task.task_id, final_status, "runtime_completed")
        summary = self._build_summary(response.text, execution_result)
        self._record_history(
            task_id=task.task_id,
            title=user_request,
            status=task.status.value,
            summary=summary,
            events=task.events,
            verification=[" ".join(step.command) for step in context.verification_plan.steps],
        )
        return TaskRunResult(
            task_id=task.task_id,
            plan_text=response.text,
            dry_run=options.dry_run,
            memory_hit_count=len(context.memory_hits),
            verification_steps=[step.command for step in context.verification_plan.steps],
            verification_result=verification_result,
            events=task.events,
            planned_changes=execution_result.planned_changes,
            applied_changes=execution_result.changes_as_dicts(),
            diff_stat=execution_result.diff_stat,
            execution_error=execution_error,
        )
```

Add helper methods inside `LocalTaskRunner`:

```python
    def _execution_preview(self, options: TaskRunOptions) -> ExecutionResult:
        if options.execution_plan is None:
            return ExecutionResult(applied=False, planned_changes=[])
        return ExecutionPlanApplier(self.repo_root).preview(options.execution_plan)

    def _apply_execution_plan(self, options: TaskRunOptions) -> ExecutionResult:
        if options.execution_plan is None:
            raise ExecutionPlanError("execution_plan is required when apply_changes is true")
        return ExecutionPlanApplier(self.repo_root).apply(options.execution_plan)

    def _build_summary(self, plan_text: str, execution_result: ExecutionResult) -> str:
        if not execution_result.applied:
            return plan_text
        changed_paths = ", ".join(change.path for change in execution_result.changes)
        diff_stat = execution_result.diff_stat or GitReader(self.repo_root).snapshot().diff_stat
        return f"{plan_text}\n\n已应用文件：{changed_paths}\n\nDiff stat:\n{diff_stat}"

    def _record_history(
        self,
        task_id: str,
        title: str,
        status: str,
        summary: str,
        events: list[str],
        verification: list[str],
    ) -> None:
        store = MemoryStore(self.repo_root)
        record = TaskRecord(
            task_id=task_id,
            title=title,
            status=status,
            summary=summary,
            events=events,
            verification=verification,
            lessons=[summary],
        )
        store.append_task(record)
        for experience in extract_experiences(record):
            store.append_experience(experience)
```

- [ ] **Step 5: Run runtime tests**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: all runtime runner tests pass.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit runtime integration**

Run:

```powershell
git add src/dev_agent/runtime tests/test_runtime_runner.py
git commit -m "feat: run local execution plans"
```

Expected: commit succeeds.

---

### Task 4: CLI Plan File Apply

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_run_applies_plan_file_and_reports_changes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "创建说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/execution.md",
                        "content": "执行闭环\n",
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
        "创建说明",
        "--fake-response",
        "计划：创建说明文件。",
        "--plan-file",
        str(plan_file),
        "--apply",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_error"] is None
    assert payload["applied_changes"][0]["path"] == "docs/execution.md"
    assert (tmp_path / "docs" / "execution.md").read_text(encoding="utf-8") == "执行闭环\n"


def test_run_previews_plan_file_without_apply(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "只预览\n",
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
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned_changes"][0]["path"] == "docs/preview.md"
    assert payload["applied_changes"] == []
    assert not (tmp_path / "docs" / "preview.md").exists()


def test_run_apply_requires_plan_file(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "缺少计划",
        "--fake-response",
        "计划：失败。",
        "--apply",
    )

    assert result.returncode == 2
    assert "--plan-file is required when --apply is used" in result.stderr
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `run` does not accept `--plan-file` or `--apply`.

- [ ] **Step 3: Implement CLI plan-file parsing**

Modify `src/dev_agent/cli.py` imports:

```python
from dev_agent.encoding import UTF8, read_text_utf8, utf8_environment_hint, write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan
```

Add helper function above `run_command`:

```python
def _load_execution_plan(path: str | None):
    if path is None:
        return None
    try:
        return parse_execution_plan(json.loads(read_text_utf8(Path(path))))
    except (json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ValueError(f"无法读取执行计划：{exc}") from exc
```

Replace `run_command` with:

```python
def run_command(args: Namespace) -> int:
    if args.apply and args.plan_file is None:
        sys.stderr.write("--plan-file is required when --apply is used\n")
        return 2
    try:
        execution_plan = _load_execution_plan(args.plan_file)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    runner = LocalTaskRunner(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        provider=FakeProvider(name="fake-main", responses=[args.fake_response]),
    )
    result = runner.run(
        args.request,
        TaskRunOptions(
            dry_run=args.dry_run,
            run_verification=args.verify,
            apply_changes=args.apply,
            execution_plan=execution_plan,
        ),
    )
    payload = {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "verification_passed": None if result.verification_result is None else result.verification_result.passed,
        "events": result.events,
        "planned_changes": result.planned_changes,
        "applied_changes": result.applied_changes,
        "diff_stat": result.diff_stat,
        "execution_error": result.execution_error,
    }
    sys.stdout.write(_json(payload))
    return 1 if result.execution_error else 0
```

Register parser arguments:

```python
    run_parser.add_argument("--plan-file")
    run_parser.add_argument("--apply", action="store_true")
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit CLI plan-file apply**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: add CLI execution plan apply"
```

Expected: commit succeeds.

---

### Task 5: Web Dry-Run Safety and Final Verification

**Files:**
- Modify: `tests/test_web_api.py`
- Modify: `src/dev_agent/web/api.py`
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Add failing Web safety regression test**

Append to `tests/test_web_api.py`:

```python
def test_web_dry_run_does_not_apply_execution_plan_payload(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = run_dry_run_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="尝试通过 Web 写文件",
        fake_response="计划：Web 只允许 dry-run。",
        execution_plan_payload={
            "summary": "不应执行",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/from-web.md",
                    "content": "不应写入\n",
                }
            ],
        },
    )

    assert payload["dry_run"] is True
    assert payload["applied_changes"] == []
    assert not (tmp_path / "docs" / "from-web.md").exists()
```

- [ ] **Step 2: Run Web API tests to verify failure**

Run:

```powershell
python -m pytest tests/test_web_api.py -v
```

Expected: FAIL because `run_dry_run_task` does not accept `execution_plan_payload`.

- [ ] **Step 3: Add explicit ignored Web execution payload parameter**

Modify `src/dev_agent/web/api.py` function signature and runner call:

```python
def run_dry_run_task(
    repo_root: Path,
    home_dir: Path,
    request_text: str,
    fake_response: str,
    execution_plan_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for Web dry-run")
    runner = LocalTaskRunner(
        repo_root=repo_root,
        home_dir=home_dir,
        provider=FakeProvider(name="fake-web", responses=[fake_response]),
    )
    result = runner.run(
        request_text,
        TaskRunOptions(dry_run=True, run_verification=False, apply_changes=False),
    )
    return {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "events": result.events,
        "planned_changes": [],
        "applied_changes": [],
        "diff_stat": "",
        "execution_error": None,
    }
```

- [ ] **Step 4: Run Web API tests**

Run:

```powershell
python -m pytest tests/test_web_api.py -v
```

Expected: all Web API tests pass.

- [ ] **Step 5: Run Web API tests**

Run:

```powershell
python -m pytest tests/test_web_api.py -v
```

Expected: all Web API tests pass.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit Web safety regression**

Run:

```powershell
git add src/dev_agent/web/api.py tests/test_web_api.py
git commit -m "test: keep web run dry-run only"
```

Expected: commit succeeds.

- [ ] **Step 8: Run final verification**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
$env:PYTHONPATH=(Resolve-Path 'src').Path
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli serve --port 0 --check
```

Expected: tests pass; `doctor` still reports Web/runtime capabilities; `serve --check` prints a local URL.

- [ ] **Step 9: Run execution smoke in a temporary repository**

Run:

```powershell
$smoke = Join-Path $env:TEMP ('dev-agent-execution-smoke-' + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $smoke | Out-Null
Set-Content -LiteralPath (Join-Path $smoke 'pyproject.toml') -Value "[project]`nname = `"sample`"`n" -Encoding UTF8
$planPath = Join-Path $smoke 'plan.json'
$planJson = @{
  summary = '创建执行闭环 smoke 文件'
  operations = @(
    @{
      action = 'create_text'
      path = 'docs/execution-smoke.md'
      content = "执行闭环 smoke`n"
    }
  )
} | ConvertTo-Json -Depth 5
Set-Content -LiteralPath $planPath -Value $planJson -Encoding UTF8
Push-Location $smoke
python -m dev_agent.cli run "验证执行闭环" --fake-response "计划：应用结构化文件操作。" --plan-file $planPath --apply
Pop-Location
```

Expected: command exits 0 and JSON output includes `applied_changes` for `docs/execution-smoke.md`.

- [ ] **Step 10: Check repository status and recent commits**

Run:

```powershell
git status --short
git log --oneline --decorate -6
```

Expected: worktree is clean after commits; recent commits include parser, applier, runtime integration, CLI apply, and Web safety regression.

---

## Self-Review

**Spec coverage:** Tasks cover structure parsing, safety boundaries, UTF-8 text operations, runtime apply path, CLI plan-file flow, Web dry-run boundary, history recording, diff stat, and final verification.

**Scope control:** No task introduces real provider calls, Git writes, Web write access, deletion/move operations, concurrent execution, or transaction rollback.

**Unfinished marker scan:** The plan contains concrete files, tests, commands, snippets, expected failures, expected passes, and commit commands.

**Type consistency:** `ExecutionOperation`, `ExecutionPlan`, `ExecutionChange`, `ExecutionResult`, `ExecutionPlanError`, `ExecutionPlanApplier`, `TaskRunOptions.apply_changes`, and `TaskRunResult.applied_changes` are defined before later tasks use them.
