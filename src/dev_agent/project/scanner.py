from dataclasses import dataclass, field
from pathlib import Path

from dev_agent.config.models import CommandConfig


@dataclass(frozen=True)
class ProjectScan:
    root: Path
    languages: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    suggested_commands: CommandConfig = field(default_factory=CommandConfig)


def _has(root: Path, name: str) -> bool:
    return (root / name).exists()


def scan_project(root: Path) -> ProjectScan:
    root = root.resolve()
    languages: list[str] = []
    markers: list[str] = []
    test_command: str | None = None
    lint_command: str | None = None
    typecheck_command: str | None = None
    build_command: str | None = None

    if _has(root, "pyproject.toml") or _has(root, "requirements.txt"):
        languages.append("python")
        for marker in ("pyproject.toml", "requirements.txt", "pytest.ini"):
            if _has(root, marker):
                markers.append(marker)
        test_command = "python -m pytest"

    if _has(root, "package.json"):
        languages.append("node")
        markers.append("package.json")
        test_command = test_command or "npm test"
        build_command = "npm run build"

    if _has(root, "tsconfig.json"):
        languages.append("typescript")
        markers.append("tsconfig.json")
        typecheck_command = "npm run typecheck"

    return ProjectScan(
        root=root,
        languages=languages,
        markers=markers,
        suggested_commands=CommandConfig(
            test=test_command,
            lint=lint_command,
            typecheck=typecheck_command,
            build=build_command,
        ),
    )
