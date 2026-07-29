from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time

from dev_agent.encoding import UTF8


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class CommandExecutor:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def run(self, command: list[str], timeout_seconds: int = 120) -> CommandResult:
        start = time.perf_counter()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = UTF8
        env["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            command,
            cwd=self.cwd,
            env=env,
            text=True,
            encoding=UTF8,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        return CommandResult(
            command=command,
            cwd=self.cwd,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
        )
