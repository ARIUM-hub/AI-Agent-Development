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
