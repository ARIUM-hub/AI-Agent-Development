import json
import subprocess
import sys
from pathlib import Path


def run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dev_agent.cli", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_init_creates_agent_files(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "init")

    assert result.returncode == 0
    assert (tmp_path / ".agent" / "project.yaml").exists()
    assert (tmp_path / ".agent" / "rules.md").read_text(encoding="utf-8").startswith("# 项目规则")
    assert "initialized" in result.stdout


def test_doctor_outputs_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"
    assert payload["capabilities"] == {
        "provider_interface": True,
        "budget_protection": True,
        "command_executor": True,
        "git_reader": True,
        "verification_runner": True,
    }


def test_scan_outputs_project_languages(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    result = run_cli(tmp_path, "scan")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["languages"] == ["node", "typescript"]
