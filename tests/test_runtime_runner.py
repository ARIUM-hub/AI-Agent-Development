from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.encoding import write_text_utf8
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
