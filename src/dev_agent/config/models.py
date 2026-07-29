from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    tech_stack: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandConfig:
    test: str | None = None
    lint: str | None = None
    typecheck: str | None = None
    build: str | None = None


@dataclass(frozen=True)
class UserPreferences:
    language: str = "zh-CN"
    approval_mode: str = "collaborative"


@dataclass(frozen=True)
class AgentContext:
    project: ProjectConfig
    commands: CommandConfig
    preferences: UserPreferences
    rules_text: str
