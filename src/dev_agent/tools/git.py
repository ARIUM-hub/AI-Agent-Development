from dataclasses import dataclass
from pathlib import Path

from dev_agent.tools.executor import CommandExecutor


@dataclass(frozen=True)
class GitSnapshot:
    status: str
    diff_stat: str
    recent_log: str


class GitReader:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.executor = CommandExecutor(repo_root)

    def snapshot(self) -> GitSnapshot:
        status = self.executor.run(["git", "status", "--short"])
        diff_stat = self.executor.run(["git", "diff", "--stat"])
        recent_log = self.executor.run(["git", "log", "--oneline", "-5"])
        return GitSnapshot(
            status=status.stdout,
            diff_stat=diff_stat.stdout,
            recent_log=recent_log.stdout,
        )
