from pathlib import Path

from dev_agent.config.loader import load_agent_context
from dev_agent.memory.retriever import MemoryRetriever
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.runtime.models import RuntimeContext
from dev_agent.tools.git import GitReader
from dev_agent.verification.planner import build_verification_plan


def resolve_runtime_context(repo_root: Path, home_dir: Path, user_request: str) -> RuntimeContext:
    agent_context = load_agent_context(repo_root, home_dir)
    scan = scan_project(repo_root)
    git = GitReader(repo_root).snapshot()
    memory_store = MemoryStore(repo_root)
    memory_hits = MemoryRetriever(
        memory_store.list_tasks(),
        memory_store.list_experiences(),
    ).search(user_request)
    verification_plan = build_verification_plan(agent_context.commands, scan)
    return RuntimeContext(
        user_request=user_request,
        project=agent_context.project,
        preferences=agent_context.preferences,
        rules_text=agent_context.rules_text,
        scan=scan,
        git=git,
        memory_hits=memory_hits,
        verification_plan=verification_plan,
    )
