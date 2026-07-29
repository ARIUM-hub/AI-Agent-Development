import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    project_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(project_src)
    return subprocess.run(
        [sys.executable, "-m", "dev_agent.cli", *args],
        cwd=repo,
        env=env,
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
        "runtime_context": True,
        "local_task_runner": True,
    }


def test_scan_outputs_project_languages(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    result = run_cli(tmp_path, "scan")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["languages"] == ["node", "typescript"]


def test_history_lists_task_records(tmp_path: Path) -> None:
    history_dir = tmp_path / ".agent" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "tasks.jsonl").write_text(
        '{"task_id":"task-1","title":"修复中文乱码","status":"passed","summary":"UTF-8 修复","events":[],"verification":[],"lessons":[]}\n',
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "history")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["tasks"][0]["title"] == "修复中文乱码"


def test_history_searches_memory(tmp_path: Path) -> None:
    history_dir = tmp_path / ".agent" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "tasks.jsonl").write_text(
        '{"task_id":"task-1","title":"修复中文乱码","status":"passed","summary":"UTF-8 修复","events":[],"verification":[],"lessons":["提交前运行完整测试"]}\n',
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "history", "--query", "完整测试")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hits"][0]["record_id"] == "task-1"


def test_run_uses_fake_response_and_records_history(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")

    result = run_cli(
        tmp_path,
        "run",
        "实现 history 查询",
        "--fake-response",
        "计划：读取文件并运行测试。",
        "--dry-run",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plan_text"] == "计划：读取文件并运行测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "实现 history 查询" in history
