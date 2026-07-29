import sys

from dev_agent.config.models import CommandConfig
from dev_agent.project.scanner import ProjectScan
from dev_agent.verification.planner import build_verification_plan
from dev_agent.verification.runner import VerificationRunner


def test_verification_plan_prefers_explicit_commands(tmp_path) -> None:
    scan = ProjectScan(root=tmp_path, languages=["python"], markers=["pyproject.toml"])
    commands = CommandConfig(test="custom test", lint="custom lint")

    plan = build_verification_plan(commands, scan)

    assert [step.name for step in plan.steps] == ["test", "lint"]
    assert plan.steps[0].command == ["custom", "test"]


def test_verification_plan_uses_scan_suggestions(tmp_path) -> None:
    scan = ProjectScan(
        root=tmp_path,
        languages=["python"],
        markers=["pyproject.toml"],
        suggested_commands=CommandConfig(test="python -m pytest"),
    )

    plan = build_verification_plan(CommandConfig(), scan)

    assert len(plan.steps) == 1
    assert plan.steps[0].command == ["python", "-m", "pytest"]


def test_verification_runner_aggregates_results(tmp_path) -> None:
    commands = CommandConfig(test=f'{sys.executable} -c "print(\'ok\')"')
    scan = ProjectScan(root=tmp_path, languages=["python"], markers=[])
    plan = build_verification_plan(commands, scan)

    result = VerificationRunner(tmp_path).run(plan)

    assert result.passed is True
    assert result.results[0].exit_code == 0
    assert result.results[0].stdout.strip() == "ok"
