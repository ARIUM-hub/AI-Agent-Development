from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
from urllib.parse import urlparse

from dev_agent.execution.plan import StaleExecutionPreviewError
from dev_agent.web.api import (
    apply_provider_plan_task,
    build_context_payload,
    build_health_payload,
    build_history_payload,
    preview_provider_plan_task,
    run_dry_run_task,
)


STATIC_DIR = Path(__file__).with_name("static")


class DevAgentHttpHandler(SimpleHTTPRequestHandler):
    repo_root: Path
    home_dir: Path

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def log_message(self, format: str, *args: object) -> None:
        return None

    def handle_request(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send_json(HTTPStatus.OK, build_health_payload(self.repo_root))
            elif path == "/api/context":
                self._send_json(HTTPStatus.OK, build_context_payload(self.repo_root, self.home_dir))
            elif path == "/api/history":
                self._send_json(HTTPStatus.OK, build_history_payload(self.repo_root))
            elif path == "/api/run" and self.command == "POST":
                body = self._read_json_body()
                payload = run_dry_run_task(
                    repo_root=self.repo_root,
                    home_dir=self.home_dir,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
            elif path == "/api/provider-plan/preview" and self.command == "POST":
                body = self._read_json_body()
                payload = preview_provider_plan_task(
                    repo_root=self.repo_root,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
            elif path == "/api/provider-plan/apply" and self.command == "POST":
                body = self._read_json_body()
                payload = apply_provider_plan_task(
                    repo_root=self.repo_root,
                    home_dir=self.home_dir,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                    preview_fingerprint=str(body.get("preview_fingerprint", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
            elif path == "/":
                self._send_static("index.html", "text/html; charset=utf-8")
            elif path == "/static/styles.css":
                self._send_static("styles.css", "text/css; charset=utf-8")
            elif path == "/static/app.js":
                self._send_static("app.js", "text/javascript; charset=utf-8")
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
        except StaleExecutionPreviewError as exc:
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, filename: str, content_type: str) -> None:
        body = (STATIC_DIR / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(repo_root: Path, home_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    class BoundHandler(DevAgentHttpHandler):
        pass

    BoundHandler.repo_root = repo_root
    BoundHandler.home_dir = home_dir
    return HTTPServer((host, port), BoundHandler)
