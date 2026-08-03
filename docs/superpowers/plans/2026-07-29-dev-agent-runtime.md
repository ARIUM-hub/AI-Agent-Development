# 本地任务运行时 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个本地 dry-run 任务运行时，把上下文解析、历史召回、fake provider 计划生成、验证计划和任务历史写回串成可测试闭环。

**Architecture:** 本阶段新增 `runtime` 包，不做真实代码修改、不调用真实云端模型、不自动 Git push。运行时先解析仓库上下文，再用 fake provider 生成计划文本，最后写入任务状态和历史记录；验证命令默认只规划，只有显式 `--verify` 才执行。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、argparse、pytest、Windows PowerShell、UTF-8 文本读写。

---

## Scope Check

本计划覆盖设计中的“自然语言 CLI 任务入口”“扫描仓库、Git 状态、项目规则和历史召回”“生成任务上下文包”“生成可读执行计划”“强验证规划”“写回任务历史”的本地 dry-run 纵切片。

本计划不实现自动代码修改、真实云端模型 provider、Web 控制台、Git commit/push 自动化、审批流 UI，也不默认执行验证命令。

本计划完成后应满足：

- 可以解析一次任务所需的上下文包。
- 可以把用户请求、规则、扫描结果、Git 快照、历史命中和验证计划组织成 provider prompt。
- 可以用 fake provider 生成计划结果，并受预算熔断保护。
- 可以通过 `dev-agent run "任务" --fake-response "计划..." --dry-run` 执行本地 dry-run。
- 可以在 dry-run 后写入 `.agent/tasks/*.json` 和 `.agent/history/tasks.jsonl`。
- 可以在显式 `--verify` 时执行验证计划并返回结构化结果。

## File Structure

- Create: `src/dev_agent/runtime/__init__.py`，运行时包说明。
- Create: `src/dev_agent/runtime/models.py`，定义 `RuntimeContext`、`TaskRunOptions`、`TaskRunResult`。
- Create: `src/dev_agent/runtime/context.py`，解析仓库上下文、Git 快照、历史命中和验证计划。
- Create: `src/dev_agent/runtime/prompts.py`，构建 provider prompt。
- Create: `src/dev_agent/runtime/runner.py`，执行本地任务 dry-run、可选验证和历史写回。
- Modify: `src/dev_agent/cli.py`，新增 `run` 子命令。
- Create: `tests/test_runtime_context.py`，覆盖上下文解析。
- Create: `tests/test_runtime_runner.py`，覆盖 fake provider dry-run 与可选验证。
- Modify: `tests/test_cli.py`，覆盖 CLI `run`。

---

### Task 1: Runtime Context Resolver

**Files:**
- Create: `src/dev_agent/runtime/__init__.py`
- Create: `src/dev_agent/runtime/models.py`
- Create: `src/dev_agent/runtime/context.py`
- Test: `tests/test_runtime_context.py`

- [ ] **Step 1: Write failing context resolver tests**

Create `tests/test_runtime_context.py`:

```python
import subprocess

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.runtime.context import resolve_runtime_context


def git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_resolve_runtime_context_combines_project_git_memory_and_verification(tmp_path) -> None:
    write_text_utf8(tmp_path / ".agent" / "project.yaml", "name: 示例项目\ntech_stack:\n  - python\n")
    write_text_utf8(tmp_path / ".agent" / "rules.md", "所有文件使用 UTF-8。\n")
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    write_text_utf8(tmp_path / "README.md", "# 示例\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "initial")
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-1",
            title="修复中文乱码",
            status="passed",
            summary="Windows UTF-8 修复",
            lessons=["子进程需要 PYTHONUTF8。"],
        )
    )

    context = resolve_runtime_context(tmp_path, tmp_path, "处理 UTF-8 编码问题")

    assert context.user_request == "处理 UTF-8 编码问题"
    assert context.project.name == "示例项目"
    assert context.scan.languages == ["python"]
    assert "initial" in context.git.recent_log
    assert context.memory_hits[0].record_id == "task-1"
    assert context.verification_plan.steps[0].command == ["python", "-m", "pytest"]
    assert "所有文件使用 UTF-8" in context.rules_text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_runtime_context.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.runtime`.

- [ ] **Step 3: Implement runtime models**

Create `src/dev_agent/runtime/__init__.py`:

```python
"""Local task runtime orchestration."""
```

Create `src/dev_agent/runtime/models.py`:

```python
from dataclasses import dataclass, field

from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.tools.git import GitSnapshot
from dev_agent.verification.planner import VerificationPlan
from dev_agent.verification.runner import VerificationResult


@dataclass(frozen=True)
class RuntimeContext:
    user_request: str
    project: ProjectConfig
    preferences: UserPreferences
    rules_text: str
    scan: ProjectScan
    git: GitSnapshot
    memory_hits: list[MemoryHit]
    verification_plan: VerificationPlan


@dataclass(frozen=True)
class TaskRunOptions:
    dry_run: bool = True
    run_verification: bool = False


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    plan_text: str
    dry_run: bool
    memory_hit_count: int
    verification_steps: list[list[str]]
    verification_result: VerificationResult | None = None
    events: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Implement context resolver**

Create `src/dev_agent/runtime/context.py`:

```python
from pathlib import Path

from dev_agent.config.loader import load_agent_context
from dev_agent.memory.retriever import MemoryRetriever
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.runtime.models import RuntimeContext
from dev_agent.tools.git import GitReader
from dev_agent.verification.planner import build_verification_plan


def resolve_runtime_context(repo_root: Path, home_dir: Path, user_request: str) -> RuntimeContext:
    agent_context = load_agent_context(repo_root, home_dir)
    scan = scan_project(repo_root)
    git = GitReader(repo_root).snapshot()
    memory_store = MemoryStore(repo_root)
    memory_hits = MemoryRetriever(
        memory_store.list_tasks(),
        memory_store.list_experiences(),
    ).search(user_request)
    verification_plan = build_verification_plan(agent_context.commands, scan)
    return RuntimeContext(
        user_request=user_request,
        project=agent_context.project,
        preferences=agent_context.preferences,
        rules_text=agent_context.rules_text,
        scan=scan,
        git=git,
        memory_hits=memory_hits,
        verification_plan=verification_plan,
    )
```

- [ ] **Step 5: Run context tests**

Run:

```powershell
python -m pytest tests/test_runtime_context.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit context resolver**

Run:

```powershell
git add src/dev_agent/runtime tests/test_runtime_context.py
git commit -m "feat: resolve runtime task context"
```

Expected: commit succeeds.

---

### Task 2: Provider Prompt Builder

**Files:**
- Create: `src/dev_agent/runtime/prompts.py`
- Test: `tests/test_runtime_runner.py`

- [ ] **Step 1: Write failing prompt builder tests**

Create `tests/test_runtime_runner.py`:

```python
from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.runtime.models import RuntimeContext
from dev_agent.runtime.prompts import build_task_prompt
from dev_agent.tools.git import GitSnapshot
from dev_agent.verification.planner import VerificationPlan, VerificationStep


def test_build_task_prompt_includes_request_context_memory_and_verification(tmp_path) -> None:
    context = RuntimeContext(
        user_request="实现 history 查询",
        project=ProjectConfig(name="研发助手", tech_stack=["python"]),
        preferences=UserPreferences(language="zh-CN"),
        rules_text="所有文本使用 UTF-8。",
        scan=ProjectScan(root=tmp_path, languages=["python"], markers=["pyproject.toml"]),
        git=GitSnapshot(status=" M src/dev_agent/cli.py\n", diff_stat="", recent_log="abc123 initial\n"),
        memory_hits=[MemoryHit(record_id="task-1", kind="task", text="提交前运行完整测试", score=2.0)],
        verification_plan=VerificationPlan(steps=[VerificationStep(name="test", command=["python", "-m", "pytest"])]),
    )

    prompt = build_task_prompt(context)

    assert "用户请求：实现 history 查询" in prompt
    assert "项目：研发助手" in prompt
    assert "所有文本使用 UTF-8" in prompt
    assert "提交前运行完整测试" in prompt
    assert "python -m pytest" in prompt
    assert "M src/dev_agent/cli.py" in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.runtime.prompts`.

- [ ] **Step 3: Implement prompt builder**

Create `src/dev_agent/runtime/prompts.py`:

```python
from dev_agent.runtime.models import RuntimeContext


def build_task_prompt(context: RuntimeContext) -> str:
    memory_lines = [
        f"- [{hit.kind}:{hit.record_id}] {hit.text}"
        for hit in context.memory_hits
    ] or ["- 无相关历史经验"]
    verification_lines = [
        f"- {step.name}: {' '.join(step.command)}"
        for step in context.verification_plan.steps
    ] or ["- 无可推断验证命令"]
    return "\n".join(
        [
            f"用户请求：{context.user_request}",
            f"项目：{context.project.name}",
            f"技术栈：{', '.join(context.project.tech_stack or context.scan.languages)}",
            f"语言偏好：{context.preferences.language}",
            "项目规则：",
            context.rules_text or "无项目规则",
            "扫描结果：",
            f"- languages: {', '.join(context.scan.languages)}",
            f"- markers: {', '.join(context.scan.markers)}",
            "Git 状态：",
            context.git.status or "工作区干净",
            "近期 Git 记录：",
            context.git.recent_log or "无 Git 记录",
            "相关历史：",
            *memory_lines,
            "建议验证：",
            *verification_lines,
            "请给出简洁、可执行、以验证为中心的研发计划。",
        ]
    )
```

- [ ] **Step 4: Run prompt tests**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit prompt builder**

Run:

```powershell
git add src/dev_agent/runtime/prompts.py tests/test_runtime_runner.py
git commit -m "feat: build runtime task prompts"
```

Expected: commit succeeds.

---

### Task 3: Local Task Runner

**Files:**
- Create: `src/dev_agent/runtime/runner.py`
- Modify: `tests/test_runtime_runner.py`

- [ ] **Step 1: Add failing task runner tests**

Append to `tests/test_runtime_runner.py`:

```python
from dev_agent.encoding import write_text_utf8
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.runner import LocalTaskRunner


def test_local_task_runner_generates_plan_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    runner = LocalTaskRunner(
        repo_root=tmp_path,
        home_dir=tmp_path,
        provider=FakeProvider(name="fake-main", responses=["计划：读取文件并运行测试。"]),
    )

    result = runner.run("实现 history 查询", TaskRunOptions(dry_run=True))

    assert result.plan_text == "计划：读取文件并运行测试。"
    assert result.dry_run is True
    assert result.verification_steps == [["python", "-m", "pytest"]]
    assert "provider_completed" in result.events
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "实现 history 查询" in history
    assert "计划：读取文件并运行测试。" in history


def test_local_task_runner_can_execute_verification_when_requested(tmp_path) -> None:
    write_text_utf8(tmp_path / ".agent" / "commands.yaml", "test: python -c \"print('ok')\"\n")
    runner = LocalTaskRunner(
        repo_root=tmp_path,
        home_dir=tmp_path,
        provider=FakeProvider(name="fake-main", responses=["计划：运行验证。"]),
    )

    result = runner.run("运行验证", TaskRunOptions(dry_run=True, run_verification=True))

    assert result.verification_result is not None
    assert result.verification_result.passed is True
    assert result.verification_result.results[0].stdout.strip() == "ok"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.runtime.runner`.

- [ ] **Step 3: Implement local task runner**

Create `src/dev_agent/runtime/runner.py`:

```python
from pathlib import Path

from dev_agent.memory.extract import extract_experiences
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.providers.base import ModelProvider
from dev_agent.providers.budget import BudgetConfig, CircuitBreaker, ProtectedProvider
from dev_agent.providers.models import ModelRequest
from dev_agent.runtime.context import resolve_runtime_context
from dev_agent.runtime.models import TaskRunOptions, TaskRunResult
from dev_agent.runtime.prompts import build_task_prompt
from dev_agent.tasks.state import TaskStatus, create_task, update_task_status
from dev_agent.verification.runner import VerificationRunner


class LocalTaskRunner:
    def __init__(self, repo_root: Path, home_dir: Path, provider: ModelProvider) -> None:
        self.repo_root = repo_root
        self.home_dir = home_dir
        self.provider = ProtectedProvider(provider, CircuitBreaker(BudgetConfig()))

    def run(self, user_request: str, options: TaskRunOptions) -> TaskRunResult:
        task = create_task(self.repo_root, user_request)
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "runtime_started")
        context = resolve_runtime_context(self.repo_root, self.home_dir, user_request)
        prompt = build_task_prompt(context)
        response = self.provider.complete(ModelRequest(prompt=prompt, task_id=task.task_id))
        events = [*task.events, "provider_completed"]
        verification_result = None
        if options.run_verification:
            verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
            events.append("verification_completed")
        final_status = TaskStatus.PASSED if verification_result is None or verification_result.passed else TaskStatus.FAILED
        task = update_task_status(self.repo_root, task.task_id, final_status, events[-1])

        store = MemoryStore(self.repo_root)
        record = TaskRecord(
            task_id=task.task_id,
            title=user_request,
            status=task.status.value,
            summary=response.text,
            events=task.events,
            verification=[" ".join(step.command) for step in context.verification_plan.steps],
            lessons=[response.text],
        )
        store.append_task(record)
        for experience in extract_experiences(record):
            store.append_experience(experience)

        return TaskRunResult(
            task_id=task.task_id,
            plan_text=response.text,
            dry_run=options.dry_run,
            memory_hit_count=len(context.memory_hits),
            verification_steps=[step.command for step in context.verification_plan.steps],
            verification_result=verification_result,
            events=task.events,
        )
```

- [ ] **Step 4: Run runtime runner tests**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit local task runner**

Run:

```powershell
git add src/dev_agent/runtime/runner.py tests/test_runtime_runner.py
git commit -m "feat: add local dry-run task runner"
```

Expected: commit succeeds.

---

### Task 4: CLI Run Command

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI run tests**

Append to `tests/test_cli.py`:

```python
def test_run_uses_fake_response_and_records_history(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")

    result = run_cli(
        tmp_path,
        "run",
        "实现 history 查询",
        "--fake-response",
        "计划：读取文件并运行测试。",
        "--dry-run",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plan_text"] == "计划：读取文件并运行测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "实现 history 查询" in history
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `run` command is not registered.

- [ ] **Step 3: Implement CLI run command**

Modify imports in `src/dev_agent/cli.py`:

```python
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.runner import LocalTaskRunner
```

Add command function:

```python
def run_command(args: Namespace) -> int:
    runner = LocalTaskRunner(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        provider=FakeProvider(name="fake-main", responses=[args.fake_response]),
    )
    result = runner.run(
        args.request,
        TaskRunOptions(dry_run=args.dry_run, run_verification=args.verify),
    )
    payload = {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "verification_passed": None if result.verification_result is None else result.verification_result.passed,
        "events": result.events,
    }
    sys.stdout.write(_json(payload))
    return 0
```

Register parser:

```python
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("request")
    run_parser.add_argument("--fake-response", required=True)
    run_parser.add_argument("--dry-run", action="store_true", default=True)
    run_parser.add_argument("--verify", action="store_true")
    run_parser.set_defaults(handler=run_command)
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

- [ ] **Step 6: Commit CLI run command**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: add local run CLI command"
```

Expected: commit succeeds.

---

### Task 5: Runtime Doctor Capability and Final Verification

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Add failing doctor capability assertion**

Modify `test_doctor_outputs_json` in `tests/test_cli.py` so `payload["capabilities"]` includes:

```python
        "runtime_context": True,
        "local_task_runner": True,
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because doctor does not report runtime capabilities.

- [ ] **Step 3: Update doctor capabilities**

Modify `doctor_command` in `src/dev_agent/cli.py` by adding:

```python
            "runtime_context": True,
            "local_task_runner": True,
```

- [ ] **Step 4: Run full verification**

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
python -m dev_agent.cli history
python -m dev_agent.cli run "验证本地运行时" --fake-response "计划：检查上下文并运行测试。" --dry-run
git status --short
```

Expected: all tests pass; `doctor` contains runtime capabilities; `run` outputs JSON with `plan_text` and writes history; Git status has only expected tracked changes before commit.

- [ ] **Step 5: Commit runtime doctor update**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: report runtime capabilities in doctor"
```

Expected: commit succeeds.

---

## Self-Review

**Spec coverage:** This plan implements a local slice of the approved orchestration flow: task input, context resolution, rules and preferences loading, project scan, Git read-only status, memory retrieval, provider plan generation, verification planning, optional verification execution, task state updates, and history writeback.

**Out of scope:** Real model APIs, automatic file edits, Web console, approval UI, Git commit/push automation, and destructive operations remain intentionally out of this plan.

**Placeholder scan:** The plan contains exact files, code snippets, verification commands, and commit commands. It avoids placeholder markers and open-ended implementation instructions.

**Type consistency:** `RuntimeContext`, `TaskRunOptions`, `TaskRunResult`, `LocalTaskRunner`, `build_task_prompt`, and `resolve_runtime_context` are introduced before use and match all later imports.
