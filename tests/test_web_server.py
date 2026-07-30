import json
from http import HTTPStatus
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dev_agent.encoding import write_text_utf8
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


def provider_plan_payload(path="docs/from-web-route.md", content="来自 Web route\n"):
    return {
        "request": "Web provider route",
        "fake_response": json.dumps(
            {
                "summary": "创建 Web route 文件",
                "operations": [
                    {
                        "action": "create_text",
                        "path": path,
                        "content": content,
                    }
                ],
            },
            ensure_ascii=False,
        ),
    }


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
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/context")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["scan"]["languages"] == ["python"]


def test_history_route_returns_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/history")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["tasks"] == []


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
    assert "provider-plan-form" in index_body
    assert "confirm-provider-apply" in index_body
    assert "provider-preview-cards" in index_body
    assert "原始 JSON" in index_body
    assert css_status == HTTPStatus.OK
    assert css_type == "text/css; charset=utf-8"
    assert "--ink" in css_body
    assert "@media" in css_body
    assert ".approval-layout" in css_body
    assert ".danger" in css_body
    assert ".preview-card-list" in css_body
    assert ".preview-card" in css_body
    assert ".risk-badge" in css_body
    assert ".risk-overwrite" in css_body
    assert ".content-preview" in css_body
    assert ".truncation-note" in css_body
    assert "overflow-wrap: anywhere" in css_body
    assert js_status == HTTPStatus.OK
    assert js_type == "text/javascript; charset=utf-8"
    assert "loadContext" in js_body
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
    assert "providerRiskLabel" in js_body
    assert "providerRiskClass" in js_body
    assert "content_preview_truncated" in js_body
    assert "textContent" in js_body


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
    assert not (tmp_path / "docs" / "from-web-route.md").exists()
    assert not (tmp_path / ".agent").exists()


def test_provider_plan_apply_route_writes_file_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(
            f"{base_url}/api/provider-plan/apply",
            provider_plan_payload(content="确认 route 写入\n"),
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
            {"request": "坏 apply route", "fake_response": '{"summary":'},
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
            provider_plan_payload(),
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
