from pathlib import Path
import re

from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.validation import ExecutionPlanValidator
from dev_agent.git.models import (
    GitCommitError,
    GitCommitCommandError,
    GitCommitPreflightError,
    GitCommitRejectedError,
    GitCommitResult,
    GitCommitSnapshot,
    GitStatusEntry,
)
from dev_agent.tools.executor import CommandExecutor, CommandResult
from dev_agent.verification.planner import VerificationPlan


IN_PROGRESS_MARKERS = {
    "MERGE_HEAD": "merge",
    "rebase-apply": "rebase",
    "rebase-merge": "rebase",
    "CHERRY_PICK_HEAD": "cherry-pick",
    "REVERT_HEAD": "revert",
    "BISECT_LOG": "bisect",
}


def validate_commit_message(message: str) -> str:
    if not message.strip():
        raise GitCommitPreflightError("--commit-message 不能为空")
    if len(message) > 200:
        raise GitCommitPreflightError("--commit-message 不能超过 200 个字符")
    if any(char in message for char in ("\r", "\n", "\0")):
        raise GitCommitPreflightError("--commit-message 必须是单行文本")
    return message


def parse_porcelain_v1_z(raw: str) -> tuple[GitStatusEntry, ...]:
    records = raw.split("\0")
    if records and records[-1] == "":
        records.pop()
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2] != " ":
            raise GitCommitPreflightError("无法解析 Git 状态")
        x, y, path = record[0], record[1], record[3:]
        original_path = None
        if x in {"R", "C"} or y in {"R", "C"}:
            index += 1
            if index >= len(records):
                raise GitCommitPreflightError("无法解析 Git 状态中的重命名记录")
            original_path = records[index]
        entries.append(GitStatusEntry(x, y, path, original_path))
        index += 1
    return tuple(entries)


class GitCommitGuard:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.executor = CommandExecutor(self.repo_root)

    def preflight(
        self, plan: ExecutionPlan, verification_plan: VerificationPlan
    ) -> GitCommitSnapshot:
        if not verification_plan.steps:
            raise GitCommitPreflightError("受控提交至少需要一条验证命令")
        self._require_repo_root()
        head_sha = self._head_sha()
        branch = self._branch()
        self._require_no_operation_in_progress()
        targets = self._target_paths(plan)
        target_keys = {path.casefold() for path in targets}
        entries = self._status_entries()
        dirty = sorted(
            {path for entry in entries for path in entry.paths if path.casefold() in target_keys}
        )
        if dirty:
            raise GitCommitPreflightError(
                "目标路径在运行前必须干净：" + ", ".join(dirty)
            )
        validator = ExecutionPlanValidator(self.repo_root)
        for operation in plan.operations:
            path = validator.resolve_target(operation.path).relative_to(self.repo_root).as_posix()
            if operation.action == "create_text" and self._is_ignored(path):
                raise GitCommitPreflightError(f"新建目标被 Git ignore：{path}")
        return GitCommitSnapshot(head_sha, branch, entries, targets)

    def prepare_commit(self, snapshot: GitCommitSnapshot) -> tuple[str, ...]:
        try:
            head, branch = self._head_sha(), self._branch()
        except GitCommitPreflightError as exc:
            raise GitCommitRejectedError(str(exc)) from exc
        if head != snapshot.head_sha:
            raise GitCommitRejectedError("运行期间 HEAD 已变化，拒绝提交")
        if branch != snapshot.branch:
            raise GitCommitRejectedError("运行期间分支已变化，拒绝提交")
        self._require_no_operation_in_progress(GitCommitRejectedError)
        current = self._status_entries()
        keys = {path.casefold() for path in snapshot.target_paths}
        before = self._outside_entries(snapshot.status_entries, keys)
        after = self._outside_entries(current, keys)
        if before != after:
            changed = sorted({path for entry in before ^ after for path in entry.paths})
            raise GitCommitRejectedError("目标外 Git 状态发生变化：" + ", ".join(changed))
        paths = tuple(sorted({entry.path for entry in current if all(p.casefold() in keys for p in entry.paths)}))
        if not paths:
            raise GitCommitRejectedError("目标路径没有实际变化，不创建空提交")
        return paths

    def commit(
        self, snapshot: GitCommitSnapshot, message: str, changed_paths: tuple[str, ...]
    ) -> GitCommitResult:
        message = validate_commit_message(message)
        paths = tuple(sorted(set(changed_paths)))
        if not paths:
            raise GitCommitRejectedError("目标路径没有实际变化，不创建空提交")
        try:
            self._git_command(["add", "--", *paths])
            self._require_staged_targets(paths)
            self._require_outside_state(snapshot)
            self._git_command(
                ["commit", "--only", "--cleanup=verbatim", "-m", message, "--", *paths]
            )
        except (GitCommitCommandError, GitCommitRejectedError):
            self._restore_target_index(paths)
            raise
        sha = self._head_sha()
        self._validate_created_commit(snapshot, sha, message, paths)
        return GitCommitResult(sha, message, paths)

    @staticmethod
    def _outside_entries(
        entries: tuple[GitStatusEntry, ...], keys: set[str]
    ) -> frozenset[GitStatusEntry]:
        return frozenset(entry for entry in entries if any(path.casefold() not in keys for path in entry.paths))

    def _git_command(self, args: list[str]) -> CommandResult:
        result = self.executor.run(["git", *args])
        if result.exit_code != 0:
            raise GitCommitCommandError(
                self._sanitize_output(result.stderr or result.stdout) or "Git 提交命令执行失败"
            )
        return result

    def _restore_target_index(self, paths: tuple[str, ...]) -> None:
        result = self.executor.run(["git", "restore", "--staged", "--", *paths])
        if result.exit_code != 0:
            raise GitCommitCommandError(
                "提交失败且目标暂存恢复失败，请人工检查 Git index："
                + self._sanitize_output(result.stderr or result.stdout)
            )

    def _require_staged_targets(self, paths: tuple[str, ...]) -> None:
        staged = tuple(sorted(filter(None, self._git_command(
            ["diff", "--cached", "--name-only", "-z", "--", *paths]
        ).stdout.split("\0"))))
        if staged != paths:
            raise GitCommitCommandError("目标暂存文件集合与审批范围不一致")

    def _require_outside_state(self, snapshot: GitCommitSnapshot) -> None:
        keys = {path.casefold() for path in snapshot.target_paths}
        if self._outside_entries(snapshot.status_entries, keys) != self._outside_entries(self._status_entries(), keys):
            raise GitCommitRejectedError("目标外 Git 状态发生变化")

    def _validate_created_commit(
        self, snapshot: GitCommitSnapshot, sha: str, message: str, paths: tuple[str, ...]
    ) -> None:
        parents = self._git_command(["rev-list", "--parents", "-n", "1", sha]).stdout.split()
        if len(parents) != 2 or parents[1].lower() != snapshot.head_sha:
            raise GitCommitCommandError("新提交父提交校验失败，请人工检查 Git 历史")
        committed = tuple(sorted(filter(None, self._git_command(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", sha]
        ).stdout.split("\0"))))
        if committed != paths:
            raise GitCommitCommandError("新提交文件集合校验失败，请人工检查 Git 历史")
        body = self._git_command(["cat-file", "commit", sha]).stdout.partition("\n\n")[2].removesuffix("\n")
        if body != message or self._branch() != snapshot.branch:
            raise GitCommitCommandError("新提交 message 或分支校验失败，请人工检查 Git 历史")
        keys = {path.casefold() for path in paths}
        dirty = sorted({p for entry in self._status_entries() for p in entry.paths if p.casefold() in keys})
        if dirty:
            raise GitCommitCommandError("新提交后目标路径仍有未提交变化，请人工检查：" + ", ".join(dirty))
        try:
            self._require_outside_state(snapshot)
        except GitCommitRejectedError as exc:
            raise GitCommitCommandError("新提交后的仓库状态校验失败，请人工检查 Git 历史：" + str(exc)) from exc

    def _git(
        self, args: list[str], allowed: frozenset[int] = frozenset({0})
    ) -> CommandResult:
        result = self.executor.run(["git", *args])
        if result.exit_code not in allowed:
            detail = self._sanitize_output(result.stderr or result.stdout)
            raise GitCommitPreflightError(detail or "Git 命令执行失败")
        return result

    def _require_repo_root(self) -> None:
        root = Path(self._git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
        if root != self.repo_root:
            raise GitCommitPreflightError("命令必须从 Git worktree 根目录运行")

    def _head_sha(self) -> str:
        result = self.executor.run(["git", "rev-parse", "--verify", "HEAD"])
        if result.exit_code != 0 or not result.stdout.strip():
            raise GitCommitPreflightError("当前分支 HEAD 尚无提交，拒绝受控提交")
        return result.stdout.strip().lower()

    def _branch(self) -> str:
        result = self._git(
            ["symbolic-ref", "--quiet", "--short", "HEAD"], frozenset({0, 1})
        )
        if result.exit_code != 0 or not result.stdout.strip():
            raise GitCommitPreflightError("受控提交不支持 detached HEAD")
        return result.stdout.strip()

    def _status_entries(self) -> tuple[GitStatusEntry, ...]:
        raw = self._git(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        ).stdout
        return parse_porcelain_v1_z(raw)

    def _target_paths(self, plan: ExecutionPlan) -> tuple[str, ...]:
        validator = ExecutionPlanValidator(self.repo_root)
        paths: dict[str, str] = {}
        for operation in plan.operations:
            path = validator.resolve_target(operation.path).relative_to(self.repo_root).as_posix()
            paths.setdefault(path.casefold(), path)
        return tuple(paths.values())

    def _is_ignored(self, path: str) -> bool:
        return self._git(["check-ignore", "-q", "--", path], frozenset({0, 1})).exit_code == 0

    def _require_no_operation_in_progress(
        self, error_type: type[GitCommitError] = GitCommitPreflightError
    ) -> None:
        for marker, label in IN_PROGRESS_MARKERS.items():
            raw = self._git(["rev-parse", "--git-path", marker]).stdout.strip()
            marker_path = Path(raw)
            if not marker_path.is_absolute():
                marker_path = self.repo_root / marker_path
            if marker_path.exists():
                raise error_type(f"Git {label} 操作正在进行，拒绝提交")

    def _sanitize_output(self, output: str) -> str:
        sanitized = output.replace(str(self.repo_root), "<repo>")
        sanitized = sanitized.replace(self.repo_root.as_posix(), "<repo>")
        sanitized = re.sub(
            r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+",
            r"\1=<redacted>",
            sanitized,
        )
        if len(sanitized) > 2000:
            return sanitized[:2000] + "\n<已截断>"
        return sanitized.strip()
