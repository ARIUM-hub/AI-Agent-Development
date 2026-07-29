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
