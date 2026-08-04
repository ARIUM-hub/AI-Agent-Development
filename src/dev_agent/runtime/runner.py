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
from dev_agent.git.commit_guard import GitCommitGuard
from dev_agent.git.models import (
    GitCommitCommandError,
    GitCommitPreflightError,
    GitCommitRejectedError,
    GitCommitRequest,
)
from dev_agent.tasks.state import TaskState


class LocalTaskRunner:
    def __init__(self, repo_root: Path, home_dir: Path, provider: ModelProvider) -> None:
        self.repo_root = repo_root
        self.home_dir = home_dir
        self.provider = ProtectedProvider(provider, CircuitBreaker(BudgetConfig()))

    def run(self, user_request: str, options: TaskRunOptions) -> TaskRunResult:
        task = create_task(self.repo_root, user_request)
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "runtime_started")
        context = resolve_runtime_context(self.repo_root, self.home_dir, user_request)
        if options.prepared_response is None:
            prompt = build_task_prompt(context)
            response = self.provider.complete(
                ModelRequest(prompt=prompt, task_id=task.task_id)
            )
        else:
            response = options.prepared_response
        history_plan_text = (
            response.text
            if options.history_plan_text is None
            else options.history_plan_text
        )
        task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "provider_completed")
        if options.commit_request is not None:
            return self._run_guarded_commit(
                task, context, response, history_plan_text, user_request, options
            )
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
                summary=f"{history_plan_text}\n\n执行失败：{execution_error}",
                events=task.events,
                verification=[" ".join(step.command) for step in context.verification_plan.steps],
            )
            return TaskRunResult(
                task_id=task.task_id,
                plan_text=response.text,
                dry_run=options.dry_run,
                memory_hit_count=len(context.memory_hits),
                verification_steps=[step.command for step in context.verification_plan.steps],
                provider=response.provider,
                model=options.provider_model,
                provider_usage=response.usage,
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
        summary = self._build_summary(history_plan_text, execution_result)
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
            provider=response.provider,
            model=options.provider_model,
            provider_usage=response.usage,
            verification_result=verification_result,
            events=task.events,
            planned_changes=execution_result.planned_changes,
            applied_changes=execution_result.changes_as_dicts(),
            diff_stat=execution_result.diff_stat,
            execution_error=execution_error,
            file_diffs=execution_result.file_diffs_as_dicts(),
            preview_fingerprint=execution_result.preview_fingerprint,
        )

    def _run_guarded_commit(
        self, task: TaskState, context, response, history_plan_text: str,
        user_request: str, options: TaskRunOptions,
    ) -> TaskRunResult:
        if options.execution_plan is None or options.confirm_commit is None:
            raise GitCommitPreflightError("受控提交需要执行计划和提交确认回调")
        guard = GitCommitGuard(self.repo_root)
        try:
            snapshot = guard.preflight(options.execution_plan, context.verification_plan)
        except GitCommitPreflightError:
            update_task_status(self.repo_root, task.task_id, TaskStatus.FAILED, "commit_rejected")
            raise
        queued = ["commit_preflight_completed"]
        execution_result = ExecutionResult(applied=False, planned_changes=[])
        execution_error = None
        verification_result = None
        git_commit = None
        commit_error = None
        declined = False
        try:
            preview = self._execution_preview(options)
            expected = options.expected_preview_fingerprint or preview.preview_fingerprint
            execution_result = self._apply_execution_plan(options, expected)
            queued.append("execution_completed")
        except ExecutionPlanError as exc:
            execution_error = str(exc)
            queued.append("execution_failed")
        if execution_error is None:
            verification_result = VerificationRunner(self.repo_root).run(context.verification_plan)
            queued.append("verification_completed")
            if verification_result.passed:
                try:
                    paths = guard.prepare_commit(snapshot)
                    request = GitCommitRequest(options.commit_request.message, snapshot.target_paths)
                    if options.confirm_commit(request, paths):
                        git_commit = guard.commit(snapshot, request.message, paths)
                        queued.append("commit_completed")
                    else:
                        declined = True
                        queued.append("commit_rejected")
                except GitCommitRejectedError as exc:
                    commit_error = str(exc)
                    queued.append("commit_rejected")
                except GitCommitCommandError as exc:
                    commit_error = str(exc)
                    queued.append("commit_failed")
        if execution_error or commit_error or (verification_result and not verification_result.passed):
            status = TaskStatus.FAILED
        elif declined:
            status = TaskStatus.BLOCKED
        else:
            status = TaskStatus.PASSED
        for event in queued:
            task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, event)
        task = update_task_status(self.repo_root, task.task_id, status, "runtime_completed")
        summary = self._build_summary(history_plan_text, execution_result)
        if git_commit:
            summary += f"\n\nGit commit: {git_commit.sha}\nMessage: {git_commit.message}\nPaths: " + ", ".join(git_commit.paths)
        elif commit_error:
            summary += "\n\n提交失败：" + commit_error
        elif declined:
            summary += "\n\n用户拒绝创建 Git 提交。"
        else:
            summary += "\n\n验证失败，未创建 Git 提交。"
        self._record_history(task.task_id, user_request, task.status.value, summary,
            task.events, [" ".join(step.command) for step in context.verification_plan.steps])
        return TaskRunResult(
            task_id=task.task_id, plan_text=response.text, dry_run=options.dry_run,
            memory_hit_count=len(context.memory_hits),
            verification_steps=[step.command for step in context.verification_plan.steps],
            provider=response.provider, model=options.provider_model,
            provider_usage=response.usage, verification_result=verification_result,
            events=task.events, planned_changes=execution_result.planned_changes,
            applied_changes=execution_result.changes_as_dicts(),
            diff_stat=execution_result.diff_stat, execution_error=execution_error,
            file_diffs=execution_result.file_diffs_as_dicts(),
            preview_fingerprint=execution_result.preview_fingerprint,
            git_commit=git_commit, commit_error=commit_error, commit_declined=declined,
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
