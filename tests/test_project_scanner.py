from pathlib import Path

from dev_agent.encoding import write_text_utf8
from dev_agent.project.scanner import scan_project


def test_scans_python_project(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", '[project]\nname = "demo"\n')
    write_text_utf8(tmp_path / "pytest.ini", "[pytest]\n")

    result = scan_project(tmp_path)

    assert result.languages == ["python"]
    assert "pyproject.toml" in result.markers
    assert result.suggested_commands.test == "python -m pytest"


def test_scans_node_typescript_project(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "package.json", '{"scripts":{"test":"vitest","build":"tsc"}}\n')
    write_text_utf8(tmp_path / "tsconfig.json", "{}\n")

    result = scan_project(tmp_path)

    assert result.languages == ["node", "typescript"]
    assert "package.json" in result.markers
    assert result.suggested_commands.test == "npm test"
    assert result.suggested_commands.build == "npm run build"
