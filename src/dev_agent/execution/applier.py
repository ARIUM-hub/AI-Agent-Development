from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8, write_text_utf8
from dev_agent.execution.models import (
    ExecutionChange,
    ExecutionOperation,
    ExecutionPlan,
    ExecutionPreviewChange,
    ExecutionResult,
)
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.tools.git import GitReader


FORBIDDEN_ROOTS = {".git", ".worktrees", ".superpowers"}
FORBIDDEN_ROOT_NAMES = {name.casefold() for name in FORBIDDEN_ROOTS}
SUPPORTED_ACTIONS = {"create_text", "overwrite_text", "append_text"}


class ExecutionPlanApplier:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def planned_changes(self, plan: ExecutionPlan) -> list[dict[str, object]]:
        return [operation.to_dict() for operation in plan.operations]

    def preview(self, plan: ExecutionPlan) -> ExecutionResult:
        return ExecutionResult(
            applied=False,
            planned_changes=self.planned_changes(plan),
            preview_changes=self._preview_changes(plan),
        )

    def apply(self, plan: ExecutionPlan) -> ExecutionResult:
        self._validate_operations(plan)
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
        if any(part.casefold() in FORBIDDEN_ROOT_NAMES for part in relative_parts):
            raise ExecutionPlanError(f"path is not allowed: {raw_path}")
        return target

    def _validate_operations(self, plan: ExecutionPlan) -> None:
        created_targets: set[Path] = set()
        for operation in plan.operations:
            if operation.action not in SUPPORTED_ACTIONS:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
            target = self._resolve_target(operation.path)
            if operation.action == "create_text":
                if target.exists() or target in created_targets:
                    raise ExecutionPlanError(f"path already exists: {operation.path}")
                created_targets.add(target)

    def _preview_changes(self, plan: ExecutionPlan) -> list[ExecutionPreviewChange]:
        self._validate_operations(plan)
        return [
            ExecutionPreviewChange(
                action=operation.action,
                path=operation.path,
                exists=self._resolve_target(operation.path).exists(),
                content_bytes=len(operation.content.encode(UTF8)),
                risk=self._risk_for_operation(operation),
            )
            for operation in plan.operations
        ]

    def _risk_for_operation(self, operation: ExecutionOperation) -> str:
        if operation.action == "create_text":
            return "create"
        if operation.action == "overwrite_text":
            return "overwrite"
        if operation.action == "append_text":
            target = self._resolve_target(operation.path)
            return "append" if target.exists() else "append_create"
        raise ExecutionPlanError(f"unsupported action: {operation.action}")
