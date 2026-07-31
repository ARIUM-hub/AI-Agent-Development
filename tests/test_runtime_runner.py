from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.encoding import write_text_utf8
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.memory.store import MemoryStore
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import RuntimeContext
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.prompts import build_task_prompt
from dev_agent.runtime.runner import LocalTaskRunner
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
    assert result.file_diffs == []
    assert result.preview_fingerprint == ""
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
    assert result.file_diffs[0]["path"] == "docs/execution.md"
    assert result.file_diffs[0]["status"] == "added"
    assert result.preview_fingerprint.startswith("sha256:")
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
