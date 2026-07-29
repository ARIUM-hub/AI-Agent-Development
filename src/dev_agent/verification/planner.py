from dataclasses import dataclass
import shlex

from dev_agent.config.models import CommandConfig
from dev_agent.project.scanner import ProjectScan


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: list[str]


@dataclass(frozen=True)
class VerificationPlan:
    steps: list[VerificationStep]


def _split(command: str | None) -> list[str] | None:
    if not command:
        return None
    return [_strip_outer_quotes(part) for part in shlex.split(command, posix=False)]


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def build_verification_plan(commands: CommandConfig, scan: ProjectScan) -> VerificationPlan:
    steps: list[VerificationStep] = []
    candidates = {
        "test": commands.test or scan.suggested_commands.test,
        "lint": commands.lint or scan.suggested_commands.lint,
        "typecheck": commands.typecheck or scan.suggested_commands.typecheck,
        "build": commands.build or scan.suggested_commands.build,
    }
    for name, command in candidates.items():
        parts = _split(command)
        if parts:
            steps.append(VerificationStep(name=name, command=parts))
    return VerificationPlan(steps=steps)
