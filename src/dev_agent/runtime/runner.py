from pathlib import Path

from dev_agent.memory.extract import extract_experiences
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.providers.base import ModelProvider
from dev_agent.providers.budget import BudgetConfig, CircuitBreaker, ProtectedProvider
from dev_agent.providers.models import ModelRequest
from dev_agent.runtime.context import resolve_runtime_context
from dev_agent.runtime.models import TaskRunOptions, TaskRunResult
from dev_agent.runtime.prompts import build_task_prompt
from dev_agent.tasks.state import TaskStatus, create_task, update_task_status
from dev_agent.verification.runner import VerificationRunner


class LocalTaskRunner:
    def __init__(self, repo_root: Path, home_dir: Path, provider: ModelProvider) -> None:
        self.repo_root = repo_root
        self.home_dir = home_dir
        self.provider = ProtectedProvider(provider, CircuitBreaker(BudgetConfig()))

    def run(self, user_request: str, options: TaskRunOptions) -> TaskRunResult:
        task = create_task(self.repo_root, user_request)
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "runtime_started")
        context = resolve_runtime_context(self.repo_root, self.home_dir, user_request)
        prompt = build_task_prompt(context)
        response = self.provider.complete(ModelRequest(prompt=prompt, task_id=task.task_id))
        events = [*task.events, "provider_completed"]
        verification_result = None
        if options.run_verification:
            verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
            events.append("verification_completed")
        final_status = TaskStatus.PASSED if verification_result is None or verification_result.passed else TaskStatus.FAILED
        task = update_task_status(self.repo_root, task.task_id, final_status, events[-1])

        store = MemoryStore(self.repo_root)
        record = TaskRecord(
            task_id=task.task_id,
            title=user_request,
            status=task.status.value,
            summary=response.text,
            events=task.events,
            verification=[" ".join(step.command) for step in context.verification_plan.steps],
            lessons=[response.text],
        )
        store.append_task(record)
        for experience in extract_experiences(record):
            store.append_experience(experience)

        return TaskRunResult(
            task_id=task.task_id,
            plan_text=response.text,
            dry_run=options.dry_run,
            memory_hit_count=len(context.memory_hits),
            verification_steps=[step.command for step in context.verification_plan.steps],
            verification_result=verification_result,
            events=task.events,
        )
