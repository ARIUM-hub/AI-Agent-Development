# 研发助手基础骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建研发助手第一阶段基础骨架，让 Windows 上的 Python CLI 能初始化仓库规则、诊断环境、加载配置、扫描 Python/Node 项目并记录任务状态。

**Architecture:** 本计划只实现规格文档的第一条可交付纵切片：Python 包、CLI、配置模型、项目扫描、任务状态和 UTF-8 基线。模型 provider、Git 自动提交、强验证执行器、历史向量检索和 Web 控制台在后续计划中接入这些接口。

**Tech Stack:** Python 3.11+、argparse、dataclasses、pathlib、json、PyYAML、pytest、Windows PowerShell。

---

## Scope Check

完整规格包含 CLI、Python 编排内核、模型 provider、成本熔断、Git、强验证、任务记忆、向量检索和本地 Web 控制台。它已经超过单个实施计划的合适范围。

本计划聚焦第一阶段基础骨架，完成后应满足：

- 可以运行 `python -m dev_agent.cli init` 创建 `.agent/` 规则文件。
- 可以运行 `python -m dev_agent.cli doctor` 输出环境诊断 JSON。
- 可以加载仓库规则与本机偏好，并按确定优先级合并。
- 可以识别 Python 与 Node.js/TypeScript 项目的基础结构。
- 可以创建、更新、读取任务状态文件。
- 所有文本读写固定使用 UTF-8，并有测试覆盖中文内容。

## File Structure

- Create: `pyproject.toml`，定义 Python 包、依赖和 pytest 配置。
- Create: `src/dev_agent/__init__.py`，暴露包版本。
- Create: `src/dev_agent/encoding.py`，集中处理 UTF-8 文本读写和 PowerShell 输出编码提示。
- Create: `src/dev_agent/config/models.py`，定义项目规则、用户偏好、合并配置的数据结构。
- Create: `src/dev_agent/config/loader.py`，加载 `.agent/` 与 `%USERPROFILE%/.dev-agent/` 配置并合并。
- Create: `src/dev_agent/project/scanner.py`，识别 Python 与 Node.js/TypeScript 项目结构。
- Create: `src/dev_agent/tasks/state.py`，管理任务状态 JSON 文件。
- Create: `src/dev_agent/cli.py`，实现 `init`、`doctor`、`scan` 三个基础命令。
- Create: `tests/test_encoding.py`，覆盖 UTF-8 中文读写。
- Create: `tests/test_config_loader.py`，覆盖规则加载和优先级合并。
- Create: `tests/test_project_scanner.py`，覆盖 Python/Node 项目识别。
- Create: `tests/test_task_state.py`，覆盖任务状态创建与更新。
- Create: `tests/test_cli.py`，覆盖 CLI 初始化、诊断和扫描命令。

---

### Task 1: Python Package Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/dev_agent/__init__.py`
- Create: `src/dev_agent/config/__init__.py`
- Create: `src/dev_agent/project/__init__.py`
- Create: `src/dev_agent/tasks/__init__.py`

- [ ] **Step 1: Create package metadata**

Write `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dev-agent"
version = "0.1.0"
description = "Windows-first personal development assistant foundation."
requires-python = ">=3.11"
dependencies = [
  "PyYAML>=6.0.2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
]

[project.scripts]
dev-agent = "dev_agent.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create package init files**

Write `src/dev_agent/__init__.py`:

```python
"""Development assistant foundation package."""

__version__ = "0.1.0"
```

Write `src/dev_agent/config/__init__.py`:

```python
"""Configuration loading and merge helpers."""
```

Write `src/dev_agent/project/__init__.py`:

```python
"""Project scanning helpers."""
```

Write `src/dev_agent/tasks/__init__.py`:

```python
"""Task state helpers."""
```

- [ ] **Step 3: Install development dependencies**

Run:

```powershell
python -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Expected: pip installs `dev-agent`, `PyYAML`, and `pytest` without errors.

- [ ] **Step 4: Verify empty test suite command works**

Run:

```powershell
python -m pytest
```

Expected: pytest exits successfully with `collected 0 items`.

- [ ] **Step 5: Commit skeleton**

Run:

```powershell
git add pyproject.toml src/dev_agent
git commit -m "chore: add Python package skeleton"
```

Expected: commit succeeds and includes only package skeleton files.

---

### Task 2: UTF-8 Encoding Utilities

**Files:**
- Create: `src/dev_agent/encoding.py`
- Create: `tests/test_encoding.py`

- [ ] **Step 1: Write failing UTF-8 tests**

Write `tests/test_encoding.py`:

```python
from pathlib import Path

from dev_agent.encoding import read_text_utf8, utf8_environment_hint, write_text_utf8


def test_write_and_read_utf8_chinese(tmp_path: Path) -> None:
    target = tmp_path / "规则.md"

    write_text_utf8(target, "中文规则：不要使用 unicode 转义。")

    assert read_text_utf8(target) == "中文规则：不要使用 unicode 转义。"
    assert target.read_bytes().startswith("中文".encode("utf-8"))


def test_utf8_environment_hint_mentions_powershell() -> None:
    hint = utf8_environment_hint()

    assert "[Console]::OutputEncoding" in hint
    assert "UTF8" in hint
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_encoding.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dev_agent.encoding'`.

- [ ] **Step 3: Implement encoding utilities**

Write `src/dev_agent/encoding.py`:

```python
from pathlib import Path


UTF8 = "utf-8"


def read_text_utf8(path: Path) -> str:
    return path.read_text(encoding=UTF8)


def write_text_utf8(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=UTF8, newline="\n")


def utf8_environment_hint() -> str:
    return (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8"
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
python -m pytest tests/test_encoding.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit encoding utilities**

Run:

```powershell
git add src/dev_agent/encoding.py tests/test_encoding.py
git commit -m "feat: add UTF-8 text utilities"
```

Expected: commit succeeds.

---

### Task 3: Configuration Models and Loader

**Files:**
- Create: `src/dev_agent/config/models.py`
- Create: `src/dev_agent/config/loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write failing configuration tests**

Write `tests/test_config_loader.py`:

```python
from pathlib import Path

from dev_agent.config.loader import load_agent_context
from dev_agent.encoding import write_text_utf8


def test_loads_repository_rules_and_user_preferences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    write_text_utf8(
        repo / ".agent" / "project.yaml",
        "name: 演示项目\ntech_stack:\n  - python\n",
    )
    write_text_utf8(
        repo / ".agent" / "commands.yaml",
        "test: python -m pytest\nlint: python -m ruff check .\n",
    )
    write_text_utf8(
        repo / ".agent" / "rules.md",
        "所有文件默认 UTF-8，中文不要写成 unicode 转义。\n",
    )
    write_text_utf8(
        home / ".dev-agent" / "preferences.yaml",
        "language: zh-CN\napproval_mode: collaborative\n",
    )

    context = load_agent_context(repo, home)

    assert context.project.name == "演示项目"
    assert context.project.tech_stack == ["python"]
    assert context.commands.test == "python -m pytest"
    assert context.commands.lint == "python -m ruff check ."
    assert context.rules_text.startswith("所有文件默认 UTF-8")
    assert context.preferences.language == "zh-CN"
    assert context.preferences.approval_mode == "collaborative"


def test_missing_files_use_safe_defaults(tmp_path: Path) -> None:
    context = load_agent_context(tmp_path / "repo", tmp_path / "home")

    assert context.project.name == "repo"
    assert context.project.tech_stack == []
    assert context.commands.test is None
    assert context.preferences.language == "zh-CN"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_config_loader.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.config.loader`.

- [ ] **Step 3: Implement configuration models**

Write `src/dev_agent/config/models.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    tech_stack: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandConfig:
    test: str | None = None
    lint: str | None = None
    typecheck: str | None = None
    build: str | None = None


@dataclass(frozen=True)
class UserPreferences:
    language: str = "zh-CN"
    approval_mode: str = "collaborative"


@dataclass(frozen=True)
class AgentContext:
    project: ProjectConfig
    commands: CommandConfig
    preferences: UserPreferences
    rules_text: str
```

- [ ] **Step 4: Implement configuration loader**

Write `src/dev_agent/config/loader.py`:

```python
from pathlib import Path
from typing import Any

import yaml

from dev_agent.config.models import AgentContext, CommandConfig, ProjectConfig, UserPreferences
from dev_agent.encoding import read_text_utf8


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(read_text_utf8(path))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML file: {path}")
    return data


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return read_text_utf8(path)


def load_agent_context(repo_root: Path, home_dir: Path) -> AgentContext:
    repo_root = repo_root.resolve()
    home_dir = home_dir.resolve()
    agent_dir = repo_root / ".agent"
    user_dir = home_dir / ".dev-agent"

    project_data = _read_yaml(agent_dir / "project.yaml")
    command_data = _read_yaml(agent_dir / "commands.yaml")
    preference_data = _read_yaml(user_dir / "preferences.yaml")

    project = ProjectConfig(
        name=str(project_data.get("name") or repo_root.name),
        tech_stack=[str(item) for item in project_data.get("tech_stack", [])],
    )
    commands = CommandConfig(
        test=command_data.get("test"),
        lint=command_data.get("lint"),
        typecheck=command_data.get("typecheck"),
        build=command_data.get("build"),
    )
    preferences = UserPreferences(
        language=str(preference_data.get("language") or "zh-CN"),
        approval_mode=str(preference_data.get("approval_mode") or "collaborative"),
    )

    return AgentContext(
        project=project,
        commands=commands,
        preferences=preferences,
        rules_text=_read_optional_text(agent_dir / "rules.md"),
    )
```

- [ ] **Step 5: Run configuration tests**

Run:

```powershell
python -m pytest tests/test_config_loader.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run encoding and configuration tests together**

Run:

```powershell
python -m pytest tests/test_encoding.py tests/test_config_loader.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit configuration loader**

Run:

```powershell
git add src/dev_agent/config tests/test_config_loader.py
git commit -m "feat: load agent configuration"
```

Expected: commit succeeds.

---

### Task 4: Project Scanner

**Files:**
- Create: `src/dev_agent/project/scanner.py`
- Create: `tests/test_project_scanner.py`

- [ ] **Step 1: Write failing scanner tests**

Write `tests/test_project_scanner.py`:

```python
from pathlib import Path

from dev_agent.encoding import write_text_utf8
from dev_agent.project.scanner import scan_project


def test_scans_python_project(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"demo\"\n")
    write_text_utf8(tmp_path / "pytest.ini", "[pytest]\n")

    result = scan_project(tmp_path)

    assert result.languages == ["python"]
    assert "pyproject.toml" in result.markers
    assert result.suggested_commands.test == "python -m pytest"


def test_scans_node_typescript_project(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "package.json", "{\"scripts\":{\"test\":\"vitest\",\"build\":\"tsc\"}}\n")
    write_text_utf8(tmp_path / "tsconfig.json", "{}\n")

    result = scan_project(tmp_path)

    assert result.languages == ["node", "typescript"]
    assert "package.json" in result.markers
    assert result.suggested_commands.test == "npm test"
    assert result.suggested_commands.build == "npm run build"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_project_scanner.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.project.scanner`.

- [ ] **Step 3: Implement project scanner**

Write `src/dev_agent/project/scanner.py`:

```python
from dataclasses import dataclass, field
from pathlib import Path

from dev_agent.config.models import CommandConfig


@dataclass(frozen=True)
class ProjectScan:
    root: Path
    languages: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    suggested_commands: CommandConfig = field(default_factory=CommandConfig)


def _has(root: Path, name: str) -> bool:
    return (root / name).exists()


def scan_project(root: Path) -> ProjectScan:
    root = root.resolve()
    languages: list[str] = []
    markers: list[str] = []
    test_command: str | None = None
    lint_command: str | None = None
    typecheck_command: str | None = None
    build_command: str | None = None

    if _has(root, "pyproject.toml") or _has(root, "requirements.txt"):
        languages.append("python")
        for marker in ("pyproject.toml", "requirements.txt", "pytest.ini"):
            if _has(root, marker):
                markers.append(marker)
        test_command = "python -m pytest"

    if _has(root, "package.json"):
        languages.append("node")
        markers.append("package.json")
        test_command = test_command or "npm test"
        build_command = "npm run build"

    if _has(root, "tsconfig.json"):
        languages.append("typescript")
        markers.append("tsconfig.json")
        typecheck_command = "npm run typecheck"

    return ProjectScan(
        root=root,
        languages=languages,
        markers=markers,
        suggested_commands=CommandConfig(
            test=test_command,
            lint=lint_command,
            typecheck=typecheck_command,
            build=build_command,
        ),
    )
```

- [ ] **Step 4: Run scanner tests**

Run:

```powershell
python -m pytest tests/test_project_scanner.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run all current tests**

Run:

```powershell
python -m pytest -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit project scanner**

Run:

```powershell
git add src/dev_agent/project/scanner.py tests/test_project_scanner.py
git commit -m "feat: scan project structure"
```

Expected: commit succeeds.

---

### Task 5: Task State Store

**Files:**
- Create: `src/dev_agent/tasks/state.py`
- Create: `tests/test_task_state.py`

- [ ] **Step 1: Write failing task state tests**

Write `tests/test_task_state.py`:

```python
from pathlib import Path

from dev_agent.tasks.state import TaskStatus, create_task, load_task, update_task_status


def test_creates_and_loads_task_state(tmp_path: Path) -> None:
    task = create_task(tmp_path, "实现登录接口")

    loaded = load_task(tmp_path, task.task_id)

    assert loaded.task_id == task.task_id
    assert loaded.title == "实现登录接口"
    assert loaded.status == TaskStatus.PLANNED
    assert loaded.events[0] == "task_created"


def test_updates_task_status(tmp_path: Path) -> None:
    task = create_task(tmp_path, "修复测试失败")

    updated = update_task_status(tmp_path, task.task_id, TaskStatus.RUNNING, "started_execution")

    assert updated.status == TaskStatus.RUNNING
    assert updated.events[-1] == "started_execution"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_task_state.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.tasks.state`.

- [ ] **Step 3: Implement task state store**

Write `src/dev_agent/tasks/state.py`:

```python
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
import json

from dev_agent.encoding import read_text_utf8, write_text_utf8


class TaskStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    BLOCKED = "blocked"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskState:
    task_id: str
    title: str
    status: TaskStatus
    created_at: str
    updated_at: str
    events: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_dir(repo_root: Path) -> Path:
    return repo_root / ".agent" / "tasks"


def _task_path(repo_root: Path, task_id: str) -> Path:
    return _task_dir(repo_root) / f"{task_id}.json"


def _dump(task: TaskState) -> str:
    data = asdict(task)
    data["status"] = task.status.value
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _parse(data: dict[str, object]) -> TaskState:
    return TaskState(
        task_id=str(data["task_id"]),
        title=str(data["title"]),
        status=TaskStatus(str(data["status"])),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
        events=[str(item) for item in data.get("events", [])],
    )


def create_task(repo_root: Path, title: str) -> TaskState:
    now = _now()
    task = TaskState(
        task_id=uuid4().hex,
        title=title,
        status=TaskStatus.PLANNED,
        created_at=now,
        updated_at=now,
        events=["task_created"],
    )
    write_text_utf8(_task_path(repo_root, task.task_id), _dump(task))
    return task


def load_task(repo_root: Path, task_id: str) -> TaskState:
    return _parse(json.loads(read_text_utf8(_task_path(repo_root, task_id))))


def update_task_status(repo_root: Path, task_id: str, status: TaskStatus, event: str) -> TaskState:
    current = load_task(repo_root, task_id)
    updated = TaskState(
        task_id=current.task_id,
        title=current.title,
        status=status,
        created_at=current.created_at,
        updated_at=_now(),
        events=[*current.events, event],
    )
    write_text_utf8(_task_path(repo_root, task_id), _dump(updated))
    return updated
```

- [ ] **Step 4: Run task state tests**

Run:

```powershell
python -m pytest tests/test_task_state.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run all current tests**

Run:

```powershell
python -m pytest -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit task state store**

Run:

```powershell
git add src/dev_agent/tasks/state.py tests/test_task_state.py
git commit -m "feat: persist task state"
```

Expected: commit succeeds.

---

### Task 6: CLI Init, Doctor, and Scan

**Files:**
- Create: `src/dev_agent/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Write `tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dev_agent.cli", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_init_creates_agent_files(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "init")

    assert result.returncode == 0
    assert (tmp_path / ".agent" / "project.yaml").exists()
    assert (tmp_path / ".agent" / "rules.md").read_text(encoding="utf-8").startswith("# 项目规则")
    assert "initialized" in result.stdout


def test_doctor_outputs_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"


def test_scan_outputs_project_languages(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{\"scripts\":{\"test\":\"vitest\"}}\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    result = run_cli(tmp_path, "scan")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["languages"] == ["node", "typescript"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `dev_agent.cli` does not exist.

- [ ] **Step 3: Implement CLI**

Write `src/dev_agent/cli.py`:

```python
from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import sys

from dev_agent import __version__
from dev_agent.encoding import UTF8, utf8_environment_hint, write_text_utf8
from dev_agent.project.scanner import scan_project


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def init_command(args: Namespace) -> int:
    root = Path.cwd()
    write_text_utf8(
        root / ".agent" / "project.yaml",
        f"name: {root.name}\ntech_stack: []\n",
    )
    write_text_utf8(
        root / ".agent" / "commands.yaml",
        "test:\nlint:\ntypecheck:\nbuild:\n",
    )
    write_text_utf8(
        root / ".agent" / "rules.md",
        "# 项目规则\n\n所有文本文件默认使用 UTF-8。包含中文时直接写中文字符。\n",
    )
    sys.stdout.write("initialized .agent configuration\n")
    return 0


def doctor_command(args: Namespace) -> int:
    payload = {
        "ok": True,
        "version": __version__,
        "encoding": UTF8,
        "powershell_utf8_hint": utf8_environment_hint(),
    }
    sys.stdout.write(_json(payload))
    return 0


def scan_command(args: Namespace) -> int:
    scan = scan_project(Path.cwd())
    payload = {
        "root": str(scan.root),
        "languages": scan.languages,
        "markers": scan.markers,
        "suggested_commands": {
            "test": scan.suggested_commands.test,
            "lint": scan.suggested_commands.lint,
            "typecheck": scan.suggested_commands.typecheck,
            "build": scan.suggested_commands.build,
        },
    }
    sys.stdout.write(_json(payload))
    return 0


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="dev-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.set_defaults(handler=init_command)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.set_defaults(handler=doctor_command)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.set_defaults(handler=scan_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
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

Expected: 11 passed.

- [ ] **Step 6: Commit CLI foundation**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: add foundation CLI commands"
```

Expected: commit succeeds.

---

### Task 7: Foundation Verification

**Files:**
- Verify: full foundation test suite and CLI smoke commands

- [ ] **Step 1: Run full verification**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
```

Expected: all tests pass, `doctor` outputs JSON with `"ok": true`, and `scan` outputs a JSON object with `languages`, `markers`, and `suggested_commands`.

- [ ] **Step 2: Inspect Git status**

Run:

```powershell
git status --short
```

Expected: no tracked implementation files remain unstaged. The existing `.superpowers/` visual brainstorming directory may remain untracked and should not be included in implementation commits.

- [ ] **Step 3: Record verification result in final response**

Report these facts in the execution final response:

- Full test command and result.
- CLI smoke command results.
- Git status summary.
- Any known limitation from this first foundation slice.

---

## Self-Review

**Spec coverage:** This plan covers the first implementation slice from the approved spec: package skeleton, Windows/UTF-8 baseline, repository rules, local preferences, project scanning, task state, and minimal CLI. It intentionally leaves model provider, cost breaker, tool execution, Git automation, history retrieval, vector retrieval, and Web console for follow-up plans because the approved spec spans multiple subsystems.

**Placeholder scan:** The plan contains concrete commands, expected results, and file content for every implementation step. It does not rely on vague deferred work descriptions.

**Type consistency:** The plan consistently uses `CommandConfig`, `ProjectConfig`, `UserPreferences`, `AgentContext`, `ProjectScan`, `TaskStatus`, and `TaskState`. Later tasks import only functions and classes defined in earlier tasks.
