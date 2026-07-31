import json
from http import HTTPStatus
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.web.server import create_server


def start_server(tmp_path):
    server = create_server(repo_root=tmp_path, home_dir=tmp_path, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], json.loads(response.read().decode("utf-8"))


def post_json(url, payload):
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers["Content-Type"], json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, exc.headers["Content-Type"], json.loads(exc.read().decode("utf-8"))


def get_text(url):
    with urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], response.read().decode("utf-8")


def provider_plan_payload(
    path="docs/from-web-route.md",
    content="来自 Web route\n",
    action="create_text",
    preview_fingerprint=None,
):
    payload = {
        "request": "Web provider route",
        "fake_response": json.dumps(
            {
                "summary": "创建 Web route 文件",
                "operations": [
                    {
                        "action": action,
                        "path": path,
                        "content": content,
                    }
                ],
            },
            ensure_ascii=False,
        ),
    }
    if preview_fingerprint is not None:
        payload["preview_fingerprint"] = preview_fingerprint
    return payload


def test_health_route_returns_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/health")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["capabilities"]["web_console"] is True


def test_context_route_returns_project_context(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    write_text_utf8(
        tmp_path / ".agent" / "project.yaml",
        "name: 示例项目\ntech_stack:\n  - python\n  - pytest\n",
    )
    write_text_utf8(
        tmp_path / ".agent" / "commands.yaml",
        "test: python -m pytest -v\nlint: python -m ruff check .\n",
    )
    write_text_utf8(tmp_path / ".agent" / "rules.md", "所有文本使用 UTF-8。\n")
    write_text_utf8(
        tmp_path / ".dev-agent" / "preferences.yaml",
        "language: zh-CN\napproval_mode: confirm\n",
    )
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/context")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["project"] == {
        "name": "示例项目",
        "tech_stack": ["python", "pytest"],
    }
    assert payload["preferences"] == {
        "language": "zh-CN",
        "approval_mode": "confirm",
    }
    assert payload["rules_text"] == "所有文本使用 UTF-8。\n"
    assert payload["scan"]["root"] == str(tmp_path.resolve())
    assert payload["scan"]["languages"] == ["python"]
    assert payload["scan"]["markers"] == ["pyproject.toml"]
    assert payload["scan"]["suggested_commands"] == {
        "test": "python -m pytest",
        "lint": None,
        "typecheck": None,
        "build": None,
    }
    assert set(payload["git"]) == {"status", "diff_stat", "recent_log"}
    assert all(isinstance(value, str) for value in payload["git"].values())
    assert payload["verification_steps"] == [
        {"name": "test", "command": ["python", "-m", "pytest", "-v"]},
        {"name": "lint", "command": ["python", "-m", "ruff", "check", "."]},
    ]


def test_history_route_returns_json(tmp_path) -> None:
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-history-1",
            title="修复中文乱码",
            status="passed",
            summary="UTF-8 修复",
            events=["runtime_started", "runtime_completed"],
            verification=["python -m pytest -v"],
            lessons=["提交前运行完整测试"],
        )
    )
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/history")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["tasks"][0]["task_id"] == "task-history-1"
    assert payload["tasks"][0]["title"] == "修复中文乱码"
    assert payload["tasks"][0]["status"] == "passed"
    assert payload["tasks"][0]["summary"] == "UTF-8 修复"
    assert payload["tasks"][0]["events"] == ["runtime_started", "runtime_completed"]
    assert payload["tasks"][0]["verification"] == ["python -m pytest -v"]
    assert payload["tasks"][0]["lessons"] == ["提交前运行完整测试"]


def test_run_route_rejects_missing_fake_response(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(f"{base_url}/api/run", {"request": "生成计划"})
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "fake_response" in payload["error"]


def test_static_index_route_returns_html(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, body = get_text(f"{base_url}/")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "text/html; charset=utf-8"
    assert "研发助手控制台" in body


def test_static_assets_include_console_interactions(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        index_status, index_type, index_body = get_text(f"{base_url}/")
        css_status, css_type, css_body = get_text(f"{base_url}/static/styles.css")
        js_status, js_type, js_body = get_text(f"{base_url}/static/app.js")
    finally:
        server.shutdown()
        server.server_close()

    assert index_status == HTTPStatus.OK
    assert index_type == "text/html; charset=utf-8"
    assert "Provider plan 审批" in index_body
    assert 'id="context-cards"' in index_body
    assert 'class="context-card-list"' in index_body
    assert '<div id="context-cards" class="context-card-list"></div>' in index_body
    assert '<h3 class="result-heading">原始 JSON</h3>' in index_body
    context_cards_index = index_body.index('id="context-cards"')
    context_json_index = index_body.index('id="context"')
    assert context_cards_index < context_json_index
    assert "history-cards" in index_body
    assert "历史 JSON" in index_body
    assert "provider-plan-form" in index_body
    assert "confirm-provider-apply" in index_body
    assert "provider-preview-cards" in index_body
    assert "provider-audit-cards" in index_body
    assert "原始 JSON" in index_body
    assert "执行结果 JSON" in index_body
    assert css_status == HTTPStatus.OK
    assert css_type == "text/css; charset=utf-8"
    assert "--ink" in css_body
    assert "@media" in css_body
    panel_block = css_body.split(".panel {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "min-width: 0;" in panel_block
    assert ".approval-layout" in css_body
    assert ".danger" in css_body
    assert ".preview-card-list" in css_body
    assert ".preview-card" in css_body
    assert ".risk-badge" in css_body
    assert ".risk-overwrite" in css_body
    assert ".content-preview" in css_body
    assert ".truncation-note" in css_body
    assert ".audit-card-list" in css_body
    assert ".audit-card" in css_body
    assert ".audit-status-badge" in css_body
    assert ".audit-success" in css_body
    assert ".audit-failed" in css_body
    assert ".audit-diff" in css_body
    assert ".history-card-list" in css_body
    assert ".history-card" in css_body
    assert ".history-status-badge" in css_body
    assert ".history-status-passed" in css_body
    assert ".history-status-failed" in css_body
    assert ".history-detail" in css_body
    assert ".context-card-list" in css_body
    assert ".context-card" in css_body
    assert ".context-project-card" in css_body
    assert ".context-git-clean" in css_body
    assert ".context-git-changed" in css_body
    assert ".context-status-badge" in css_body
    assert ".context-command-row" in css_body
    assert ".context-copy-button" in css_body
    assert ".context-copy-status" in css_body
    assert ".context-rule-detail" in css_body
    assert "overflow-wrap: anywhere" in css_body
    assert js_status == HTTPStatus.OK
    assert js_type == "text/javascript; charset=utf-8"
    assert "loadContext" in js_body
    assert "contextCards" in js_body
    assert "clearContextCards" in js_body
    assert "formatContextCommand" in js_body
    assert "collectContextCommands" in js_body
    assert "contextCommandLabel" in js_body
    assert "copyContextCommand" in js_body
    assert "renderContextCards" in js_body
    assert "navigator.clipboard.writeText(command)" in js_body
    assert 'button.textContent = "已复制"' in js_body
    assert 'button.textContent = "复制失败"' in js_body
    assert 'status.setAttribute("role", "status")' in js_body
    load_context_index = js_body.index("async function loadContext")
    render_context_index = js_body.index("renderContextCards(payload)", load_context_index)
    context_json_index = js_body.index('renderJson("context", payload)', load_context_index)
    assert render_context_index < context_json_index
    assert "historyCards" in js_body
    assert "renderHistoryCards" in js_body
    assert "historyStatusLabel" in js_body
    assert "historyStatusClass" in js_body
    assert "clearHistoryCards" in js_body
    assert "appendHistoryList" in js_body
    assert "submitRun" in js_body
    assert "submitProviderPreview" in js_body
    assert "submitProviderApply" in js_body
    assert "resetProviderPreview" in js_body
    assert 'providerForm().addEventListener("input", resetProviderPreview)' in js_body
    assert "需要重新预览" in js_body
    assert "/api/provider-plan/preview" in js_body
    assert "/api/provider-plan/apply" in js_body
    assert "providerPreviewCards" in js_body
    assert "renderProviderPreviewCards" in js_body
    assert "clearProviderPreviewCards" in js_body
    assert "providerAuditCards" in js_body
    assert "renderProviderAuditCards" in js_body
    assert "renderProviderAuditFailure" in js_body
    assert "clearProviderAuditCards" in js_body
    assert "providerRiskLabel" in js_body
    assert "providerRiskClass" in js_body
    assert "execution_error" in js_body
    assert "applied_changes" in js_body
    assert "content_preview_truncated" in js_body
    assert "textContent" in js_body
    load_history_index = js_body.index("async function loadHistory")
    render_history_index = js_body.index("renderHistoryCards(payload)", load_history_index)
    render_json_index = js_body.index('renderJson("history", payload)', load_history_index)
    assert render_history_index < render_json_index
    reset_index = js_body.index("const resetProviderPreview")
    audit_clear_index = js_body.index("clearProviderAuditCards();", reset_index)
    stale_preview_guard_index = js_body.index("if (lastProviderPreview === null)", reset_index)
    assert audit_clear_index < stale_preview_guard_index


def test_web_context_card_javascript_behaviors() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for Web JavaScript behavior tests")

    test_file = Path(__file__).with_name("web_context_cards.test.mjs")
    completed = subprocess.run(
        [node, "--test", str(test_file)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_provider_plan_preview_route_returns_preview_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/preview",
            provider_plan_payload(),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is True
    assert payload["preview_changes"][0]["path"] == "docs/from-web-route.md"
    assert payload["file_diffs"][0]["path"] == "docs/from-web-route.md"
    assert payload["preview_fingerprint"].startswith("sha256:")
    assert not (tmp_path / "docs" / "from-web-route.md").exists()
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_apply_route_writes_file_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        plan_payload = provider_plan_payload(content="确认 route 写入\n")
        preview_status, _preview_type, preview = post_json(
            f"{base_url}/api/provider-plan/preview",
            plan_payload,
        )
        assert preview_status == HTTPStatus.OK
        plan_payload["preview_fingerprint"] = preview["preview_fingerprint"]
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            plan_payload,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is True
    assert payload["applied_changes"][0]["path"] == "docs/from-web-route.md"
    assert payload["preview_changes"][0]["path"] == "docs/from-web-route.md"
    assert payload["preview_changes"][0]["content_preview"] == "确认 route 写入\n"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert "diff_stat" in payload
    assert payload["execution_error"] is None
    assert (tmp_path / "docs" / "from-web-route.md").read_text(encoding="utf-8") == "确认 route 写入\n"
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "Web provider route" in history


def test_provider_plan_apply_route_requires_preview_fingerprint(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            provider_plan_payload(),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "preview_fingerprint is required" in payload["error"]
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_apply_route_rejects_stale_preview_fingerprint(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "版本一\n")
    server, base_url = start_server(tmp_path)
    try:
        plan_payload = provider_plan_payload(
            path="target.md",
            content="批准内容\n",
            action="overwrite_text",
        )
        preview_status, _preview_type, preview = post_json(
            f"{base_url}/api/provider-plan/preview",
            plan_payload,
        )
        assert preview_status == HTTPStatus.OK
        write_text_utf8(tmp_path / "target.md", "版本二\n")
        plan_payload["preview_fingerprint"] = preview["preview_fingerprint"]

        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            plan_payload,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.CONFLICT
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "重新预览" in payload["error"]
    assert (tmp_path / "target.md").read_text(encoding="utf-8") == "版本二\n"
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_preview_route_rejects_bad_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/preview",
            {"request": "坏 Web provider route", "fake_response": '{"summary":'},
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "无法解析 provider 执行计划" in payload["error"]


def test_provider_plan_preview_route_rejects_dangerous_path(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/preview",
            provider_plan_payload(path="../escape.md"),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "执行计划预览失败" in payload["error"]
    assert not (tmp_path.parent / "escape.md").exists()


def test_provider_plan_apply_route_rejects_bad_json_without_writing(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            {
                "request": "坏 apply route",
                "fake_response": '{"summary":',
                "preview_fingerprint": "sha256:unused",
            },
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "无法解析 provider 执行计划" in payload["error"]
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_apply_route_rejects_create_conflict_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "docs" / "from-web-route.md", "已存在\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            provider_plan_payload(preview_fingerprint="sha256:unused"),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "执行计划预览失败" in payload["error"]
    assert (tmp_path / "docs" / "from-web-route.md").read_text(encoding="utf-8") == "已存在\n"
    assert not (tmp_path / ".agent").exists()
