from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8, write_text_utf8
from dev_agent.execution.models import ExecutionChange, ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.tools.git import GitReader


FORBIDDEN_ROOTS = {".git", ".worktrees", ".superpowers"}


class ExecutionPlanApplier:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def planned_changes(self, plan: ExecutionPlan) -> list[dict[str, object]]:
        return [operation.to_dict() for operation in plan.operations]

    def preview(self, plan: ExecutionPlan) -> ExecutionResult:
        return ExecutionResult(
            applied=False,
            planned_changes=self.planned_changes(plan),
        )

    def apply(self, plan: ExecutionPlan) -> ExecutionResult:
        changes: list[ExecutionChange] = []
        for operation in plan.operations:
            target = self._resolve_target(operation.path)
            before_exists = target.exists()
            if operation.action == "create_text":
                if before_exists:
                    raise ExecutionPlanError(f"path already exists: {operation.path}")
                write_text_utf8(target, operation.content)
            elif operation.action == "overwrite_text":
                write_text_utf8(target, operation.content)
            elif operation.action == "append_text":
                existing = read_text_utf8(target) if before_exists else ""
                write_text_utf8(target, existing + operation.content)
            else:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
            changes.append(
                ExecutionChange(
                    action=operation.action,
                    path=operation.path,
                    before_exists=before_exists,
                    after_exists=target.exists(),
                    bytes_written=len(operation.content.encode(UTF8)),
                )
            )
        diff_stat = GitReader(self.repo_root).snapshot().diff_stat
        return ExecutionResult(
            applied=True,
            planned_changes=self.planned_changes(plan),
            changes=changes,
            diff_stat=diff_stat,
        )

    def _resolve_target(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise ExecutionPlanError("path must not be empty")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ExecutionPlanError(f"path must be relative: {raw_path}")
        repo_root = self.repo_root.resolve()
        target = (repo_root / relative).resolve()
        try:
            target.relative_to(repo_root)
        except ValueError as exc:
            raise ExecutionPlanError(f"path escapes repository: {raw_path}") from exc
        relative_parts = target.relative_to(repo_root).parts
        if relative_parts and relative_parts[0] in FORBIDDEN_ROOTS:
            raise ExecutionPlanError(f"path is not allowed: {raw_path}")
        return target
