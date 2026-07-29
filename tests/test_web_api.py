import subprocess

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.web.api import build_context_payload, build_health_payload, build_history_payload, run_dry_run_task


def git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_build_health_payload_reports_local_web_capability(tmp_path) -> None:
    payload = build_health_payload(tmp_path)

    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"
    assert payload["cwd"] == str(tmp_path)
    assert payload["capabilities"]["web_console"] is True
    assert payload["capabilities"]["dry_run_only"] is True


def test_build_context_payload_combines_scan_git_rules_and_verification(tmp_path) -> None:
    write_text_utf8(tmp_path / ".agent" / "rules.md", "# 项目规则\n\n所有文件使用 UTF-8。\n")
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    write_text_utf8(tmp_path / "README.md", "# 示例\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "initial")

    payload = build_context_payload(tmp_path, tmp_path)

    assert payload["scan"]["languages"] == ["python"]
    assert payload["git"]["recent_log"]
    assert payload["rules_text"] == "# 项目规则\n\n所有文件使用 UTF-8。\n"
    assert payload["verification_steps"] == [{"name": "test", "command": ["python", "-m", "pytest"]}]


def test_build_history_payload_lists_tasks(tmp_path) -> None:
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-1",
            title="实现 Web 控制台",
            status="passed",
            summary="已完成 dry-run 页面",
        )
    )

    payload = build_history_payload(tmp_path)

    assert payload["tasks"][0]["task_id"] == "task-1"
    assert payload["tasks"][0]["title"] == "实现 Web 控制台"


def test_run_dry_run_task_requires_fake_response_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = run_dry_run_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="生成实现计划",
        fake_response="计划：先看上下文，再跑测试。",
    )

    assert payload["plan_text"] == "计划：先看上下文，再跑测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "生成实现计划" in history


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
