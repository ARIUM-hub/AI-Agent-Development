from pathlib import Path
import subprocess

import pytest

from dev_agent.git.commit_guard import parse_porcelain_v1_z, validate_commit_message
from dev_agent.git.models import GitCommitPreflightError, GitStatusEntry
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.git.commit_guard import GitCommitGuard
from dev_agent.verification.planner import VerificationPlan, VerificationStep


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


def verification_plan() -> VerificationPlan:
    return VerificationPlan([VerificationStep("test", ["python", "-c", "print('ok')"])])


def overwrite_plan() -> ExecutionPlan:
    return ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "tracked.txt", "changed\n")])


def test_preflight_accepts_unrelated_staged_and_untracked_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "other.txt").write_text("other\n", encoding="utf-8")
    git(tmp_path, "add", "--", "other.txt")
    (tmp_path / "notes.tmp").write_text("note\n", encoding="utf-8")
    snapshot = GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())
    assert snapshot.target_paths == ("tracked.txt",)
    assert {entry.path for entry in snapshot.status_entries} == {"other.txt", "notes.tmp"}


@pytest.mark.parametrize("mode", ["unstaged", "staged"])
def test_preflight_rejects_dirty_target(tmp_path: Path, mode: str) -> None:
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    if mode == "staged":
        git(tmp_path, "add", "--", "tracked.txt")
    with pytest.raises(GitCommitPreflightError, match="目标路径在运行前必须干净"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())


@pytest.mark.parametrize("ignored", [False, True])
def test_preflight_rejects_untracked_or_ignored_create(tmp_path: Path, ignored: bool) -> None:
    init_repo(tmp_path)
    if ignored:
        (tmp_path / ".gitignore").write_text("new.txt\n", encoding="utf-8")
        git(tmp_path, "add", "--", ".gitignore")
        git(tmp_path, "commit", "-qm", "ignore")
    else:
        (tmp_path / "new.txt").write_text("existing\n", encoding="utf-8")
    plan = ExecutionPlan("创建", [ExecutionOperation("create_text", "new.txt", "new\n")])
    with pytest.raises(GitCommitPreflightError):
        GitCommitGuard(tmp_path).preflight(plan, verification_plan())


def test_preflight_rejects_empty_verification_plan(tmp_path: Path) -> None:
    init_repo(tmp_path)
    with pytest.raises(GitCommitPreflightError, match="至少需要一条验证命令"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), VerificationPlan([]))


def test_preflight_rejects_detached_and_unborn_head(tmp_path: Path) -> None:
    init_repo(tmp_path)
    git(tmp_path, "checkout", "--detach", "-q")
    with pytest.raises(GitCommitPreflightError, match="detached HEAD"):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    git(unborn, "init", "-q")
    with pytest.raises(GitCommitPreflightError, match="HEAD 尚无提交"):
        GitCommitGuard(unborn).preflight(
            ExecutionPlan("创建", [ExecutionOperation("create_text", "new.txt", "x")]),
            verification_plan(),
        )


@pytest.mark.parametrize(
    ("marker", "label", "directory"),
    [("MERGE_HEAD", "merge", False), ("rebase-apply", "rebase", True),
     ("rebase-merge", "rebase", True), ("CHERRY_PICK_HEAD", "cherry-pick", False),
     ("REVERT_HEAD", "revert", False), ("BISECT_LOG", "bisect", False)],
)
def test_preflight_rejects_git_operation_in_progress(
    tmp_path: Path, marker: str, label: str, directory: bool
) -> None:
    init_repo(tmp_path)
    path = Path(git(tmp_path, "rev-parse", "--git-path", marker).stdout.strip())
    if not path.is_absolute():
        path = tmp_path / path
    if directory:
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("in progress\n", encoding="utf-8")
    with pytest.raises(GitCommitPreflightError, match=label):
        GitCommitGuard(tmp_path).preflight(overwrite_plan(), verification_plan())
