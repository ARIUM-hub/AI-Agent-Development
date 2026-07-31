from pathlib import Path

from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError
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
from dev_agent.tools.git import GitReader
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
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "provider_completed")
        events = [*task.events]
        verification_result = None
        execution_result = ExecutionResult(applied=False, planned_changes=[])
        execution_error = None
        try:
            execution_result = self._execution_preview(options)
            if options.apply_changes:
                expected_fingerprint = (
                    options.expected_preview_fingerprint
                    or execution_result.preview_fingerprint
                )
                execution_result = self._apply_execution_plan(
                    options,
                    expected_fingerprint,
                )
                task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "execution_completed")
                events = [*task.events]
        except ExecutionPlanError as exc:
            execution_error = str(exc)
            task = update_task_status(self.repo_root, task.task_id, TaskStatus.FAILED, "execution_failed")
            self._record_history(
                task_id=task.task_id,
                title=user_request,
                status=task.status.value,
                summary=f"{response.text}\n\n执行失败：{execution_error}",
                events=task.events,
                verification=[" ".join(step.command) for step in context.verification_plan.steps],
            )
            return TaskRunResult(
                task_id=task.task_id,
                plan_text=response.text,
                dry_run=options.dry_run,
                memory_hit_count=len(context.memory_hits),
                verification_steps=[step.command for step in context.verification_plan.steps],
                events=task.events,
                planned_changes=execution_result.planned_changes,
                applied_changes=execution_result.changes_as_dicts(),
                diff_stat=execution_result.diff_stat,
                execution_error=execution_error,
                file_diffs=execution_result.file_diffs_as_dicts(),
                preview_fingerprint=execution_result.preview_fingerprint,
            )
        if options.run_verification:
            verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
            task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "verification_completed")
            events = [*task.events]
        final_status = TaskStatus.PASSED if verification_result is None or verification_result.passed else TaskStatus.FAILED
        task = update_task_status(self.repo_root, task.task_id, final_status, "runtime_completed")
        summary = self._build_summary(response.text, execution_result)
        self._record_history(
            task_id=task.task_id,
            title=user_request,
            status=task.status.value,
            summary=summary,
            events=task.events,
            verification=[" ".join(step.command) for step in context.verification_plan.steps],
        )
        return TaskRunResult(
            task_id=task.task_id,
            plan_text=response.text,
            dry_run=options.dry_run,
            memory_hit_count=len(context.memory_hits),
            verification_steps=[step.command for step in context.verification_plan.steps],
            verification_result=verification_result,
            events=task.events,
            planned_changes=execution_result.planned_changes,
            applied_changes=execution_result.changes_as_dicts(),
            diff_stat=execution_result.diff_stat,
            execution_error=execution_error,
            file_diffs=execution_result.file_diffs_as_dicts(),
            preview_fingerprint=execution_result.preview_fingerprint,
        )

    def _execution_preview(self, options: TaskRunOptions) -> ExecutionResult:
        if options.execution_plan is None:
            return ExecutionResult(applied=False, planned_changes=[])
        return ExecutionPlanApplier(self.repo_root).preview(options.execution_plan)

    def _apply_execution_plan(
        self,
        options: TaskRunOptions,
        expected_fingerprint: str,
    ) -> ExecutionResult:
        if options.execution_plan is None:
            raise ExecutionPlanError("execution_plan is required when apply_changes is true")
        return ExecutionPlanApplier(self.repo_root).apply(
            options.execution_plan,
            expected_fingerprint=expected_fingerprint,
        )

    def _build_summary(self, plan_text: str, execution_result: ExecutionResult) -> str:
        if not execution_result.applied:
            return plan_text
        changed_paths = ", ".join(change.path for change in execution_result.changes)
        diff_stat = execution_result.diff_stat or GitReader(self.repo_root).snapshot().diff_stat
        return f"{plan_text}\n\n已应用文件：{changed_paths}\n\nDiff stat:\n{diff_stat}"

    def _record_history(
        self,
        task_id: str,
        title: str,
        status: str,
        summary: str,
        events: list[str],
        verification: list[str],
    ) -> None:
        store = MemoryStore(self.repo_root)
        record = TaskRecord(
            task_id=task_id,
            title=title,
            status=status,
            summary=summary,
            events=events,
            verification=verification,
            lessons=[summary],
        )
        store.append_task(record)
        for experience in extract_experiences(record):
            store.append_experience(experience)
