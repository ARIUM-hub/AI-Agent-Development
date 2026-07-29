# 模型 Provider 与工具执行器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在基础骨架上实现可测试的模型 provider 抽象、请求预算与熔断保护、命令执行器、Git 只读能力和验证命令执行器。

**Architecture:** 本阶段只做本地可验证的执行底座，不调用真实云端模型，也不做写入型 Git 操作。Provider 层通过 fake provider 和预算控制器验证接口边界；工具执行器统一记录命令、退出码、标准输出、标准错误和耗时；验证执行器复用项目规则与扫描结果生成测试/lint/typecheck/build 计划。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、subprocess、time、pytest、Windows PowerShell。

---

## Scope Check

完整设计还包含真实云端模型接入、自动代码修改、Git commit/push、任务历史检索、向量检索和本地 Web 控制台。本计划只实现下一条可独立验证的基础纵切片：provider 接口、预算熔断、命令执行、Git 只读、验证计划与执行。

本计划完成后应满足：

- 可以用 fake provider 调用统一 provider 接口。
- 可以限制单任务请求数、重试次数和预算，并在超限时给出中文风险提示。
- 可以执行本地命令并记录结构化结果。
- 可以读取 Git `status`、`diff --stat`、`log --oneline`。
- 可以从项目规则或扫描结果生成验证命令。
- 可以通过 CLI `doctor` 展示 provider/tooling 能力摘要。

## File Structure

- Create: `src/dev_agent/providers/models.py`，定义 provider 请求、响应、使用量和错误类型。
- Create: `src/dev_agent/providers/base.py`，定义 provider 协议和 fake provider。
- Create: `src/dev_agent/providers/budget.py`，实现请求预算、冷却和熔断状态。
- Create: `src/dev_agent/tools/executor.py`，执行命令并返回结构化结果。
- Create: `src/dev_agent/tools/git.py`，实现 Git 只读状态读取。
- Create: `src/dev_agent/verification/planner.py`，根据配置和扫描结果生成验证命令。
- Create: `src/dev_agent/verification/runner.py`，执行验证命令并聚合结果。
- Modify: `src/dev_agent/cli.py`，让 `doctor` 输出 provider/tooling 基础能力摘要。
- Create: `tests/test_provider_budget.py`，覆盖 provider 和预算保护。
- Create: `tests/test_tool_executor.py`，覆盖命令执行器。
- Create: `tests/test_git_reader.py`，覆盖 Git 只读读取。
- Create: `tests/test_verification.py`，覆盖验证计划和执行聚合。
- Modify: `tests/test_cli.py`，覆盖增强后的 `doctor` 输出。

---

### Task 1: Provider Models and Fake Provider

**Files:**
- Create: `src/dev_agent/providers/__init__.py`
- Create: `src/dev_agent/providers/models.py`
- Create: `src/dev_agent/providers/base.py`
- Test: `tests/test_provider_budget.py`

- [ ] **Step 1: Write failing provider interface tests**

Write `tests/test_provider_budget.py`:

```python
import pytest

from dev_agent.providers.base import FakeProvider
from dev_agent.providers.models import ModelRequest, ProviderError


def test_fake_provider_returns_configured_response() -> None:
    provider = FakeProvider(name="fake-main", responses=["计划：读取文件并运行测试。"])

    response = provider.complete(ModelRequest(prompt="帮我实现登录接口"))

    assert response.provider == "fake-main"
    assert response.text == "计划：读取文件并运行测试。"
    assert response.usage.request_count == 1
    assert response.usage.output_chars == len("计划：读取文件并运行测试。")


def test_fake_provider_raises_when_no_response_left() -> None:
    provider = FakeProvider(name="fake-main", responses=[])

    with pytest.raises(ProviderError, match="没有可用的 fake provider 响应"):
        provider.complete(ModelRequest(prompt="继续"))
```

- [ ] **Step 2: Run provider tests to verify failure**

Run:

```powershell
python -m pytest tests/test_provider_budget.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.providers`.

- [ ] **Step 3: Implement provider models**

Write `src/dev_agent/providers/__init__.py`:

```python
"""Model provider interfaces and safety controls."""
```

Write `src/dev_agent/providers/models.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    task_id: str | None = None


@dataclass(frozen=True)
class ProviderUsage:
    request_count: int
    input_chars: int
    output_chars: int


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    text: str
    usage: ProviderUsage


class ProviderError(RuntimeError):
    """Raised when a model provider cannot produce a response."""
```

- [ ] **Step 4: Implement provider protocol and fake provider**

Write `src/dev_agent/providers/base.py`:

```python
from typing import Protocol

from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderError, ProviderUsage


class ModelProvider(Protocol):
    name: str

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class FakeProvider:
    def __init__(self, name: str, responses: list[str]) -> None:
        self.name = name
        self._responses = list(responses)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not self._responses:
            raise ProviderError("没有可用的 fake provider 响应")
        text = self._responses.pop(0)
        return ModelResponse(
            provider=self.name,
            text=text,
            usage=ProviderUsage(
                request_count=1,
                input_chars=len(request.prompt),
                output_chars=len(text),
            ),
        )
```

- [ ] **Step 5: Run provider interface tests**

Run:

```powershell
python -m pytest tests/test_provider_budget.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit provider interface**

Run:

```powershell
git add src/dev_agent/providers tests/test_provider_budget.py
git commit -m "feat: add model provider interface"
```

Expected: commit succeeds.

---

### Task 2: Request Budget and Circuit Breaker

**Files:**
- Modify: `src/dev_agent/providers/budget.py`
- Modify: `tests/test_provider_budget.py`

- [ ] **Step 1: Extend failing tests for budget and breaker**

Append to `tests/test_provider_budget.py`:

```python
from dev_agent.providers.budget import BudgetConfig, BudgetExceeded, CircuitBreaker, ProtectedProvider


def test_protected_provider_blocks_when_request_limit_is_exceeded() -> None:
    provider = FakeProvider(name="fake-main", responses=["第一次", "第二次"])
    breaker = CircuitBreaker(BudgetConfig(max_requests=1, max_output_chars=100))
    protected = ProtectedProvider(provider, breaker)

    first = protected.complete(ModelRequest(prompt="第一次请求"))

    assert first.text == "第一次"
    with pytest.raises(BudgetExceeded, match="模型请求已停止"):
        protected.complete(ModelRequest(prompt="第二次请求"))


def test_protected_provider_blocks_when_output_budget_is_exceeded() -> None:
    provider = FakeProvider(name="fake-main", responses=["这段输出会超过预算"])
    breaker = CircuitBreaker(BudgetConfig(max_requests=3, max_output_chars=3))
    protected = ProtectedProvider(provider, breaker)

    with pytest.raises(BudgetExceeded, match="输出预算"):
        protected.complete(ModelRequest(prompt="生成方案"))


def test_circuit_breaker_opens_after_failures() -> None:
    provider = FakeProvider(name="fake-main", responses=[])
    breaker = CircuitBreaker(BudgetConfig(max_requests=3, max_failures=1))
    protected = ProtectedProvider(provider, breaker)

    with pytest.raises(ProviderError):
        protected.complete(ModelRequest(prompt="会失败"))

    with pytest.raises(BudgetExceeded, match="供应商已进入冷却"):
        protected.complete(ModelRequest(prompt="不要继续请求"))
```

- [ ] **Step 2: Run budget tests to verify failure**

Run:

```powershell
python -m pytest tests/test_provider_budget.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.providers.budget`.

- [ ] **Step 3: Implement budget and breaker**

Write `src/dev_agent/providers/budget.py`:

```python
from dataclasses import dataclass

from dev_agent.providers.base import ModelProvider
from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderError


@dataclass(frozen=True)
class BudgetConfig:
    max_requests: int = 8
    max_output_chars: int = 12000
    max_failures: int = 2


class BudgetExceeded(RuntimeError):
    """Raised when model safety controls stop further provider calls."""


@dataclass
class BudgetState:
    requests: int = 0
    output_chars: int = 0
    failures: int = 0
    open: bool = False


class CircuitBreaker:
    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self.state = BudgetState()

    def before_request(self) -> None:
        if self.state.open:
            raise BudgetExceeded("模型请求已停止：供应商已进入冷却。")
        if self.state.requests >= self.config.max_requests:
            raise BudgetExceeded("模型请求已停止：单任务请求次数超过预算。")

    def after_success(self, response: ModelResponse) -> None:
        self.state.requests += response.usage.request_count
        self.state.output_chars += response.usage.output_chars
        if self.state.output_chars > self.config.max_output_chars:
            self.state.open = True
            raise BudgetExceeded("模型请求已停止：输出预算已超过限制。")

    def after_failure(self) -> None:
        self.state.failures += 1
        if self.state.failures >= self.config.max_failures:
            self.state.open = True


class ProtectedProvider:
    def __init__(self, provider: ModelProvider, breaker: CircuitBreaker) -> None:
        self.provider = provider
        self.breaker = breaker
        self.name = provider.name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.breaker.before_request()
        try:
            response = self.provider.complete(request)
        except ProviderError:
            self.breaker.after_failure()
            raise
        self.breaker.after_success(response)
        return response
```

- [ ] **Step 4: Run budget tests**

Run:

```powershell
python -m pytest tests/test_provider_budget.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit budget controls**

Run:

```powershell
git add src/dev_agent/providers/budget.py tests/test_provider_budget.py
git commit -m "feat: add provider budget controls"
```

Expected: commit succeeds.

---

### Task 3: Command Executor

**Files:**
- Create: `src/dev_agent/tools/__init__.py`
- Create: `src/dev_agent/tools/executor.py`
- Test: `tests/test_tool_executor.py`

- [ ] **Step 1: Write failing command executor tests**

Write `tests/test_tool_executor.py`:

```python
import sys

from dev_agent.tools.executor import CommandExecutor


def test_command_executor_captures_success_output(tmp_path) -> None:
    executor = CommandExecutor(cwd=tmp_path)

    result = executor.run([sys.executable, "-c", "print('中文输出')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "中文输出"
    assert result.stderr == ""
    assert result.duration_ms >= 0
    assert result.command[0] == sys.executable


def test_command_executor_captures_failure_output(tmp_path) -> None:
    executor = CommandExecutor(cwd=tmp_path)

    result = executor.run([sys.executable, "-c", "import sys; print('错误', file=sys.stderr); sys.exit(7)"])

    assert result.exit_code == 7
    assert result.stdout == ""
    assert result.stderr.strip() == "错误"
```

- [ ] **Step 2: Run command executor tests to verify failure**

Run:

```powershell
python -m pytest tests/test_tool_executor.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.tools`.

- [ ] **Step 3: Implement command executor**

Write `src/dev_agent/tools/__init__.py`:

```python
"""Tool execution helpers."""
```

Write `src/dev_agent/tools/executor.py`:

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time

from dev_agent.encoding import UTF8


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class CommandExecutor:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def run(self, command: list[str], timeout_seconds: int = 120) -> CommandResult:
        start = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=self.cwd,
            text=True,
            encoding=UTF8,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        return CommandResult(
            command=command,
            cwd=self.cwd,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
        )
```

- [ ] **Step 4: Run command executor tests**

Run:

```powershell
python -m pytest tests/test_tool_executor.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit command executor**

Run:

```powershell
git add src/dev_agent/tools tests/test_tool_executor.py
git commit -m "feat: add command executor"
```

Expected: commit succeeds.

---

### Task 4: Git Read-Only Adapter

**Files:**
- Create: `src/dev_agent/tools/git.py`
- Test: `tests/test_git_reader.py`

- [ ] **Step 1: Write failing Git reader tests**

Write `tests/test_git_reader.py`:

```python
import subprocess

from dev_agent.encoding import write_text_utf8
from dev_agent.tools.git import GitReader


def git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_git_reader_reports_status_log_and_diff_stat(tmp_path) -> None:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    write_text_utf8(tmp_path / "README.md", "# 示例\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "initial")
    write_text_utf8(tmp_path / "README.md", "# 示例\n\n更新\n")

    reader = GitReader(tmp_path)
    snapshot = reader.snapshot()

    assert "README.md" in snapshot.status
    assert "README.md" in snapshot.diff_stat
    assert "initial" in snapshot.recent_log
```

- [ ] **Step 2: Run Git reader tests to verify failure**

Run:

```powershell
python -m pytest tests/test_git_reader.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.tools.git`.

- [ ] **Step 3: Implement Git reader**

Write `src/dev_agent/tools/git.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from dev_agent.tools.executor import CommandExecutor


@dataclass(frozen=True)
class GitSnapshot:
    status: str
    diff_stat: str
    recent_log: str


class GitReader:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.executor = CommandExecutor(repo_root)

    def snapshot(self) -> GitSnapshot:
        status = self.executor.run(["git", "status", "--short"])
        diff_stat = self.executor.run(["git", "diff", "--stat"])
        recent_log = self.executor.run(["git", "log", "--oneline", "-5"])
        return GitSnapshot(
            status=status.stdout,
            diff_stat=diff_stat.stdout,
            recent_log=recent_log.stdout,
        )
```

- [ ] **Step 4: Run Git reader tests**

Run:

```powershell
python -m pytest tests/test_git_reader.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit Git reader**

Run:

```powershell
git add src/dev_agent/tools/git.py tests/test_git_reader.py
git commit -m "feat: add git read-only adapter"
```

Expected: commit succeeds.

---

### Task 5: Verification Planner and Runner

**Files:**
- Create: `src/dev_agent/verification/__init__.py`
- Create: `src/dev_agent/verification/planner.py`
- Create: `src/dev_agent/verification/runner.py`
- Test: `tests/test_verification.py`

- [ ] **Step 1: Write failing verification tests**

Write `tests/test_verification.py`:

```python
import sys

from dev_agent.config.models import CommandConfig
from dev_agent.project.scanner import ProjectScan
from dev_agent.verification.planner import build_verification_plan
from dev_agent.verification.runner import VerificationRunner


def test_verification_plan_prefers_explicit_commands(tmp_path) -> None:
    scan = ProjectScan(root=tmp_path, languages=["python"], markers=["pyproject.toml"])
    commands = CommandConfig(test="custom test", lint="custom lint")

    plan = build_verification_plan(commands, scan)

    assert [step.name for step in plan.steps] == ["test", "lint"]
    assert plan.steps[0].command == ["custom", "test"]


def test_verification_plan_uses_scan_suggestions(tmp_path) -> None:
    scan = ProjectScan(
        root=tmp_path,
        languages=["python"],
        markers=["pyproject.toml"],
        suggested_commands=CommandConfig(test="python -m pytest"),
    )

    plan = build_verification_plan(CommandConfig(), scan)

    assert len(plan.steps) == 1
    assert plan.steps[0].command == ["python", "-m", "pytest"]


def test_verification_runner_aggregates_results(tmp_path) -> None:
    commands = CommandConfig(test=f"{sys.executable} -c \"print('ok')\"")
    scan = ProjectScan(root=tmp_path, languages=["python"], markers=[])
    plan = build_verification_plan(commands, scan)

    result = VerificationRunner(tmp_path).run(plan)

    assert result.passed is True
    assert result.results[0].exit_code == 0
    assert result.results[0].stdout.strip() == "ok"
```

- [ ] **Step 2: Run verification tests to verify failure**

Run:

```powershell
python -m pytest tests/test_verification.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.verification`.

- [ ] **Step 3: Implement verification planner**

Write `src/dev_agent/verification/__init__.py`:

```python
"""Verification planning and execution."""
```

Write `src/dev_agent/verification/planner.py`:

```python
from dataclasses import dataclass
import shlex

from dev_agent.config.models import CommandConfig
from dev_agent.project.scanner import ProjectScan


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: list[str]


@dataclass(frozen=True)
class VerificationPlan:
    steps: list[VerificationStep]


def _split(command: str | None) -> list[str] | None:
    if not command:
        return None
    return shlex.split(command, posix=False)


def build_verification_plan(commands: CommandConfig, scan: ProjectScan) -> VerificationPlan:
    steps: list[VerificationStep] = []
    candidates = {
        "test": commands.test or scan.suggested_commands.test,
        "lint": commands.lint or scan.suggested_commands.lint,
        "typecheck": commands.typecheck or scan.suggested_commands.typecheck,
        "build": commands.build or scan.suggested_commands.build,
    }
    for name, command in candidates.items():
        parts = _split(command)
        if parts:
            steps.append(VerificationStep(name=name, command=parts))
    return VerificationPlan(steps=steps)
```

- [ ] **Step 4: Implement verification runner**

Write `src/dev_agent/verification/runner.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from dev_agent.tools.executor import CommandExecutor, CommandResult
from dev_agent.verification.planner import VerificationPlan


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    results: list[CommandResult]


class VerificationRunner:
    def __init__(self, cwd: Path) -> None:
        self.executor = CommandExecutor(cwd)

    def run(self, plan: VerificationPlan) -> VerificationResult:
        results = [self.executor.run(step.command) for step in plan.steps]
        return VerificationResult(
            passed=all(result.exit_code == 0 for result in results),
            results=results,
        )
```

- [ ] **Step 5: Run verification tests**

Run:

```powershell
python -m pytest tests/test_verification.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit verification planner and runner**

Run:

```powershell
git add src/dev_agent/verification tests/test_verification.py
git commit -m "feat: plan and run verification commands"
```

Expected: commit succeeds.

---

### Task 6: CLI Doctor Capability Summary

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Extend failing CLI doctor test**

Modify `test_doctor_outputs_json` in `tests/test_cli.py`:

```python
def test_doctor_outputs_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"
    assert payload["capabilities"] == {
        "provider_interface": True,
        "budget_protection": True,
        "command_executor": True,
        "git_reader": True,
        "verification_runner": True,
    }
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL with `KeyError: 'capabilities'`.

- [ ] **Step 3: Update doctor output**

Modify `doctor_command` in `src/dev_agent/cli.py`:

```python
def doctor_command(args: Namespace) -> int:
    payload = {
        "ok": True,
        "version": __version__,
        "encoding": UTF8,
        "powershell_utf8_hint": utf8_environment_hint(),
        "capabilities": {
            "provider_interface": True,
            "budget_protection": True,
            "command_executor": True,
            "git_reader": True,
            "verification_runner": True,
        },
    }
    sys.stdout.write(_json(payload))
    return 0
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit doctor capability summary**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: report foundation capabilities in doctor"
```

Expected: commit succeeds.

---

### Task 7: Final Verification

**Files:**
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke commands**

Run:

```powershell
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
```

Expected: `doctor` outputs JSON with `"ok": true` and `capabilities`; `scan` outputs JSON with project languages and suggested commands.

- [ ] **Step 3: Inspect Git status**

Run:

```powershell
git status --short
```

Expected: no tracked implementation files remain unstaged. Ignored local caches such as `.pytest_cache/`, `__pycache__/`, and `*.egg-info/` may exist but must not appear in Git status.

---

## Self-Review

**Spec coverage:** This plan covers the approved spec sections for model provider abstraction, provider budget protection, command execution, Git read-only inspection, and strong verification command execution. It intentionally leaves real cloud provider calls, Git write operations, task history retrieval, vector retrieval, and Web console for later plans.

**Concrete steps:** Every task includes exact files, test code, implementation code, verification commands, expected results, and a focused commit.

**Type consistency:** The plan consistently uses `ModelRequest`, `ModelResponse`, `ProviderUsage`, `ProviderError`, `BudgetConfig`, `CircuitBreaker`, `ProtectedProvider`, `CommandResult`, `GitSnapshot`, `VerificationPlan`, and `VerificationResult` with matching imports and field names.
