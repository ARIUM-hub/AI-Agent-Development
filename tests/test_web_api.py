import json
import subprocess

import pytest

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.web.api import (
    apply_provider_plan_task,
    build_context_payload,
    build_health_payload,
    build_history_payload,
    preview_provider_plan_task,
    run_dry_run_task,
)


def git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_build_health_payload_reports_local_web_capability(tmp_path) -> None:
    payload = build_health_payload(tmp_path)

    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"
    assert payload["cwd"] == str(tmp_path)
    assert payload["capabilities"]["web_console"] is True
    assert payload["capabilities"]["dry_run_only"] is True


def test_build_context_payload_combines_scan_git_rules_and_verification(tmp_path) -> None:
    write_text_utf8(tmp_path / ".agent" / "rules.md", "# 项目规则\n\n所有文件使用 UTF-8。\n")
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    write_text_utf8(tmp_path / "README.md", "# 示例\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "initial")

    payload = build_context_payload(tmp_path, tmp_path)

    assert payload["scan"]["languages"] == ["python"]
    assert payload["git"]["recent_log"]
    assert payload["rules_text"] == "# 项目规则\n\n所有文件使用 UTF-8。\n"
    assert payload["verification_steps"] == [{"name": "test", "command": ["python", "-m", "pytest"]}]


def test_build_history_payload_lists_tasks(tmp_path) -> None:
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-1",
            title="实现 Web 控制台",
            status="passed",
            summary="已完成 dry-run 页面",
        )
    )

    payload = build_history_payload(tmp_path)

    assert payload["tasks"][0]["task_id"] == "task-1"
    assert payload["tasks"][0]["title"] == "实现 Web 控制台"


def test_run_dry_run_task_requires_fake_response_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = run_dry_run_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="生成实现计划",
        fake_response="计划：先看上下文，再跑测试。",
    )

    assert payload["plan_text"] == "计划：先看上下文，再跑测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "生成实现计划" in history


def test_web_dry_run_does_not_apply_execution_plan_payload(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = run_dry_run_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="尝试通过 Web 写文件",
        fake_response="计划：Web 只允许 dry-run。",
        execution_plan_payload={
            "summary": "不应执行",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/from-web.md",
                    "content": "不应写入\n",
                }
            ],
        },
    )

    assert payload["dry_run"] is True
    assert payload["applied_changes"] == []
    assert not (tmp_path / "docs" / "from-web.md").exists()


def provider_plan_json(path: str = "docs/from-web-provider.md", content: str = "来自 Web provider\n") -> str:
    return json.dumps(
        {
            "summary": "创建 Web provider 文件",
            "operations": [
                {
                    "action": "create_text",
                    "path": path,
                    "content": content,
                }
            ],
        },
        ensure_ascii=False,
    )


def test_preview_provider_plan_task_returns_preview_without_side_effects(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = preview_provider_plan_task(
        repo_root=tmp_path,
        request_text="预览 Web provider plan",
        fake_response=provider_plan_json(),
    )

    assert payload["ok"] is True
    assert payload["task_id"] is None
    assert payload["dry_run"] is True
    assert payload["planned_changes"][0]["path"] == "docs/from-web-provider.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["applied_changes"] == []
    assert payload["diff_stat"] == ""
    assert payload["execution_error"] is None
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "from-web-provider.md").exists()


def test_preview_provider_plan_task_rejects_malformed_json_without_writing(tmp_path) -> None:
    with pytest.raises(ValueError, match="无法解析 provider 执行计划"):
        preview_provider_plan_task(
            repo_root=tmp_path,
            request_text="坏 provider plan",
            fake_response='{"summary":',
        )

    assert not (tmp_path / ".agent").exists()


def test_preview_provider_plan_task_rejects_dangerous_path_without_writing(tmp_path) -> None:
    with pytest.raises(ValueError, match="执行计划预览失败"):
        preview_provider_plan_task(
            repo_root=tmp_path,
            request_text="危险 provider plan",
            fake_response=provider_plan_json(path="../escape.md"),
        )

    assert not (tmp_path.parent / "escape.md").exists()


def test_apply_provider_plan_task_writes_file_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = apply_provider_plan_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="确认 Web provider plan",
        fake_response=provider_plan_json(content="确认写入\n"),
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["task_id"]
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["applied_changes"][0]["path"] == "docs/from-web-provider.md"
    assert (tmp_path / "docs" / "from-web-provider.md").read_text(encoding="utf-8") == "确认写入\n"
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "确认 Web provider plan" in history


def test_apply_provider_plan_task_rechecks_preview_before_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "docs" / "from-web-provider.md", "已存在\n")

    with pytest.raises(ValueError, match="执行计划预览失败"):
        apply_provider_plan_task(
            repo_root=tmp_path,
            home_dir=tmp_path,
            request_text="确认 Web provider plan",
            fake_response=provider_plan_json(),
        )

    assert (tmp_path / "docs" / "from-web-provider.md").read_text(encoding="utf-8") == "已存在\n"
    assert not (tmp_path / ".agent").exists()
