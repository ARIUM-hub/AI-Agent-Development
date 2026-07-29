from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.runtime.models import RuntimeContext
from dev_agent.runtime.prompts import build_task_prompt
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
