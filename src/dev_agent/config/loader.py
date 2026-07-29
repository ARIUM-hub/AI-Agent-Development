from pathlib import Path
from typing import Any

import yaml

from dev_agent.config.models import AgentContext, CommandConfig, ProjectConfig, UserPreferences
from dev_agent.encoding import read_text_utf8


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(read_text_utf8(path))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML file: {path}")
    return data


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return read_text_utf8(path)


def load_agent_context(repo_root: Path, home_dir: Path) -> AgentContext:
    repo_root = repo_root.resolve()
    home_dir = home_dir.resolve()
    agent_dir = repo_root / ".agent"
    user_dir = home_dir / ".dev-agent"

    project_data = _read_yaml(agent_dir / "project.yaml")
    command_data = _read_yaml(agent_dir / "commands.yaml")
    preference_data = _read_yaml(user_dir / "preferences.yaml")

    project = ProjectConfig(
        name=str(project_data.get("name") or repo_root.name),
        tech_stack=[str(item) for item in project_data.get("tech_stack", [])],
    )
    commands = CommandConfig(
        test=command_data.get("test"),
        lint=command_data.get("lint"),
        typecheck=command_data.get("typecheck"),
        build=command_data.get("build"),
    )
    preferences = UserPreferences(
        language=str(preference_data.get("language") or "zh-CN"),
        approval_mode=str(preference_data.get("approval_mode") or "collaborative"),
    )

    return AgentContext(
        project=project,
        commands=commands,
        preferences=preferences,
        rules_text=_read_optional_text(agent_dir / "rules.md"),
    )
