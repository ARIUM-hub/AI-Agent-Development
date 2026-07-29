from dataclasses import dataclass
from pathlib import Path

from dev_agent.tools.executor import CommandExecutor, CommandResult
from dev_agent.verification.planner import VerificationPlan


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    results: list[CommandResult]


class VerificationRunner:
    def __init__(self, cwd: Path) -> None:
        self.executor = CommandExecutor(cwd)

    def run(self, plan: VerificationPlan) -> VerificationResult:
        results = [self.executor.run(step.command) for step in plan.steps]
        return VerificationResult(
            passed=all(result.exit_code == 0 for result in results),
            results=results,
        )
