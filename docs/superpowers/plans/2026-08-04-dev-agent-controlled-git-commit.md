# Controlled Git Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为研发助手增加只提交已审批执行计划实际目标、验证后再次确认、失败保留现场的受控 Git commit v1。

**Architecture:** 新建独立 `dev_agent.git` 包，由 `GitCommitGuard` 解析完整 porcelain 状态、执行 preflight/readiness、隔离暂存与普通 `git commit --only`，runner 只编排生命周期。commit 模式在 `provider_completed` 后建立 Git 基线，并冻结 `.agent` 审计落盘，直到提交成功、拒绝或失败结果确定后再统一持久化；CLI 负责参数校验和两次用户确认，Web 只返回稳定空字段。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、subprocess/Git porcelain、pytest、现有 OpenAI-compatible `/v1/chat/completions` 回环 HTTPServer；不新增第三方依赖。

---

## 文件结构

- Create: `src/dev_agent/git/__init__.py`：导出受控提交公共类型。
- Create: `src/dev_agent/git/models.py`：状态项、快照、请求、结果和分层错误。
- Create: `src/dev_agent/git/commit_guard.py`：porcelain 解析、preflight、readiness、暂存、commit、恢复和脱敏。
- Create: `tests/test_git_commit_guard.py`：独立临时 Git 仓库中的全部 Git 安全边界。
- Modify: `src/dev_agent/runtime/models.py`：增加 commit request、确认回调、结果和拒绝标记。
- Modify: `src/dev_agent/runtime/runner.py`：增加受控提交编排和 `.agent` 审计冻结。
- Modify: `src/dev_agent/cli.py`：新增参数、校验、第二次确认、JSON 和退出码。
- Modify: `src/dev_agent/web/api.py`：所有任务 payload 增加空 commit 字段。
- Modify: `tests/test_runtime_runner.py`：runner 成功、验证失败、拒绝和审计冻结测试。
- Modify: `tests/test_cli.py`：参数矩阵、fake、plan-file、真实 Provider 单请求和错误退出测试。
- Modify: `tests/test_web_api.py`、`tests/test_web_server.py`：Web schema 稳定且无 Git 写入口。

执行 Python 命令前设置：

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
```

实施应在 `codex/controlled-git-commit` 隔离分支或 worktree 中进行，不在 `master` 直接修改生产代码。

### Task 1: 建立 Git 数据模型、message 校验与 porcelain 解析

**Files:**
- Create: `src/dev_agent/git/__init__.py`
- Create: `src/dev_agent/git/models.py`
- Create: `src/dev_agent/git/commit_guard.py`
- Create: `tests/test_git_commit_guard.py`

- [ ] **Step 1: 写入 message 与 porcelain 解析失败测试**

在 `tests/test_git_commit_guard.py` 写入基础测试辅助和首批测试：

```python
from pathlib import Path
import subprocess

import pytest

from dev_agent.git.commit_guard import parse_porcelain_v1_z, validate_commit_message
from dev_agent.git.models import GitCommitPreflightError, GitStatusEntry


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=check,
    )


def init_repo(repo: Path) -> None:
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "tester")
    git(repo, "config", "user.email", "tester@example.invalid")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "--", "tracked.txt")
    git(repo, "commit", "-qm", "base")


@pytest.mark.parametrize(
    "message",
    ["", "   ", "a" * 201, "line one\nline two", "line one\rline two", "bad\0message"],
)
def test_validate_commit_message_rejects_unsafe_values(message: str) -> None:
    with pytest.raises(GitCommitPreflightError):
        validate_commit_message(message)


def test_validate_commit_message_accepts_single_line_chinese() -> None:
    assert validate_commit_message("fix: 修复参数校验") == "fix: 修复参数校验"


def test_parse_porcelain_v1_z_handles_spaces_chinese_and_rename() -> None:
    raw = (
        " M path with spaces.txt\0?? 中文.txt\0"
        "R  new name.txt\0old name.txt\0"
        " R worktree new.txt\0worktree old.txt\0"
    )

    assert parse_porcelain_v1_z(raw) == (
        GitStatusEntry(" ", "M", "path with spaces.txt"),
        GitStatusEntry("?", "?", "中文.txt"),
        GitStatusEntry("R", " ", "new name.txt", "old name.txt"),
        GitStatusEntry(" ", "R", "worktree new.txt", "worktree old.txt"),
    )


def test_parse_porcelain_v1_z_rejects_truncated_rename() -> None:
    with pytest.raises(GitCommitPreflightError, match="Git 状态"):
        parse_porcelain_v1_z("R  new.txt\0")
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m pytest tests/test_git_commit_guard.py -q
```

Expected: collection FAIL，`dev_agent.git` 尚不存在。

- [ ] **Step 3: 实现最小数据模型和 parser**

在 `src/dev_agent/git/models.py` 写入：

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class GitCommitError(Exception):
    pass


class GitCommitPreflightError(GitCommitError):
    pass


class GitCommitRejectedError(GitCommitError):
    pass


class GitCommitCommandError(GitCommitError):
    pass


@dataclass(frozen=True, order=True)
class GitStatusEntry:
    index: str
    worktree: str
    path: str
    original_path: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        if self.original_path is None:
            return (self.path,)
        return (self.path, self.original_path)


@dataclass(frozen=True)
class GitCommitSnapshot:
    head_sha: str
    branch: str
    status_entries: tuple[GitStatusEntry, ...]
    target_paths: tuple[str, ...]


@dataclass(frozen=True)
class GitCommitRequest:
    message: str
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitCommitResult:
    sha: str
    message: str
    paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"sha": self.sha, "message": self.message, "paths": list(self.paths)}


CommitConfirmation = Callable[[GitCommitRequest, tuple[str, ...]], bool]
```

在 `src/dev_agent/git/commit_guard.py` 写入：

```python
from __future__ import annotations

from pathlib import Path

from dev_agent.git.models import GitCommitPreflightError, GitStatusEntry


def validate_commit_message(message: str) -> str:
    if not message.strip():
        raise GitCommitPreflightError("--commit-message 不能为空")
    if len(message) > 200:
        raise GitCommitPreflightError("--commit-message 不能超过 200 个字符")
    if any(char in message for char in ("\r", "\n", "\0")):
        raise GitCommitPreflightError("--commit-message 必须是单行文本")
    return message


def parse_porcelain_v1_z(raw: str) -> tuple[GitStatusEntry, ...]:
    records = raw.split("\0")
    if records and records[-1] == "":
        records.pop()
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2] != " ":
            raise GitCommitPreflightError("无法解析 Git 状态")
        x, y, path = record[0], record[1], record[3:]
        original_path = None
        if x in {"R", "C"} or y in {"R", "C"}:
            index += 1
            if index >= len(records):
                raise GitCommitPreflightError("无法解析 Git 状态中的重命名记录")
            original_path = records[index]
        entries.append(GitStatusEntry(x, y, path, original_path))
        index += 1
    return tuple(entries)
```

在 `src/dev_agent/git/__init__.py` 导出稳定类型：

```python
from dev_agent.git.models import GitCommitRequest, GitCommitResult

__all__ = ["GitCommitRequest", "GitCommitResult"]
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: PASS。

- [ ] **Step 5: 提交模型与 parser**

```powershell
git add -- src/dev_agent/git tests/test_git_commit_guard.py
git commit -m "feat: add guarded git commit models"
```

### Task 2: 实现仓库、操作状态和目标路径 preflight

**Files:**
- Modify: `src/dev_agent/git/commit_guard.py`
- Modify: `tests/test_git_commit_guard.py`

- [ ] **Step 1: 写入 preflight 失败测试**

在 `tests/test_git_commit_guard.py` 增加：

```python
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.git.commit_guard import GitCommitGuard
from dev_agent.verification.planner import VerificationPlan, VerificationStep


def verification_plan() -> VerificationPlan:
    return VerificationPlan(
        steps=[VerificationStep("test", ["python", "-c", "print('ok')"])]
    )


def overwrite_plan() -> ExecutionPlan:
    return ExecutionPlan(
        "修改 tracked",
        [ExecutionOperation("overwrite_text", "tracked.txt", "changed\n")],
    )


def test_preflight_accepts_unrelated_staged_and_untracked_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("other\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    (tmp_path / "notes.tmp").write_text("note\n", encoding="utf-8")

    snapshot = GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())

    assert snapshot.target_paths == ("tracked.txt",)
    assert any(entry.path == "other.txt" and entry.index == "A" for entry in snapshot.status_entries)
    assert any(entry.path == "notes.tmp" and entry.index == "?" for entry in snapshot.status_entries)


@pytest.mark.parametrize("mode", ["unstaged", "staged"])
def test_preflight_rejects_dirty_target(tmp_path: Path, mode: str) -> None:
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    if mode == "staged":
        git(tmp_path, "add", "--", "tracked.txt")

    with pytest.raises(GitCommitPreflightError, match="目标路径在运行前必须干净"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())


def test_preflight_rejects_ignored_create_target(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    git(tmp_path, "add", "--", ".gitignore")
    git(tmp_path, "commit", "-qm", "ignore generated")
    plan = ExecutionPlan(
        "创建 ignored",
        [ExecutionOperation("create_text", "generated/out.txt", "content\n")],
    )

    with pytest.raises(GitCommitPreflightError, match="Git ignore"):
        GitCommitGuard(tmp_path).preflight(plan, verification_plan())


def test_preflight_rejects_untracked_create_target(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "new.txt").write_text("existing untracked\n", encoding="utf-8")
    plan = ExecutionPlan(
        "创建冲突",
        [ExecutionOperation("create_text", "new.txt", "new\n")],
    )

    with pytest.raises(GitCommitPreflightError, match="目标路径在运行前必须干净"):
        GitCommitGuard(tmp_path).preflight(plan, verification_plan())


def test_preflight_rejects_empty_verification_plan(tmp_path: Path) -> None:
    init_repo(tmp_path)
    with pytest.raises(GitCommitPreflightError, match="至少一条验证命令"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), VerificationPlan([]))


def test_preflight_rejects_detached_head(tmp_path: Path) -> None:
    init_repo(tmp_path)
    git(tmp_path, "checkout", "--detach", "-q")
    with pytest.raises(GitCommitPreflightError, match="detached HEAD"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())


def test_preflight_rejects_unborn_branch(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.invalid")
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")

    with pytest.raises(GitCommitPreflightError, match="HEAD 尚无提交"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())
```

同一步增加进行中操作测试，marker 路径通过 Git 解析，不能假设 `.git` 是目录：

```python
@pytest.mark.parametrize(
    ("marker", "label", "is_directory"),
    [
        ("MERGE_HEAD", "merge", False),
        ("rebase-apply", "rebase", True),
        ("rebase-merge", "rebase", True),
        ("CHERRY_PICK_HEAD", "cherry-pick", False),
        ("REVERT_HEAD", "revert", False),
        ("BISECT_LOG", "bisect", False),
    ],
)
def test_preflight_rejects_git_operation_in_progress(
    tmp_path: Path,
    marker: str,
    label: str,
    is_directory: bool,
) -> None:
    init_repo(tmp_path)
    marker_path = Path(git(tmp_path, "rev-parse", "--git-path", marker).stdout.strip())
    if not marker_path.is_absolute():
        marker_path = tmp_path / marker_path
    if is_directory:
        marker_path.mkdir(parents=True)
    else:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("in progress\n", encoding="utf-8")

    with pytest.raises(GitCommitPreflightError, match=label):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())
```

- [ ] **Step 2: 运行 preflight 测试并确认 RED**

Run:

```powershell
python -m pytest tests/test_git_commit_guard.py -q
```

Expected: FAIL，`GitCommitGuard` 尚不存在。

- [ ] **Step 3: 实现 Git 命令边界和 preflight**

在 `commit_guard.py` 增加以下核心结构：

```python
from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.validation import ExecutionPlanValidator
from dev_agent.git.models import GitCommitSnapshot
from dev_agent.tools.executor import CommandExecutor, CommandResult
from dev_agent.verification.planner import VerificationPlan


IN_PROGRESS_MARKERS = {
    "MERGE_HEAD": "merge",
    "rebase-apply": "rebase",
    "rebase-merge": "rebase",
    "CHERRY_PICK_HEAD": "cherry-pick",
    "REVERT_HEAD": "revert",
    "BISECT_LOG": "bisect",
}


class GitCommitGuard:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.executor = CommandExecutor(self.repo_root)

    def preflight(
        self,
        plan: ExecutionPlan,
        verification_plan: VerificationPlan,
    ) -> GitCommitSnapshot:
        if not verification_plan.steps:
            raise GitCommitPreflightError("受控提交至少需要一条验证命令")
        self._require_repo_root()
        head_sha = self._head_sha()
        branch = self._branch()
        self._require_no_operation_in_progress()
        targets = self._target_paths(plan)
        entries = self._status_entries()
        dirty = sorted(
            path
            for entry in entries
            for path in entry.paths
            if path.casefold() in {target.casefold() for target in targets}
        )
        if dirty:
            raise GitCommitPreflightError(
                "目标路径在运行前必须干净：" + ", ".join(dirty)
            )
        validator = ExecutionPlanValidator(self.repo_root)
        for operation in plan.operations:
            path = validator.resolve_target(operation.path).relative_to(self.repo_root).as_posix()
            if operation.action == "create_text" and self._is_ignored(path):
                raise GitCommitPreflightError(f"新建目标被 Git ignore：{path}")
        return GitCommitSnapshot(head_sha, branch, entries, targets)

    def _git(self, args: list[str], allowed: set[int] = {0}) -> CommandResult:
        result = self.executor.run(["git", *args])
        if result.exit_code not in allowed:
            detail = self._sanitize_output(result.stderr or result.stdout)
            raise GitCommitPreflightError(detail or "Git 命令执行失败")
        return result

    def _require_repo_root(self) -> None:
        root = Path(self._git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
        if root != self.repo_root:
            raise GitCommitPreflightError("命令必须从 Git worktree 根目录运行")

    def _head_sha(self) -> str:
        result = self.executor.run(["git", "rev-parse", "--verify", "HEAD"])
        if result.exit_code != 0 or not result.stdout.strip():
            raise GitCommitPreflightError("当前分支 HEAD 尚无提交，拒绝受控提交")
        return result.stdout.strip().lower()

    def _branch(self) -> str:
        result = self._git(["symbolic-ref", "--quiet", "--short", "HEAD"], {0, 1})
        if result.exit_code != 0 or not result.stdout.strip():
            raise GitCommitPreflightError("受控提交不支持 detached HEAD")
        return result.stdout.strip()

    def _status_entries(self) -> tuple[GitStatusEntry, ...]:
        raw = self._git(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        ).stdout
        return parse_porcelain_v1_z(raw)

    def _target_paths(self, plan: ExecutionPlan) -> tuple[str, ...]:
        validator = ExecutionPlanValidator(self.repo_root)
        paths: dict[str, str] = {}
        for operation in plan.operations:
            path = validator.resolve_target(operation.path).relative_to(self.repo_root).as_posix()
            paths.setdefault(path.casefold(), path)
        return tuple(paths.values())

    def _is_ignored(self, path: str) -> bool:
        result = self._git(["check-ignore", "-q", "--", path], {0, 1})
        return result.exit_code == 0
```

同一实现步骤加入完整 marker 检测和输出脱敏：

```python
import re

from dev_agent.git.models import GitCommitError


    def _require_no_operation_in_progress(
        self,
        error_type: type[GitCommitError] = GitCommitPreflightError,
    ) -> None:
        for marker, label in IN_PROGRESS_MARKERS.items():
            raw = self._git(["rev-parse", "--git-path", marker]).stdout.strip()
            marker_path = Path(raw)
            if not marker_path.is_absolute():
                marker_path = self.repo_root / marker_path
            if marker_path.exists():
                raise error_type(f"Git {label} 操作正在进行，拒绝提交")

    def _sanitize_output(self, output: str) -> str:
        sanitized = output.replace(str(self.repo_root), "<repo>")
        sanitized = sanitized.replace(self.repo_root.as_posix(), "<repo>")
        sanitized = re.sub(
            r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+",
            r"\1=<redacted>",
            sanitized,
        )
        limit = 2000
        if len(sanitized) > limit:
            return sanitized[:limit] + "\n<已截断>"
        return sanitized.strip()
```

- [ ] **Step 4: 运行 preflight 测试并确认 GREEN**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: PASS。

- [ ] **Step 5: 提交 preflight**

```powershell
git add -- src/dev_agent/git/commit_guard.py tests/test_git_commit_guard.py
git commit -m "feat: add git commit preflight"
```

### Task 3: 实现 apply 后快照比较和实际目标选择

**Files:**
- Modify: `src/dev_agent/git/commit_guard.py`
- Modify: `tests/test_git_commit_guard.py`

- [ ] **Step 1: 写入 readiness 失败测试**

在 `tests/test_git_commit_guard.py` 增加：

```python
from dev_agent.git.models import GitCommitRejectedError


def test_prepare_commit_returns_only_changed_targets(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "second.txt").write_text("second\n", encoding="utf-8")
    git(tmp_path, "add", "--", "second.txt")
    git(tmp_path, "commit", "-qm", "add second")
    plan = ExecutionPlan(
        "修改两个目标",
        [
            ExecutionOperation("overwrite_text", "tracked.txt", "changed\n"),
            ExecutionOperation("overwrite_text", "second.txt", "second\n"),
        ],
    )
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(plan, verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    assert guard.prepare_commit(snapshot) == ("tracked.txt",)


def test_prepare_commit_preserves_initial_unrelated_staged_state(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("staged\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    assert guard.prepare_commit(snapshot) == ("tracked.txt",)


@pytest.mark.parametrize("change", ["modify", "create", "stage"])
def test_prepare_commit_rejects_new_unrelated_state(tmp_path: Path, change: str) -> None:
    init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("base\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    git(tmp_path, "commit", "-qm", "add other")
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    if change == "modify":
        (tmp_path / "other.txt").write_text("modified\n", encoding="utf-8")
    elif change == "create":
        (tmp_path / "generated.tmp").write_text("generated\n", encoding="utf-8")
    else:
        (tmp_path / "other.txt").write_text("staged\n", encoding="utf-8")
        git(tmp_path, "add", "--", "other.txt")

    with pytest.raises(GitCommitRejectedError, match="目标外 Git 状态发生变化"):
        guard.prepare_commit(snapshot)


def test_prepare_commit_rejects_empty_difference(tmp_path: Path) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())

    with pytest.raises(GitCommitRejectedError, match="没有实际变化"):
        guard.prepare_commit(snapshot)


def test_prepare_commit_rejects_head_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "other.txt").write_text("other\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    git(tmp_path, "commit", "-qm", "external commit")

    with pytest.raises(GitCommitRejectedError, match="HEAD"):
        guard.prepare_commit(snapshot)


def test_prepare_commit_rejects_branch_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    git(tmp_path, "switch", "-c", "other-branch")
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(GitCommitRejectedError, match="分支"):
        guard.prepare_commit(snapshot)


def test_prepare_commit_rejects_new_git_operation_state(tmp_path: Path) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    marker = Path(git(tmp_path, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip())
    if not marker.is_absolute():
        marker = tmp_path / marker
    marker.write_text(snapshot.head_sha + "\n", encoding="utf-8")

    with pytest.raises(GitCommitRejectedError, match="merge"):
        guard.prepare_commit(snapshot)
```

- [ ] **Step 2: 运行 readiness 测试并确认 RED**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: FAIL，`prepare_commit` 尚不存在。

- [ ] **Step 3: 实现结构化快照比较**

在 `GitCommitGuard` 增加：

```python
    def prepare_commit(self, snapshot: GitCommitSnapshot) -> tuple[str, ...]:
        try:
            current_head = self._head_sha()
            current_branch = self._branch()
        except GitCommitPreflightError as exc:
            raise GitCommitRejectedError(str(exc)) from exc
        if current_head != snapshot.head_sha:
            raise GitCommitRejectedError("运行期间 HEAD 已变化，拒绝提交")
        if current_branch != snapshot.branch:
            raise GitCommitRejectedError("运行期间分支已变化，拒绝提交")
        self._require_no_operation_in_progress(error_type=GitCommitRejectedError)
        current = self._status_entries()
        targets = {path.casefold() for path in snapshot.target_paths}
        before_outside = self._outside_entries(snapshot.status_entries, targets)
        after_outside = self._outside_entries(current, targets)
        if before_outside != after_outside:
            changed = sorted(
                {path for entry in before_outside ^ after_outside for path in entry.paths}
            )
            raise GitCommitRejectedError(
                "目标外 Git 状态发生变化：" + ", ".join(changed)
            )
        changed_targets = sorted(
            {
                entry.path
                for entry in current
                if all(path.casefold() in targets for path in entry.paths)
            }
        )
        if not changed_targets:
            raise GitCommitRejectedError("目标路径没有实际变化，不创建空提交")
        return tuple(changed_targets)

    @staticmethod
    def _outside_entries(
        entries: tuple[GitStatusEntry, ...],
        targets: set[str],
    ) -> frozenset[GitStatusEntry]:
        return frozenset(
            entry
            for entry in entries
            if any(path.casefold() not in targets for path in entry.paths)
        )
```

把 `_require_no_operation_in_progress()` 参数化为可抛出 `GitCommitPreflightError` 或 `GitCommitRejectedError`，错误文本只含操作名称，不含 `.git` 绝对路径。

- [ ] **Step 4: 运行 readiness 测试并确认 GREEN**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: PASS。

- [ ] **Step 5: 提交 readiness**

```powershell
git add -- src/dev_agent/git/commit_guard.py tests/test_git_commit_guard.py
git commit -m "feat: guard git state before commit"
```

### Task 4: 实现目标隔离提交、后校验和失败恢复

**Files:**
- Modify: `src/dev_agent/git/commit_guard.py`
- Modify: `tests/test_git_commit_guard.py`

- [ ] **Step 1: 写入成功提交和无关 staged 保留测试**

在 `tests/test_git_commit_guard.py` 增加：

```python
def test_commit_only_includes_targets_and_preserves_unrelated_stage(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "unstaged.txt").write_text("base\n", encoding="utf-8")
    git(tmp_path, "add", "--", "unstaged.txt")
    git(tmp_path, "commit", "-qm", "add unrelated tracked file")
    (tmp_path / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    (tmp_path / "other.txt").write_text("staged other\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    (tmp_path / "notes.tmp").write_text("untracked\n", encoding="utf-8")
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    paths = guard.prepare_commit(snapshot)

    result = guard.commit(snapshot, " fix: 修改目标 ", paths)

    assert result.message == " fix: 修改目标 "
    assert result.paths == ("tracked.txt",)
    assert git(tmp_path, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.splitlines() == ["tracked.txt"]
    assert git(tmp_path, "rev-parse", "HEAD^").stdout.strip() == snapshot.head_sha
    commit_object = git(tmp_path, "cat-file", "commit", "HEAD").stdout
    assert commit_object.partition("\n\n")[2].removesuffix("\n") == " fix: 修改目标 "
    assert set(git(tmp_path, "status", "--short").stdout.splitlines()) == {
        "A  other.txt",
        " M unstaged.txt",
        "?? notes.tmp",
    }


def test_commit_supports_new_target_without_empty_commit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    plan = ExecutionPlan(
        "创建文档",
        [ExecutionOperation("create_text", "docs/new.md", "中文\n")],
    )
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(plan, verification_plan())
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/new.md").write_text("中文\n", encoding="utf-8")

    result = guard.commit(snapshot, "docs: 添加中文说明", guard.prepare_commit(snapshot))

    assert result.paths == ("docs/new.md",)


def test_commit_supports_multiple_changed_targets(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "second.txt").write_text("before second\n", encoding="utf-8")
    git(tmp_path, "add", "--", "second.txt")
    git(tmp_path, "commit", "-qm", "add second")
    plan = ExecutionPlan(
        "修改两个文件",
        [
            ExecutionOperation("overwrite_text", "tracked.txt", "after first\n"),
            ExecutionOperation("overwrite_text", "second.txt", "after second\n"),
        ],
    )
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(plan, verification_plan())
    (tmp_path / "tracked.txt").write_text("after first\n", encoding="utf-8")
    (tmp_path / "second.txt").write_text("after second\n", encoding="utf-8")

    result = guard.commit(snapshot, "fix: 修改两个文件", guard.prepare_commit(snapshot))

    assert result.paths == ("second.txt", "tracked.txt")
```

- [ ] **Step 2: 写入 hook 失败恢复和脱敏测试**

```python
from dev_agent.git.models import GitCommitCommandError
from dev_agent.tools.executor import CommandResult


def test_commit_hook_failure_unstages_target_and_preserves_worktree(tmp_path: Path) -> None:
    init_repo(tmp_path)
    hook = Path(git(tmp_path, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip())
    if not hook.is_absolute():
        hook = tmp_path / hook
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho hook-denied >&2\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(GitCommitCommandError, match="hook-denied"):
        guard.commit(snapshot, "fix: should fail", guard.prepare_commit(snapshot))

    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "changed\n"
    assert git(tmp_path, "diff", "--cached", "--name-only").stdout == ""
    assert git(tmp_path, "diff", "--name-only").stdout.strip() == "tracked.txt"


def test_git_add_failure_keeps_target_unstaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    original_run = guard.executor.run

    def fail_add(command: list[str], timeout_seconds: int = 120) -> CommandResult:
        if command[:2] == ["git", "add"]:
            return CommandResult(command, tmp_path, 1, "", "add denied", 1)
        return original_run(command, timeout_seconds)

    monkeypatch.setattr(guard.executor, "run", fail_add)

    with pytest.raises(GitCommitCommandError, match="add denied"):
        guard.commit(snapshot, "fix: should fail", guard.prepare_commit(snapshot))

    assert git(tmp_path, "diff", "--cached", "--name-only").stdout == ""
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "changed\n"


def test_restore_failure_requests_manual_index_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    original_run = guard.executor.run

    def fail_commit_and_restore(
        command: list[str],
        timeout_seconds: int = 120,
    ) -> CommandResult:
        if command[:2] == ["git", "commit"]:
            return CommandResult(command, tmp_path, 1, "", "commit denied", 1)
        if command[:3] == ["git", "restore", "--staged"]:
            return CommandResult(command, tmp_path, 1, "", "restore denied", 1)
        return original_run(command, timeout_seconds)

    monkeypatch.setattr(guard.executor, "run", fail_commit_and_restore)

    with pytest.raises(GitCommitCommandError, match="人工检查 Git index"):
        guard.commit(snapshot, "fix: should fail", guard.prepare_commit(snapshot))


def test_post_validation_failure_does_not_reset_created_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_repo(tmp_path)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    def fail_validation(*_args: object) -> None:
        raise GitCommitCommandError("post validation failed")

    monkeypatch.setattr(guard, "_validate_created_commit", fail_validation)

    with pytest.raises(GitCommitCommandError, match="post validation failed"):
        guard.commit(snapshot, "fix: created before failure", guard.prepare_commit(snapshot))

    assert git(tmp_path, "rev-parse", "HEAD").stdout.strip() != snapshot.head_sha


def test_successful_hook_cannot_leave_dirty_target(tmp_path: Path) -> None:
    init_repo(tmp_path)
    hook = Path(git(tmp_path, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip())
    if not hook.is_absolute():
        hook = tmp_path / hook
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\nprintf 'hook changed\\n' > tracked.txt\nexit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("approved\n", encoding="utf-8")

    with pytest.raises(GitCommitCommandError, match="目标路径仍有未提交变化"):
        guard.commit(snapshot, "fix: approved content", guard.prepare_commit(snapshot))

    assert git(tmp_path, "rev-parse", "HEAD").stdout.strip() != snapshot.head_sha
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "hook changed\n"


def test_git_error_redacts_repo_path_and_truncates_hook_output(tmp_path: Path) -> None:
    init_repo(tmp_path)
    hook = Path(git(tmp_path, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip())
    if not hook.is_absolute():
        hook = tmp_path / hook
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\nprintf '%05000d' 1 >&2\necho ' " + str(tmp_path).replace("\\", "/") + " api_key=SECRET' >&2\nexit 1\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    guard = GitCommitGuard(tmp_path)
    snapshot = guard.preflight(overwrite_plan(), verification_plan())
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(GitCommitCommandError) as caught:
        guard.commit(snapshot, "fix: fail", guard.prepare_commit(snapshot))

    message = str(caught.value)
    assert str(tmp_path) not in message
    assert "SECRET" not in message
    assert "已截断" in message
    assert len(message) < 2300
```

- [ ] **Step 3: 运行 commit 测试并确认 RED**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: FAIL，`commit` 尚不存在。

- [ ] **Step 4: 实现 add、commit、恢复和后校验**

在 `GitCommitGuard` 增加：

```python
    def commit(
        self,
        snapshot: GitCommitSnapshot,
        message: str,
        changed_paths: tuple[str, ...],
    ) -> GitCommitResult:
        message = validate_commit_message(message)
        paths = tuple(sorted(set(changed_paths)))
        if not paths:
            raise GitCommitRejectedError("目标路径没有实际变化，不创建空提交")
        try:
            self._git_command(["add", "--", *paths])
            self._require_staged_targets(paths)
            self._require_outside_state(snapshot)
            self._git_command(
                ["commit", "--only", "--cleanup=verbatim", "-m", message, "--", *paths]
            )
        except (GitCommitCommandError, GitCommitRejectedError):
            self._restore_target_index(paths)
            raise
        new_sha = self._head_sha()
        self._validate_created_commit(snapshot, new_sha, message, paths)
        return GitCommitResult(new_sha, message, paths)

    def _git_command(self, args: list[str]) -> CommandResult:
        result = self.executor.run(["git", *args])
        if result.exit_code != 0:
            detail = self._sanitize_output(result.stderr or result.stdout)
            raise GitCommitCommandError(detail or "Git 提交命令执行失败")
        return result

    def _restore_target_index(self, paths: tuple[str, ...]) -> None:
        result = self.executor.run(["git", "restore", "--staged", "--", *paths])
        if result.exit_code != 0:
            detail = self._sanitize_output(result.stderr or result.stdout)
            raise GitCommitCommandError(
                "提交失败且目标暂存恢复失败，请人工检查 Git index：" + detail
            )

    def _validate_created_commit(
        self,
        snapshot: GitCommitSnapshot,
        new_sha: str,
        message: str,
        paths: tuple[str, ...],
    ) -> None:
        parents = self._git_command(["rev-list", "--parents", "-n", "1", new_sha]).stdout.split()
        if len(parents) != 2 or parents[1].lower() != snapshot.head_sha:
            raise GitCommitCommandError("新提交父提交校验失败，请人工检查 Git 历史")
        committed = tuple(
            sorted(
                filter(
                    None,
                    self._git_command(
                        ["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", new_sha]
                    ).stdout.split("\0"),
                )
            )
        )
        if committed != paths:
            raise GitCommitCommandError("新提交文件集合校验失败，请人工检查 Git 历史")
        commit_object = self._git_command(["cat-file", "commit", new_sha]).stdout
        separator, committed_message = commit_object.partition("\n\n")[1:]
        if separator != "\n\n":
            raise GitCommitCommandError("无法解析新提交对象，请人工检查 Git 历史")
        committed_message = committed_message.removesuffix("\n")
        if committed_message != message or self._branch() != snapshot.branch:
            raise GitCommitCommandError("新提交 message 或分支校验失败，请人工检查 Git 历史")
        target_keys = {item.casefold() for item in paths}
        dirty_targets = sorted(
            {
                path
                for entry in self._status_entries()
                for path in entry.paths
                if path.casefold() in target_keys
            }
        )
        if dirty_targets:
            raise GitCommitCommandError(
                "新提交后目标路径仍有未提交变化，请人工检查："
                + ", ".join(dirty_targets)
            )
        try:
            self._require_outside_state(snapshot)
        except GitCommitRejectedError as exc:
            raise GitCommitCommandError(
                "新提交后的仓库状态校验失败，请人工检查 Git 历史：" + str(exc)
            ) from exc
```

同一实现步骤加入两个校验辅助函数：

```python
    def _require_staged_targets(self, paths: tuple[str, ...]) -> None:
        staged = tuple(
            sorted(
                filter(
                    None,
                    self._git_command(
                        ["diff", "--cached", "--name-only", "-z", "--", *paths]
                    ).stdout.split("\0"),
                )
            )
        )
        if staged != paths:
            raise GitCommitCommandError("目标暂存文件集合与审批范围不一致")

    def _require_outside_state(self, snapshot: GitCommitSnapshot) -> None:
        targets = {path.casefold() for path in snapshot.target_paths}
        before = self._outside_entries(snapshot.status_entries, targets)
        after = self._outside_entries(self._status_entries(), targets)
        if before != after:
            changed = sorted(
                {path for entry in before ^ after for path in entry.paths}
            )
            raise GitCommitRejectedError(
                "目标外 Git 状态发生变化：" + ", ".join(changed)
            )
```

提交后校验失败不能自动 reset 已创建提交，只报告需要人工检查。

- [ ] **Step 5: 运行 Git guard 全部测试并确认 GREEN**

Run: `python -m pytest tests/test_git_commit_guard.py -q`

Expected: PASS。

- [ ] **Step 6: 提交隔离 commit 能力**

```powershell
git add -- src/dev_agent/git/commit_guard.py tests/test_git_commit_guard.py
git commit -m "feat: commit approved git targets only"
```

### Task 5: 在 runner 中编排提交并冻结审计写入

**Files:**
- Modify: `src/dev_agent/runtime/models.py`
- Modify: `src/dev_agent/runtime/runner.py`
- Modify: `tests/test_runtime_runner.py`

- [ ] **Step 1: 写入 runtime 类型和成功路径失败测试**

在 `tests/test_runtime_runner.py` 增加 Git 初始化辅助，并增加：

```python
import json
import subprocess

from dev_agent.git.models import GitCommitRequest


def init_runtime_repo(repo: Path, verification_command: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.invalid"],
        cwd=repo,
        check=True,
    )
    write_text_utf8(repo / "target.txt", "before\n")
    write_text_utf8(repo / ".agent" / "commands.yaml", f"test: {verification_command}\n")
    subprocess.run(
        ["git", "add", "--", "target.txt", ".agent/commands.yaml"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)


def test_runner_commits_after_verification_and_freezes_audit_writes(
    tmp_path: Path,
) -> None:
    init_runtime_repo(tmp_path, 'python -c "print(\'ok\')"')
    plan = ExecutionPlan(
        "修改目标",
        [ExecutionOperation("overwrite_text", "target.txt", "after\n")],
    )
    preview = ExecutionPlanApplier(tmp_path).preview(plan)
    observed_events: list[str] = []

    def confirm(request: GitCommitRequest, paths: tuple[str, ...]) -> bool:
        task_files = list((tmp_path / ".agent" / "tasks").glob("*.json"))
        task_payload = json.loads(task_files[0].read_text(encoding="utf-8"))
        observed_events.extend(task_payload["events"])
        assert paths == ("target.txt",)
        assert not (tmp_path / ".agent" / "history" / "tasks.jsonl").exists()
        return True

    result = LocalTaskRunner(
        tmp_path,
        tmp_path,
        FakeProvider(name="fake-main", responses=["计划：修改目标。"]),
    ).run(
        "修改目标",
        TaskRunOptions(
            apply_changes=True,
            run_verification=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            commit_request=GitCommitRequest("fix: 修改目标"),
            confirm_commit=confirm,
        ),
    )

    assert observed_events[-1] == "provider_completed"
    assert "execution_completed" not in observed_events
    assert result.git_commit is not None
    assert result.git_commit.paths == ("target.txt",)
    assert result.commit_error is None
    assert result.commit_declined is False
    assert result.events[-3:] == [
        "verification_completed",
        "commit_completed",
        "runtime_completed",
    ]
    assert subprocess.run(
        ["git", "show", "--format=", "--name-only", "HEAD"],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.split() == ["target.txt"]
    history = MemoryStore(tmp_path).list_tasks()[-1]
    assert result.git_commit.sha in history.summary
    assert "fix: 修改目标" in history.summary
    assert "target.txt" in history.summary
```

- [ ] **Step 2: 写入验证失败和用户拒绝测试**

```python
def test_runner_does_not_confirm_or_commit_when_verification_fails(tmp_path: Path) -> None:
    init_runtime_repo(tmp_path, 'python -c "import sys; sys.exit(7)"')
    plan = ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "target.txt", "after\n")])
    preview = ExecutionPlanApplier(tmp_path).preview(plan)
    confirmation_calls = 0

    def confirm(_request: GitCommitRequest, _paths: tuple[str, ...]) -> bool:
        nonlocal confirmation_calls
        confirmation_calls += 1
        return True

    result = LocalTaskRunner(
        tmp_path,
        tmp_path,
        FakeProvider(name="fake-main", responses=["计划"]),
    ).run(
        "修改",
        TaskRunOptions(
            apply_changes=True,
            run_verification=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            commit_request=GitCommitRequest("fix: 不应提交"),
            confirm_commit=confirm,
        ),
    )

    assert confirmation_calls == 0
    assert result.verification_result is not None
    assert result.verification_result.passed is False
    assert result.git_commit is None
    assert result.commit_error is None
    assert subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=tmp_path, text=True, capture_output=True
    ).stdout.strip() == "1"


def test_runner_records_declined_commit_without_staging(tmp_path: Path) -> None:
    init_runtime_repo(tmp_path, 'python -c "print(\'ok\')"')
    plan = ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "target.txt", "after\n")])
    preview = ExecutionPlanApplier(tmp_path).preview(plan)

    result = LocalTaskRunner(
        tmp_path,
        tmp_path,
        FakeProvider(name="fake-main", responses=["计划"]),
    ).run(
        "修改",
        TaskRunOptions(
            apply_changes=True,
            run_verification=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            commit_request=GitCommitRequest("fix: 用户拒绝"),
            confirm_commit=lambda _request, _paths: False,
        ),
    )

    assert result.commit_declined is True
    assert result.git_commit is None
    assert result.commit_error is None
    assert "commit_rejected" in result.events
    assert subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    ).stdout == ""
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "after\n"
```

- [ ] **Step 3: 运行 runner 测试并确认 RED**

Run: `python -m pytest tests/test_runtime_runner.py -q`

Expected: FAIL，`TaskRunOptions` 和 `TaskRunResult` 尚无 commit 字段。

- [ ] **Step 4: 扩展 runtime 数据模型**

在 `runtime/models.py` 增加 imports 和字段：

```python
from dev_agent.git.models import (
    CommitConfirmation,
    GitCommitRequest,
    GitCommitResult,
)


@dataclass(frozen=True)
class TaskRunOptions:
    # 保留现有字段和顺序
    commit_request: GitCommitRequest | None = None
    confirm_commit: CommitConfirmation | None = None


@dataclass(frozen=True)
class TaskRunResult:
    # 保留现有字段
    git_commit: GitCommitResult | None = None
    commit_error: str | None = None
    commit_declined: bool = False
```

字段必须放在已有必填字段之后，避免 dataclass 的 non-default/default 顺序错误。原有调用方不传 commit 字段时行为不变。

- [ ] **Step 5: 在 runner 中增加独立 commit 路径**

保留现有非 commit 流程，新增 `_run_guarded_commit()`。`run()` 在 `provider_completed` 已持久化后分流：

```python
        if options.commit_request is not None:
            return self._run_guarded_commit(
                task=task,
                context=context,
                response=response,
                history_plan_text=history_plan_text,
                user_request=user_request,
                options=options,
            )
```

核心实现顺序固定为：

```python
    guard = GitCommitGuard(self.repo_root)
    snapshot = guard.preflight(options.execution_plan, context.verification_plan)
    queued_events = ["commit_preflight_completed"]
    execution_result = self._apply_execution_plan(options, expected_fingerprint)
    queued_events.append("execution_completed")
    verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
    queued_events.append("verification_completed")

    git_commit = None
    commit_error = None
    commit_declined = False
    if verification_result.passed:
        try:
            changed_paths = guard.prepare_commit(snapshot)
            assert options.confirm_commit is not None
            normalized_request = GitCommitRequest(
                message=options.commit_request.message,
                target_paths=snapshot.target_paths,
            )
            if not options.confirm_commit(normalized_request, changed_paths):
                commit_declined = True
                queued_events.append("commit_rejected")
            else:
                git_commit = guard.commit(snapshot, normalized_request.message, changed_paths)
                queued_events.append("commit_completed")
        except GitCommitRejectedError as exc:
            commit_error = str(exc)
            queued_events.append("commit_rejected")
        except GitCommitCommandError as exc:
            commit_error = str(exc)
            queued_events.append("commit_failed")
```

只有上面代码块结束后才逐个调用 `update_task_status()` 写入 `queued_events`，最后追加 `runtime_completed`。状态规则：验证失败或 `commit_error` 为 `FAILED`，用户主动拒绝为 `BLOCKED`，成功为 `PASSED`。随后调用一次 `_record_history()`；summary 成功时包含 commit SHA/message/paths，失败或拒绝时包含脱敏结果，不包含绝对路径。

统一 flush 和摘要函数写为：

```python
    def _flush_guarded_events(
        self,
        task: TaskState,
        queued_events: list[str],
        final_status: TaskStatus,
    ) -> TaskState:
        current = task
        for event in queued_events:
            current = update_task_status(
                self.repo_root,
                current.task_id,
                TaskStatus.RUNNING,
                event,
            )
        return update_task_status(
            self.repo_root,
            current.task_id,
            final_status,
            "runtime_completed",
        )

    def _build_guarded_summary(
        self,
        plan_text: str,
        execution_result: ExecutionResult,
        git_commit: GitCommitResult | None,
        commit_error: str | None,
        commit_declined: bool,
    ) -> str:
        summary = self._build_summary(plan_text, execution_result)
        if git_commit is not None:
            return (
                summary
                + f"\n\nGit commit: {git_commit.sha}"
                + f"\nMessage: {git_commit.message}"
                + "\nPaths: "
                + ", ".join(git_commit.paths)
            )
        if commit_error is not None:
            return summary + "\n\n提交失败：" + commit_error
        if commit_declined:
            return summary + "\n\n用户拒绝创建 Git 提交。"
        return summary + "\n\n验证失败，未创建 Git 提交。"
```

`TaskState` 从 `dev_agent.tasks.state` 导入。flush 之后使用返回 task 的最终 `events` 构造 `TaskRunResult` 并写一条历史；任何 guarded 分支都不得在 flush 前调用 `_record_history()`。

preflight 抛出 `GitCommitPreflightError` 时尚未进入冻结窗口：先把任务更新为 failed/`commit_rejected` 并记录历史，再重新抛出供 CLI 映射退出码 `2`。`commit_request` 存在但 `execution_plan` 或 `confirm_commit` 为 `None` 时同样抛中文 preflight 错误。

preflight 失败路径固定为：

```python
        try:
            snapshot = guard.preflight(options.execution_plan, context.verification_plan)
        except GitCommitPreflightError as exc:
            task = update_task_status(
                self.repo_root,
                task.task_id,
                TaskStatus.FAILED,
                "commit_rejected",
            )
            self._record_history(
                task_id=task.task_id,
                title=user_request,
                status=task.status.value,
                summary=history_plan_text + "\n\n提交预检失败：" + str(exc),
                events=task.events,
                verification=[
                    " ".join(step.command)
                    for step in context.verification_plan.steps
                ],
            )
            raise
```

- [ ] **Step 6: 运行 runner 定向和回归测试**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py tests/test_git_commit_guard.py -q
```

Expected: PASS，原有 runner 测试不需要修改断言。

- [ ] **Step 7: 提交 runner 编排**

```powershell
git add -- src/dev_agent/runtime/models.py src/dev_agent/runtime/runner.py tests/test_runtime_runner.py
git commit -m "feat: orchestrate verified git commits"
```

### Task 6: 完成 CLI 参数、确认、JSON 和退出码

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 写入参数矩阵失败测试**

在 `tests/test_cli.py` 增加：

```python
@pytest.mark.parametrize(
    "args, expected",
    [
        (("--commit", "--verify", "--commit-message", "fix: x"), "--commit 必须与 --apply"),
        (("--commit", "--apply", "--commit-message", "fix: x"), "--commit 必须与 --verify"),
        (("--commit", "--apply", "--verify"), "--commit-message"),
        (("--commit-message", "fix: x"), "只能与 --commit"),
        (("--commit", "--apply", "--verify", "--commit-message", "   "), "不能为空"),
        (("--commit", "--apply", "--verify", "--commit-message", "x" * 201), "200"),
    ],
)
def test_commit_argument_contract_rejects_invalid_combinations(
    tmp_path: Path,
    args: tuple[str, ...],
    expected: str,
) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "提交",
        "--fake-response",
        strict_cli_plan(),
        "--use-provider-plan",
        *args,
    )

    assert result.returncode == 2
    assert expected in result.stderr
    assert not (tmp_path / "docs/cli-provider.md").exists()
```

换行和 NUL 无法可靠作为 Windows subprocess argv 传递，因此增加直接单元测试：

```python
from argparse import Namespace

from dev_agent.cli import _validate_commit_arguments


@pytest.mark.parametrize("message", ["line one\rline two", "line one\nline two", "bad\0message"])
def test_validate_commit_arguments_rejects_control_characters(message: str) -> None:
    args = Namespace(
        commit=True,
        apply=True,
        verify=True,
        commit_message=message,
    )

    with pytest.raises(ValueError, match="单行"):
        _validate_commit_arguments(args)
```

- [ ] **Step 2: 写入 `--yes` plan-file 成功提交测试**

```python
def prepare_cli_commit_repo(tmp_path: Path, verification_command: str) -> Path:
    init_cli_git_repo(tmp_path)
    track_cli_file(tmp_path, "tracked.txt", b"before\n")
    write_text_utf8(
        tmp_path / ".agent" / "commands.yaml",
        f"test: {verification_command}\n",
    )
    subprocess.run(
        ["git", "add", "--", ".agent/commands.yaml"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "修改目标",
                "operations": [
                    {"action": "overwrite_text", "path": "tracked.txt", "content": "after\n"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return plan_file


def test_plan_file_apply_verify_commit_yes_creates_isolated_commit(tmp_path: Path) -> None:
    plan_file = prepare_cli_commit_repo(
        tmp_path,
        'python -c "print(\'ok\')"',
    )

    result = run_cli(
        tmp_path,
        "run",
        "修改目标",
        "--fake-response",
        "计划：修改目标。",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "fix: 修改目标",
        "--yes",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["git_commit"]["message"] == "fix: 修改目标"
    assert payload["git_commit"]["paths"] == ["tracked.txt"]
    assert len(payload["git_commit"]["sha"]) >= 40
    assert payload["commit_error"] is None
    assert payload["verification_passed"] is True


def test_fake_provider_plan_apply_verify_commit_yes_creates_commit(tmp_path: Path) -> None:
    prepare_cli_commit_repo(
        tmp_path,
        'python -c "print(\'ok\')"',
    )

    result = run_cli(
        tmp_path,
        "run",
        "创建 provider 文档",
        "--fake-response",
        strict_cli_plan(),
        "--use-provider-plan",
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "docs: 创建 provider 文档",
        "--yes",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["git_commit"]["paths"] == ["docs/cli-provider.md"]
    assert (tmp_path / "docs/cli-provider.md").read_text(encoding="utf-8") == "CLI 中文\n"
```

- [ ] **Step 3: 写入拒绝和验证失败退出码测试**

```python
def test_commit_without_yes_declines_before_apply_in_non_tty(tmp_path: Path) -> None:
    plan_file = prepare_cli_commit_repo(
        tmp_path,
        'python -c "print(\'ok\')"',
    )

    result = run_cli(
        tmp_path,
        "run",
        "修改",
        "--fake-response",
        "计划",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "fix: x",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "before\n"


def test_commit_verification_failure_returns_one_and_keeps_worktree(tmp_path: Path) -> None:
    plan_file = prepare_cli_commit_repo(
        tmp_path,
        'python -c "import sys; sys.exit(9)"',
    )

    result = run_cli(
        tmp_path,
        "run",
        "修改",
        "--fake-response",
        "计划",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "fix: x",
        "--yes",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["verification_passed"] is False
    assert payload["git_commit"] is None
    assert payload["commit_error"] is None
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "after\n"
```

再直接覆盖第二次确认和退出码映射：

```python
from io import StringIO
from types import SimpleNamespace

from dev_agent.cli import _confirm_commit, _result_exit_code
from dev_agent.git.models import GitCommitRequest


class InteractiveInput(StringIO):
    def isatty(self) -> bool:
        return True


def test_confirm_commit_reads_a_separate_answer_after_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", InteractiveInput("no\n"))

    accepted = _confirm_commit(
        Namespace(yes=False),
        GitCommitRequest("fix: x", ("tracked.txt",)),
        ("tracked.txt",),
    )

    assert accepted is False


def test_declined_commit_maps_to_exit_two() -> None:
    result = SimpleNamespace(
        commit_declined=True,
        execution_error=None,
        commit_error=None,
        verification_result=None,
    )
    assert _result_exit_code(result) == 2
```

- [ ] **Step 4: 注册参数并实现参数校验**

在 `build_parser()` 增加：

```python
    run_parser.add_argument("--commit", action="store_true")
    run_parser.add_argument("--commit-message")
```

新增并在 Provider 分流前调用：

```python
def _validate_commit_arguments(args: Namespace) -> None:
    if not args.commit:
        if args.commit_message is not None:
            raise ValueError("--commit-message 只能与 --commit 同时使用")
        return
    if not args.apply:
        raise ValueError("--commit 必须与 --apply 同时使用")
    if not args.verify:
        raise ValueError("--commit 必须与 --verify 同时使用")
    if args.commit_message is None:
        raise ValueError("--commit 必须提供 --commit-message")
    try:
        validate_commit_message(args.commit_message)
    except GitCommitPreflightError as exc:
        raise ValueError(str(exc)) from exc
```

- [ ] **Step 5: 实现第二次确认和 payload/退出码**

新增：

```python
def _confirm_commit(
    args: Namespace,
    request: GitCommitRequest,
    paths: tuple[str, ...],
) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    sys.stderr.write(
        "验证已通过。提交信息："
        + request.message
        + "；文件："
        + ", ".join(paths)
        + "。输入 yes 创建提交："
    )
    return sys.stdin.readline().strip() == "yes"
```

fake 和 OpenAI-compatible apply 调用的 `TaskRunOptions` 都增加：

```python
commit_request=(
    GitCommitRequest(args.commit_message) if args.commit else None
),
confirm_commit=(
    (lambda request, paths: _confirm_commit(args, request, paths))
    if args.commit
    else None
),
```

`_preview_payload()`、`_prepared_preview_payload()` 和 `_result_payload()` 增加：

```python
"git_commit": None if result.git_commit is None else result.git_commit.to_dict(),
"commit_error": result.commit_error,
```

preview 两个 helper 直接返回两个 `None`。统一退出码 helper：

```python
def _result_exit_code(result: TaskRunResult) -> int:
    if result.commit_declined:
        return 2
    if result.execution_error or result.commit_error:
        return 1
    if result.verification_result is not None and not result.verification_result.passed:
        return 1
    return 0
```

runner 抛出的 `GitCommitPreflightError` 在 fake/openai 两个入口写 stderr 并返回 `2`。非交互第二次拒绝由 JSON `git_commit: null`、`commit_error: null` 和退出码 `2` 表达。

- [ ] **Step 6: 运行 CLI 定向测试并确认 GREEN**

Run:

```powershell
python -m pytest tests/test_cli.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 CLI 契约**

```powershell
git add -- src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: expose controlled commit in cli"
```

### Task 7: 稳定 Web schema 并验证真实 Provider 单请求

**Files:**
- Modify: `src/dev_agent/web/api.py`
- Modify: `tests/test_web_api.py`
- Modify: `tests/test_web_server.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 写入 Web 空字段失败测试**

在 `tests/test_web_api.py` 的 dry-run、provider preview 和 provider apply 测试分别增加：

```python
assert payload["git_commit"] is None
assert payload["commit_error"] is None
```

在 `tests/test_web_server.py` 对 `/api/run`、`/api/provider-plan/preview` 和 `/api/provider-plan/apply` 响应增加相同断言，并发送额外 JSON 字段：

```python
"commit": True,
"commit_message": "不应执行",
```

断言响应仍只有 fake apply 行为，`git rev-list --count HEAD` 不变化；Web server 不解析这两个字段。

- [ ] **Step 2: 运行 Web 测试并确认 RED**

Run:

```powershell
python -m pytest tests/test_web_api.py tests/test_web_server.py -q
```

Expected: FAIL，payload 缺少 commit 字段。

- [ ] **Step 3: 给全部 Web 任务 payload 增加稳定空字段**

在 `_provider_plan_payload()` 和 `run_dry_run_task()` 的返回 dict 增加：

```python
"git_commit": None,
"commit_error": None,
```

不修改 `web/server.py` 的请求参数，不实例化 `GitCommitGuard`，不增加前端控件。

- [ ] **Step 4: 写入真实 Provider commit 单请求测试**

在 `tests/test_cli.py` 复用现有 `provider_server_factory()` 和 `write_provider_config()`，增加：

```python
def prepare_openai_commit_repo(
    tmp_path: Path,
    provider_server_factory: Callable,
    verification_command: str,
) -> tuple[Path, Path, CliProviderServer]:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    init_cli_git_repo(repo)
    track_cli_file(repo, "target.md", "旧值\n".encode("utf-8"))
    write_text_utf8(
        repo / ".agent" / "commands.yaml",
        f"test: {verification_command}\n",
    )
    subprocess.run(["git", "add", "--", ".agent/commands.yaml"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)
    response = json.dumps(replace_plan("target.md", "旧值", "新值"), ensure_ascii=False)
    server = provider_server_factory(response)
    write_provider_config(home, server.base_url)
    return repo, home, server


def test_openai_commit_reuses_one_response_and_creates_commit(
    tmp_path: Path,
    provider_server_factory: Callable,
) -> None:
    repo, home, server = prepare_openai_commit_repo(
        tmp_path,
        provider_server_factory,
        'python -c "print(\'ok\')"',
    )

    result = run_cli(
        repo,
        "run",
        "替换目标",
        "--provider",
        "openai-compatible",
        "--context-file",
        "target.md",
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "fix: 替换目标",
        "--yes",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "test-key"},
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert server.request_count == 1
    assert payload["provider_usage"]["request_count"] == 1
    assert payload["git_commit"]["paths"] == ["target.md"]
    assert (repo / "target.md").read_text(encoding="utf-8") == "新值\n"


def test_openai_commit_rejects_verifier_output_without_retry(
    tmp_path: Path,
    provider_server_factory: Callable,
) -> None:
    repo, home, server = prepare_openai_commit_repo(
        tmp_path,
        provider_server_factory,
        'python -c "from pathlib import Path; Path(\'coverage.tmp\').write_text(\'generated\', encoding=\'utf-8\')"',
    )
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.strip()

    result = run_cli(
        repo,
        "run",
        "替换目标",
        "--provider",
        "openai-compatible",
        "--context-file",
        "target.md",
        "--apply",
        "--verify",
        "--commit",
        "--commit-message",
        "fix: 替换目标",
        "--yes",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "test-key"},
    )

    payload = json.loads(result.stdout)
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert result.returncode == 1
    assert server.request_count == 1
    assert payload["git_commit"] is None
    assert "目标外 Git 状态发生变化" in payload["commit_error"]
    assert head_after == head_before
    assert (repo / "coverage.tmp").read_text(encoding="utf-8") == "generated"
    assert (repo / "target.md").read_text(encoding="utf-8") == "新值\n"
```

- [ ] **Step 5: 运行 Web 与真实 Provider 定向测试**

Run:

```powershell
python -m pytest tests/test_web_api.py tests/test_web_server.py tests/test_cli.py -q
```

Expected: PASS；所有 HTTP 只访问 `127.0.0.1`，无重试。

- [ ] **Step 6: 提交 Web schema 与单请求集成**

```powershell
git add -- src/dev_agent/web/api.py tests/test_web_api.py tests/test_web_server.py tests/test_cli.py
git commit -m "test: cover controlled commit entry points"
```

### Task 8: 完整回归、安全扫描和规格验收

**Files:**
- Modify only if a verification failure identifies a scoped defect in files already listed above.
- Verify: all Python source, tests, docs and Git history produced by Tasks 1-7.

- [ ] **Step 1: 核对 Git guard 边界矩阵测试名称**

Run:

```powershell
rg -n "^def test_(preflight|prepare_commit|commit|git_add|restore|post_validation|parse_porcelain|validate_commit_message)" tests/test_git_commit_guard.py
```

Expected: 输出中能逐项定位以下已经在 Tasks 1-4 写明的测试：

```text
dirty target: staged / unstaged / untracked
ignored create
unborn / detached HEAD
merge / rebase-apply / rebase-merge / cherry-pick / revert / bisect
unrelated staged / unstaged / untracked preserved
HEAD / branch / operation-state drift
verifier-created outside file
empty target diff
single and multiple changed targets
git add / hook / commit failure cleanup
parent / message / exact path-set post-validation
absolute-path / secret / long-hook-output redaction
spaces / Chinese / rename porcelain records
```

如果命令没有列出上述任一已规划测试，停止验收并返回对应 Task 完成该测试，不在本步骤引入新的生产行为。

- [ ] **Step 2: 运行 Git、runner、CLI 和 Web 分层测试**

Run:

```powershell
python -m pytest tests/test_git_commit_guard.py -q
python -m pytest tests/test_runtime_runner.py -q
python -m pytest tests/test_cli.py -q
python -m pytest tests/test_web_api.py tests/test_web_server.py -q
```

Expected: 每条命令 PASS；真实 Provider 回环测试的 `request_count == 1`。

- [ ] **Step 3: 运行完整自动化测试**

Run:

```powershell
python -m pytest -q
```

Expected: 全部 PASS，现有基线 `310 passed, 1 skipped` 只因新增测试增加通过数量，不出现原有测试回归。

- [ ] **Step 4: 运行服务启动检查**

Run:

```powershell
python -m dev_agent.cli serve --host 127.0.0.1 --port 0 --check
```

Expected: exit `0`，JSON 中 `ok: true` 且 URL 为 `http://127.0.0.1:<动态端口>/`。

- [ ] **Step 5: 检查 UTF-8、Diff 和敏感信息**

Run:

```powershell
git diff --check
$files = git diff --name-only master...HEAD | Where-Object { $_ -match '\.(py|md|js|css|html)$' }
$strict = [System.Text.UTF8Encoding]::new($false, $true)
foreach ($file in $files) { $null = $strict.GetString([System.IO.File]::ReadAllBytes((Resolve-Path $file))) }
rg -n "sk-[A-Za-z0-9]|Authorization:\s*Bearer|api_key\s*=\s*[^<]" src tests
```

Expected: `git diff --check` 无输出；全部文本严格 UTF-8 解码；扫描只命中明确的脱敏测试 fixture，不在生产代码中出现真实密钥或未脱敏输出。

- [ ] **Step 6: 检查最终范围**

Run:

```powershell
git diff --stat master...HEAD
git log --oneline master..HEAD
rg -n "git push|--amend|git merge|commit-tree|GIT_INDEX_FILE" src/dev_agent
```

Expected: 变更只涉及计划列出的 Git guard、runtime、CLI、Web payload 和测试；生产代码不包含 push、merge、amend、临时 index 或 tree plumbing；提交历史按 Task 1-7 分层清晰。

- [ ] **Step 7: 创建最终验收提交（仅在 Step 1 补充过代码或测试时）**

```powershell
git add -- src/dev_agent tests
git commit -m "test: complete controlled commit safety coverage"
```

若 Step 1 未产生任何变更，不创建空提交。
