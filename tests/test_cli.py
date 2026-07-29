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
        "web_console": True,
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


def test_serve_check_outputs_local_url(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "serve", "--host", "127.0.0.1", "--port", "0", "--check")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["host"] == "127.0.0.1"
    assert isinstance(payload["port"], int)
    assert payload["url"].startswith("http://127.0.0.1:")


def test_run_applies_plan_file_and_reports_changes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "创建说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/execution.md",
                        "content": "执行闭环\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "创建说明",
        "--fake-response",
        "计划：创建说明文件。",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--yes",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_error"] is None
    assert payload["applied_changes"][0]["path"] == "docs/execution.md"
    assert (tmp_path / "docs" / "execution.md").read_text(encoding="utf-8") == "执行闭环\n"


def test_run_previews_plan_file_without_apply(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "只预览\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览计划",
        "--fake-response",
        "计划：只预览。",
        "--plan-file",
        str(plan_file),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned_changes"][0]["path"] == "docs/preview.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["preview_changes"][0]["content_bytes"] == len("只预览\n".encode("utf-8"))
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "preview.md").exists()


def test_run_preview_outputs_preview_changes_without_writing(tmp_path: Path) -> None:
    write_target = tmp_path / "docs" / "preview.md"
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "预览中文\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览计划",
        "--fake-response",
        "计划：只预览。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["preview_changes"] == [
        {
            "action": "create_text",
            "path": "docs/preview.md",
            "exists": False,
            "content_bytes": len("预览中文\n".encode("utf-8")),
            "risk": "create",
        }
    ]
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not write_target.exists()


def test_run_accepts_plan_file_with_utf8_bom(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        "\ufeff"
        + json.dumps(
            {
                "summary": "BOM 计划",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/bom.md",
                        "content": "兼容 Windows UTF-8 BOM\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "读取 BOM 计划",
        "--fake-response",
        "计划：兼容 BOM。",
        "--plan-file",
        str(plan_file),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned_changes"][0]["path"] == "docs/bom.md"
    assert payload["applied_changes"] == []


def test_run_apply_requires_plan_file(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "缺少计划",
        "--fake-response",
        "计划：失败。",
        "--apply",
    )

    assert result.returncode == 2
    assert "--plan-file is required when --apply is used" in result.stderr


def test_run_reports_missing_plan_file_as_cli_error(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "缺少计划文件",
        "--fake-response",
        "计划：失败。",
        "--plan-file",
        str(tmp_path / "missing.json"),
        "--apply",
    )

    assert result.returncode == 2
    assert "无法读取执行计划" in result.stderr


def test_run_apply_without_confirmation_rejects_and_does_not_write(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "需要确认",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/needs-confirmation.md",
                        "content": "不应写入\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "未确认执行",
        "--fake-response",
        "计划：需要确认。",
        "--plan-file",
        str(plan_file),
        "--apply",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert not (tmp_path / "docs" / "needs-confirmation.md").exists()


def test_run_preview_rejects_create_conflict_without_writing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# existing\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "冲突预览",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "README.md",
                        "content": "# new\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览冲突",
        "--fake-response",
        "计划：冲突。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 2
    assert "执行计划预览失败" in result.stderr
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# existing\n"
