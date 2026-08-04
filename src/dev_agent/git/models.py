from dataclasses import dataclass
from typing import Callable


class GitCommitError(Exception):
    pass


class GitCommitPreflightError(GitCommitError):
    pass


class GitCommitRejectedError(GitCommitError):
    pass


class GitCommitCommandError(GitCommitError):
    pass


@dataclass(frozen=True, order=True)
class GitStatusEntry:
    index: str
    worktree: str
    path: str
    original_path: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        if self.original_path is None:
            return (self.path,)
        return (self.path, self.original_path)


@dataclass(frozen=True)
class GitCommitSnapshot:
    head_sha: str
    branch: str
    status_entries: tuple[GitStatusEntry, ...]
    target_paths: tuple[str, ...]


@dataclass(frozen=True)
class GitCommitRequest:
    message: str
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitCommitResult:
    sha: str
    message: str
    paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"sha": self.sha, "message": self.message, "paths": list(self.paths)}


CommitConfirmation = Callable[[GitCommitRequest, tuple[str, ...]], bool]
