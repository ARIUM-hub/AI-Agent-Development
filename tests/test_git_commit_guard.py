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
