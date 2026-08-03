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
