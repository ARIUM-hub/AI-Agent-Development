from pathlib import Path

from dev_agent.execution.models import ExecutionPlan, SUPPORTED_ACTIONS
from dev_agent.execution.plan import ExecutionPlanError


FORBIDDEN_ROOTS = {".git", ".worktrees", ".superpowers"}
FORBIDDEN_ROOT_NAMES = {name.casefold() for name in FORBIDDEN_ROOTS}


class ExecutionPlanValidator:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def resolve_target(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise ExecutionPlanError("path must not be empty")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ExecutionPlanError(f"path must be relative: {raw_path}")
        target = (self.repo_root / relative).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError as exc:
            raise ExecutionPlanError(f"path escapes repository: {raw_path}") from exc
        relative_parts = target.relative_to(self.repo_root).parts
        if any(part.casefold() in FORBIDDEN_ROOT_NAMES for part in relative_parts):
            raise ExecutionPlanError(f"path is not allowed: {raw_path}")
        return target

    def validate(self, plan: ExecutionPlan) -> None:
        planned_files: set[Path] = set()
        for operation in plan.operations:
            if operation.action not in SUPPORTED_ACTIONS:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
            target = self.resolve_target(operation.path)
            self._validate_parent_directories(target, planned_files)
            if target.exists() and target.is_dir():
                raise ExecutionPlanError(f"path is a directory: {operation.path}")
            if operation.action == "create_text" and (target.exists() or target in planned_files):
                raise ExecutionPlanError(f"path already exists: {operation.path}")
            planned_files.add(target)

    def _validate_parent_directories(self, target: Path, planned_files: set[Path]) -> None:
        for parent in target.parents:
            if parent == self.repo_root:
                return
            if parent.exists() and not parent.is_dir():
                relative = parent.relative_to(self.repo_root)
                raise ExecutionPlanError(f"parent path is not a directory: {relative}")
            if parent in planned_files:
                relative = parent.relative_to(self.repo_root)
                raise ExecutionPlanError(f"parent path is not a directory: {relative}")
