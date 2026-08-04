from pathlib import Path
import json
import subprocess

import pytest

from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.encoding import write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.memory.store import MemoryStore
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.providers.base import FakeProvider
from dev_agent.providers.models import ModelResponse, ProviderUsage
from dev_agent.runtime.models import RuntimeContext
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.prompts import build_task_prompt
from dev_agent.runtime.runner import LocalTaskRunner
from dev_agent.tools.git import GitSnapshot
from dev_agent.verification.planner import VerificationPlan, VerificationStep
from dev_agent.git.models import GitCommitRequest
from dev_agent.git.models import GitCommitPreflightError


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


class FailingProvider:
    name = "must-not-run"

    def complete(self, request):
        raise AssertionError("prepared apply must not call provider")


def prepared_response() -> ModelResponse:
    return ModelResponse(
        provider="openai-compatible",
        text='{"summary":"创建说明","operations":[]}',
        usage=ProviderUsage(request_count=1, input_chars=120, output_chars=80),
    )


def test_local_task_runner_reuses_prepared_response_without_provider_call(
    tmp_path: Path,
) -> None:
    plan = ExecutionPlan(
        summary="创建说明",
        operations=[
            ExecutionOperation(
                "create_text",
                "docs/reused.md",
                "复用响应\n",
            )
        ],
    )
    preview = ExecutionPlanApplier(tmp_path).preview(plan)
    runner = LocalTaskRunner(tmp_path, tmp_path, FailingProvider())

    result = runner.run(
        "创建说明",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            prepared_response=prepared_response(),
            provider_model="model-name",
        ),
    )

    assert (
        tmp_path / "docs" / "reused.md"
    ).read_text(encoding="utf-8") == "复用响应\n"
    assert result.provider == "openai-compatible"
    assert result.model == "model-name"
    assert result.provider_usage == ProviderUsage(1, 120, 80)
    assert "provider_completed" in result.events


def test_prepared_response_keeps_stale_preview_protection(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "README.md", "before\n")
    plan = ExecutionPlan(
        "覆盖",
        [ExecutionOperation("overwrite_text", "README.md", "after\n")],
    )
    fingerprint = ExecutionPlanApplier(tmp_path).preview(plan).preview_fingerprint
    write_text_utf8(tmp_path / "README.md", "changed after preview\n")
    runner = LocalTaskRunner(tmp_path, tmp_path, FailingProvider())

    result = runner.run(
        "覆盖 README",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=fingerprint,
            prepared_response=prepared_response(),
            provider_model="model-name",
        ),
    )

    assert "文件状态已变化" in (result.execution_error or "")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == (
        "changed after preview\n"
    )
    assert result.provider == "openai-compatible"
    assert result.provider_usage.request_count == 1
    assert MemoryStore(tmp_path).list_tasks()[-1].status == "failed"


def test_runner_uses_history_plan_text_but_returns_original_response(
    tmp_path: Path,
) -> None:
    write_text_utf8(tmp_path / "target.md", "OLD_SOURCE_MARKER\n")
    response = ModelResponse(
        provider="openai-compatible",
        text="RAW_PROVIDER_BODY_MARKER",
        usage=ProviderUsage(1, 10, 10),
    )
    plan = ExecutionPlan(
        "替换",
        [
            ExecutionOperation(
                action="replace_text",
                path="target.md",
                old_text="OLD_SOURCE_MARKER",
                new_text="NEW_SOURCE_MARKER",
            )
        ],
    )
    preview = ExecutionPlanApplier(tmp_path).preview(plan)

    result = LocalTaskRunner(tmp_path, tmp_path, FailingProvider()).run(
        "替换",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            prepared_response=response,
            history_plan_text="SANITIZED_HISTORY_MARKER",
        ),
    )

    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(
        encoding="utf-8"
    )
    assert result.plan_text == "RAW_PROVIDER_BODY_MARKER"
    assert "SANITIZED_HISTORY_MARKER" in history
    assert "RAW_PROVIDER_BODY_MARKER" not in history
    assert "OLD_SOURCE_MARKER" not in history
    assert "NEW_SOURCE_MARKER" not in history


def test_runner_uses_history_plan_text_for_execution_failure(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "target.md", "prefix OLD_FAILURE_MARKER\n")
    plan = ExecutionPlan(
        "替换",
        [
            ExecutionOperation(
                action="replace_text",
                path="target.md",
                old_text="OLD_FAILURE_MARKER",
                new_text="NEW_FAILURE_MARKER",
            )
        ],
    )
    approved_fingerprint = ExecutionPlanApplier(tmp_path).preview(
        plan
    ).preview_fingerprint
    write_text_utf8(
        tmp_path / "target.md",
        "prefix OLD_FAILURE_MARKER\nexternal change\n",
    )

    result = LocalTaskRunner(tmp_path, tmp_path, FailingProvider()).run(
        "替换失败",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=approved_fingerprint,
            prepared_response=prepared_response(),
            history_plan_text="SANITIZED_FAILURE_MARKER",
        ),
    )

    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(
        encoding="utf-8"
    )
    assert result.execution_error is not None
    assert "SANITIZED_FAILURE_MARKER" in history
    assert "OLD_FAILURE_MARKER" not in history
    assert "NEW_FAILURE_MARKER" not in history


def _init_commit_repo(repo: Path, command: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.invalid"], cwd=repo, check=True)
    write_text_utf8(repo / "target.txt", "before\n")
    write_text_utf8(repo / ".agent" / "commands.yaml", f"test: {command}\n")
    subprocess.run(["git", "add", "--", "target.txt", ".agent/commands.yaml"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)


def test_runner_commits_after_verification_and_freezes_audit(tmp_path: Path) -> None:
    _init_commit_repo(tmp_path, 'python -c "print(\'ok\')"')
    plan = ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "target.txt", "after\n")])
    preview = ExecutionPlanApplier(tmp_path).preview(plan)

    def confirm(_request: GitCommitRequest, paths: tuple[str, ...]) -> bool:
        task_file = next((tmp_path / ".agent" / "tasks").glob("*.json"))
        assert json.loads(task_file.read_text(encoding="utf-8"))["events"][-1] == "provider_completed"
        assert not (tmp_path / ".agent" / "history" / "tasks.jsonl").exists()
        assert paths == ("target.txt",)
        return True

    result = LocalTaskRunner(tmp_path, tmp_path, FakeProvider("fake", ["计划"])).run(
        "修改",
        TaskRunOptions(
            apply_changes=True,
            run_verification=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            commit_request=GitCommitRequest("fix: 修改"),
            confirm_commit=confirm,
        ),
    )
    assert result.git_commit is not None
    assert result.git_commit.paths == ("target.txt",)
    assert result.commit_error is None
    assert "commit_completed" in result.events


def test_runner_skips_commit_when_verification_fails(tmp_path: Path) -> None:
    _init_commit_repo(tmp_path, 'python -c "import sys; sys.exit(7)"')
    plan = ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "target.txt", "after\n")])
    preview = ExecutionPlanApplier(tmp_path).preview(plan)
    calls = 0

    def confirm(_request: GitCommitRequest, _paths: tuple[str, ...]) -> bool:
        nonlocal calls
        calls += 1
        return True

    result = LocalTaskRunner(tmp_path, tmp_path, FakeProvider("fake", ["计划"])).run(
        "修改",
        TaskRunOptions(apply_changes=True, run_verification=True, execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            commit_request=GitCommitRequest("fix: 不提交"), confirm_commit=confirm),
    )
    assert calls == 0
    assert result.verification_result is not None and not result.verification_result.passed
    assert result.git_commit is None


def test_runner_records_commit_preflight_failure_history(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.invalid"], cwd=tmp_path, check=True)
    write_text_utf8(tmp_path / "target.txt", "before\n")
    subprocess.run(["git", "add", "--", "target.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    plan = ExecutionPlan("修改", [ExecutionOperation("overwrite_text", "target.txt", "after\n")])

    with pytest.raises(GitCommitPreflightError, match="至少需要一条验证命令"):
        LocalTaskRunner(tmp_path, tmp_path, FakeProvider("fake", ["计划"])).run(
            "修改",
            TaskRunOptions(apply_changes=True, run_verification=True, execution_plan=plan,
                commit_request=GitCommitRequest("fix: 修改"),
                confirm_commit=lambda _request, _paths: True),
        )

    history = MemoryStore(tmp_path).list_tasks()
    assert history[-1].status == "failed"
    assert "提交预检失败" in history[-1].summary
