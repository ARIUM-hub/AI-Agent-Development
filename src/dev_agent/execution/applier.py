from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8, write_text_utf8
from dev_agent.execution.diff import ExecutionPlanDiffer
from dev_agent.execution.models import (
    ExecutionChange,
    ExecutionOperation,
    ExecutionPlan,
    ExecutionPreviewChange,
    ExecutionResult,
)
from dev_agent.execution.plan import ExecutionPlanError, StaleExecutionPreviewError
from dev_agent.execution.validation import ExecutionPlanValidator
from dev_agent.tools.git import GitReader


CONTENT_PREVIEW_MAX_LINES = 6
CONTENT_PREVIEW_MAX_CHARS = 600


class ExecutionPlanApplier:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.validator = ExecutionPlanValidator(repo_root)

    def planned_changes(self, plan: ExecutionPlan) -> list[dict[str, object]]:
        return [operation.to_dict() for operation in plan.operations]

    def preview(self, plan: ExecutionPlan) -> ExecutionResult:
        file_diffs, preview_fingerprint = ExecutionPlanDiffer(
            self.repo_root,
            self.validator,
        ).build(plan)
        return ExecutionResult(
            applied=False,
            planned_changes=self.planned_changes(plan),
            preview_changes=self._preview_changes(plan),
            file_diffs=file_diffs,
            preview_fingerprint=preview_fingerprint,
        )

    def apply(self, plan: ExecutionPlan, *, expected_fingerprint: str) -> ExecutionResult:
        file_diffs, current_fingerprint = ExecutionPlanDiffer(
            self.repo_root,
            self.validator,
        ).build(plan)
        if current_fingerprint != expected_fingerprint:
            raise StaleExecutionPreviewError("文件状态已变化，请重新预览后再执行")
        changes: list[ExecutionChange] = []
        for operation in plan.operations:
            target = self.validator.resolve_target(operation.path)
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
            file_diffs=file_diffs,
            preview_fingerprint=current_fingerprint,
        )

    def _content_preview_for_operation(self, operation: ExecutionOperation) -> dict[str, object]:
        content = operation.content
        line_parts = content.splitlines(keepends=True)
        line_count = len(content.splitlines())
        line_limited = "".join(line_parts[:CONTENT_PREVIEW_MAX_LINES])
        truncated_by_lines = len(line_parts) > CONTENT_PREVIEW_MAX_LINES
        if len(line_limited) > CONTENT_PREVIEW_MAX_CHARS:
            preview = line_limited[:CONTENT_PREVIEW_MAX_CHARS]
            truncated_by_chars = True
        else:
            preview = line_limited
            truncated_by_chars = False
        return {
            "content_preview": preview,
            "content_preview_truncated": truncated_by_lines or truncated_by_chars,
            "content_preview_line_count": line_count,
            "content_preview_char_count": len(content),
        }

    def _preview_changes(self, plan: ExecutionPlan) -> list[ExecutionPreviewChange]:
        self.validator.validate(plan)
        return [
            ExecutionPreviewChange(
                action=operation.action,
                path=operation.path,
                exists=self.validator.resolve_target(operation.path).exists(),
                content_bytes=len(operation.content.encode(UTF8)),
                risk=self._risk_for_operation(operation),
                **self._content_preview_for_operation(operation),
            )
            for operation in plan.operations
        ]

    def _risk_for_operation(self, operation: ExecutionOperation) -> str:
        if operation.action == "create_text":
            return "create"
        if operation.action == "overwrite_text":
            return "overwrite"
        if operation.action == "append_text":
            target = self.validator.resolve_target(operation.path)
            return "append" if target.exists() else "append_create"
        raise ExecutionPlanError(f"unsupported action: {operation.action}")
