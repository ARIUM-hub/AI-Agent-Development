from dataclasses import dataclass
from difflib import unified_diff
import hashlib
import json
from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8
from dev_agent.execution.models import ExecutionFileDiff, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.validation import ExecutionPlanValidator


DIFF_MAX_LINES = 200
DIFF_MAX_CHARS = 20_000


@dataclass
class _SimulatedFile:
    raw_path: str
    target: Path
    before_exists: bool
    before_content: str
    after_content: str


class ExecutionPlanDiffer:
    def __init__(self, repo_root: Path, validator: ExecutionPlanValidator) -> None:
        self.repo_root = repo_root.resolve()
        self.validator = validator

    def build(self, plan: ExecutionPlan) -> tuple[list[ExecutionFileDiff], str]:
        self.validator.validate(plan)
        files = self._simulate(plan)
        file_diffs = [self._build_file_diff(item) for item in files]
        return file_diffs, self._fingerprint(plan, files)

    def _simulate(self, plan: ExecutionPlan) -> list[_SimulatedFile]:
        by_target: dict[Path, _SimulatedFile] = {}
        ordered: list[_SimulatedFile] = []
        for operation in plan.operations:
            target = self.validator.resolve_target(operation.path)
            item = by_target.get(target)
            if item is None:
                before_exists = target.exists()
                before_content = read_text_utf8(target) if before_exists else ""
                item = _SimulatedFile(
                    raw_path=operation.path,
                    target=target,
                    before_exists=before_exists,
                    before_content=before_content,
                    after_content=before_content,
                )
                by_target[target] = item
                ordered.append(item)
            if operation.action in {"create_text", "overwrite_text"}:
                item.after_content = operation.content
            elif operation.action == "append_text":
                item.after_content += operation.content
            else:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
        return ordered

    def _build_file_diff(self, item: _SimulatedFile) -> ExecutionFileDiff:
        if item.before_content == item.after_content:
            full_diff = ""
        else:
            old_label = f"a/{item.raw_path}" if item.before_exists else "/dev/null"
            new_label = f"b/{item.raw_path}"
            lines = list(
                unified_diff(
                    item.before_content.splitlines(),
                    item.after_content.splitlines(),
                    fromfile=old_label,
                    tofile=new_label,
                    lineterm="",
                )
            )
            full_diff = "\n".join(lines) + ("\n" if lines else "")
        additions = sum(
            1
            for line in full_diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1
            for line in full_diff.splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        status = "added" if not item.before_exists else "modified"
        if item.before_content == item.after_content:
            status = "unchanged"
        return ExecutionFileDiff(
            path=item.raw_path,
            status=status,
            diff_text=full_diff,
            additions=additions,
            deletions=deletions,
            diff_line_count=len(full_diff.splitlines()),
            diff_char_count=len(full_diff),
            displayed_line_count=len(full_diff.splitlines()),
            displayed_char_count=len(full_diff),
            truncated=False,
            before_line_ending=self._line_ending(item.before_content),
            after_line_ending=self._line_ending(item.after_content),
        )

    def _line_ending(self, text: str) -> str:
        without_crlf = text.replace("\r\n", "")
        if "\r\n" in text and "\n" not in without_crlf and "\r" not in without_crlf:
            return "crlf"
        if "\r\n" in text or "\r" in text:
            return "mixed"
        if "\n" in text:
            return "lf"
        return "none"

    def _fingerprint(self, plan: ExecutionPlan, files: list[_SimulatedFile]) -> str:
        state = {
            "plan": plan.to_dict(),
            "files": [
                {
                    "path": item.raw_path,
                    "before_exists": item.before_exists,
                    "before_sha256": hashlib.sha256(item.before_content.encode(UTF8)).hexdigest(),
                    "after_sha256": hashlib.sha256(item.after_content.encode(UTF8)).hexdigest(),
                }
                for item in files
            ],
        }
        encoded = json.dumps(
            state,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode(UTF8)
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
