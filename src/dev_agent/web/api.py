from pathlib import Path

from dev_agent import __version__
from dev_agent.config.loader import load_agent_context
from dev_agent.encoding import UTF8
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
            "dry_run_only": True,
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


def run_dry_run_task(repo_root: Path, home_dir: Path, request_text: str, fake_response: str) -> dict[str, object]:
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
        TaskRunOptions(dry_run=True, run_verification=False),
    )
    return {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "events": result.events,
    }
