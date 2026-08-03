from pathlib import Path

from dev_agent.config.loader import load_agent_context
from dev_agent.encoding import write_text_utf8


def test_loads_repository_rules_and_user_preferences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    write_text_utf8(
        repo / ".agent" / "project.yaml",
        "name: 演示项目\ntech_stack:\n  - python\n",
    )
    write_text_utf8(
        repo / ".agent" / "commands.yaml",
        "test: python -m pytest\nlint: python -m ruff check .\n",
    )
    write_text_utf8(
        repo / ".agent" / "rules.md",
        "所有文件默认 UTF-8，中文不要写成 unicode 转义。\n",
    )
    write_text_utf8(
        home / ".dev-agent" / "preferences.yaml",
        "language: zh-CN\napproval_mode: collaborative\n",
    )

    context = load_agent_context(repo, home)

    assert context.project.name == "演示项目"
    assert context.project.tech_stack == ["python"]
    assert context.commands.test == "python -m pytest"
    assert context.commands.lint == "python -m ruff check ."
    assert context.rules_text.startswith("所有文件默认 UTF-8")
    assert context.preferences.language == "zh-CN"
    assert context.preferences.approval_mode == "collaborative"


def test_missing_files_use_safe_defaults(tmp_path: Path) -> None:
    context = load_agent_context(tmp_path / "repo", tmp_path / "home")

    assert context.project.name == "repo"
    assert context.project.tech_stack == []
    assert context.commands.test is None
    assert context.preferences.language == "zh-CN"
