from pathlib import Path

from dev_agent import __version__
from dev_agent.config.loader import load_agent_context
from dev_agent.encoding import UTF8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError, StaleExecutionPreviewError
from dev_agent.execution.provider_plan import parse_provider_execution_plan
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.runner import LocalTaskRunner
from dev_agent.tools.git import GitReader
from dev_agent.verification.planner import build_verification_plan


def build_health_payload(repo_root: Path) -> dict[str, object]:
    return {
        "ok": True,
        "version": __version__,
        "cwd": str(repo_root),
        "encoding": UTF8,
        "capabilities": {
            "web_console": True,
            "dry_run_only": False,
            "provider_plan_preview": True,
            "provider_plan_apply": True,
            "real_model_calls": False,
        },
    }


def build_context_payload(repo_root: Path, home_dir: Path) -> dict[str, object]:
    agent_context = load_agent_context(repo_root, home_dir)
    scan = scan_project(repo_root)
    git = GitReader(repo_root).snapshot()
    verification_plan = build_verification_plan(agent_context.commands, scan)
    return {
        "project": {
            "name": agent_context.project.name,
            "tech_stack": agent_context.project.tech_stack,
        },
        "preferences": {
            "language": agent_context.preferences.language,
            "approval_mode": agent_context.preferences.approval_mode,
        },
        "rules_text": agent_context.rules_text,
        "scan": {
            "root": str(scan.root),
            "languages": scan.languages,
            "markers": scan.markers,
            "suggested_commands": {
                "test": scan.suggested_commands.test,
                "lint": scan.suggested_commands.lint,
                "typecheck": scan.suggested_commands.typecheck,
                "build": scan.suggested_commands.build,
            },
        },
        "git": {
            "status": git.status,
            "diff_stat": git.diff_stat,
            "recent_log": git.recent_log,
        },
        "verification_steps": [
            {"name": step.name, "command": step.command}
            for step in verification_plan.steps
        ],
    }


def build_history_payload(repo_root: Path) -> dict[str, object]:
    tasks = MemoryStore(repo_root).list_tasks()
    return {"tasks": [task.to_dict() for task in tasks]}


def _planned_changes(plan: ExecutionPlan) -> list[dict[str, object]]:
    return [operation.to_dict() for operation in plan.operations]


def _provider_preview(repo_root: Path, fake_response: str) -> tuple[ExecutionPlan, ExecutionResult]:
    try:
        plan = parse_provider_execution_plan(fake_response)
        preview = ExecutionPlanApplier(repo_root).preview(plan)
    except ExecutionPlanError as exc:
        message = str(exc)
        if message.startswith("无法解析 provider 执行计划"):
            raise ValueError(message) from exc
        raise ValueError(f"执行计划预览失败：{message}") from exc
    return plan, preview


def _provider_plan_payload(
    *,
    ok: bool,
    task_id: str | None,
    plan_text: str,
    dry_run: bool,
    planned_changes: list[dict[str, object]],
    preview_result: ExecutionResult,
    applied_changes: list[dict[str, object]] | None = None,
    diff_stat: str = "",
    execution_error: str | None = None,
) -> dict[str, object]:
    return {
        "ok": ok,
        "task_id": task_id,
        "plan_text": plan_text,
        "dry_run": dry_run,
        "planned_changes": planned_changes,
        "preview_changes": preview_result.preview_changes_as_dicts(),
        "applied_changes": applied_changes or [],
        "diff_stat": diff_stat,
        "execution_error": execution_error,
        "file_diffs": preview_result.file_diffs_as_dicts(),
        "preview_fingerprint": preview_result.preview_fingerprint,
    }


def preview_provider_plan_task(repo_root: Path, request_text: str, fake_response: str) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for provider plan preview")
    plan, preview = _provider_preview(repo_root, fake_response)
    return _provider_plan_payload(
        ok=True,
        task_id=None,
        plan_text="",
        dry_run=True,
        planned_changes=_planned_changes(plan),
        preview_result=preview,
    )


def apply_provider_plan_task(
    repo_root: Path,
    home_dir: Path,
    request_text: str,
    fake_response: str,
    preview_fingerprint: str,
) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for provider plan apply")
    if not preview_fingerprint.strip():
        raise ValueError("preview_fingerprint is required")
    plan, preview = _provider_preview(repo_root, fake_response)
    if preview.preview_fingerprint != preview_fingerprint:
        raise StaleExecutionPreviewError("文件状态已变化，请重新预览后再执行")
    runner = LocalTaskRunner(
        repo_root=repo_root,
        home_dir=home_dir,
        provider=FakeProvider(name="fake-web-provider-plan", responses=[fake_response]),
    )
    result = runner.run(
        request_text,
        TaskRunOptions(
            dry_run=False,
            run_verification=False,
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview_fingerprint,
        ),
    )
    return _provider_plan_payload(
        ok=True,
        task_id=result.task_id,
        plan_text=result.plan_text,
        dry_run=result.dry_run,
        planned_changes=result.planned_changes,
        preview_result=preview,
        applied_changes=result.applied_changes,
        diff_stat=result.diff_stat,
        execution_error=result.execution_error,
    )


def run_dry_run_task(
    repo_root: Path,
    home_dir: Path,
    request_text: str,
    fake_response: str,
    execution_plan_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for Web dry-run")
    runner = LocalTaskRunner(
        repo_root=repo_root,
        home_dir=home_dir,
        provider=FakeProvider(name="fake-web", responses=[fake_response]),
    )
    result = runner.run(
        request_text,
        TaskRunOptions(dry_run=True, run_verification=False, apply_changes=False),
    )
    return {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "events": result.events,
        "planned_changes": [],
        "applied_changes": [],
        "diff_stat": "",
        "execution_error": None,
        "file_diffs": [],
        "preview_fingerprint": "",
    }
