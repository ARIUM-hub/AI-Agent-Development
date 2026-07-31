from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Any

import pytest

from dev_agent.config.provider import OpenAICompatibleConfig
from dev_agent.providers.models import ModelRequest, ProviderError
from dev_agent.providers.openai_compatible import (
    MAX_RESPONSE_BYTES,
    OpenAICompatibleProvider,
)


class RecordingServer(HTTPServer):
    request_count: int
    requests: list[dict[str, object]]
    response_body: bytes
    response_status: int
    response_delay: float


class RecordingHandler(BaseHTTPRequestHandler):
    server: RecordingServer

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.request_count += 1
        self.server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "user_agent": self.headers.get("User-Agent"),
                "json": json.loads(body.decode("utf-8")),
            }
        )
        if self.server.response_delay:
            time.sleep(self.server.response_delay)
        try:
            self.send_response(self.server.response_status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(self.server.response_body)))
            self.end_headers()
            self.wfile.write(self.server.response_body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def local_server() -> Iterator[Callable[..., tuple[RecordingServer, str]]]:
    servers: list[tuple[RecordingServer, threading.Thread]] = []

    def start(
        payload: object | None = None,
        *,
        raw_body: bytes | None = None,
        status: int = 200,
        delay: float = 0,
    ) -> tuple[RecordingServer, str]:
        body = (
            raw_body
            if raw_body is not None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        server = RecordingServer(("127.0.0.1", 0), RecordingHandler)
        server.request_count = 0
        server.requests = []
        server.response_body = body
        server.response_status = status
        server.response_delay = delay
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        thread.start()
        servers.append((server, thread))
        host, port = server.server_address
        return server, f"http://{host}:{port}"

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def make_provider(
    base_url: str,
    *,
    api_key: str = "secret-for-test",
    timeout_seconds: float = 2,
) -> OpenAICompatibleProvider:
    config = OpenAICompatibleConfig(
        base_url=f"{base_url}/v1",
        model="model-name",
        api_key_env="TEST_KEY",
        timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
    )
    return OpenAICompatibleProvider(config, api_key=api_key)


def successful_payload(content: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": content}}]}


def test_posts_chat_completions_once_with_utf8_messages(local_server) -> None:
    plan_text = '{"summary":"中文计划","operations":[]}'
    server, base_url = local_server(successful_payload(plan_text))
    provider = make_provider(base_url)

    response = provider.complete(
        ModelRequest(prompt="用户中文", system_prompt="系统约束")
    )

    assert server.request_count == 1
    request = server.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["authorization"] == "Bearer secret-for-test"
    assert request["content_type"] == "application/json; charset=utf-8"
    assert request["user_agent"] == "dev-agent/0.1 openai-compatible"
    assert request["json"] == {
        "model": "model-name",
        "messages": [
            {"role": "system", "content": "系统约束"},
            {"role": "user", "content": "用户中文"},
        ],
    }
    assert set(request["json"]) == {"model", "messages"}  # type: ignore[arg-type]
    assert response.provider == "openai-compatible"
    assert response.text == plan_text
    assert response.usage.request_count == 1
    assert response.usage.input_chars == len("系统约束用户中文")
    assert response.usage.output_chars == len(plan_text)


def test_omits_system_message_when_request_has_no_system_prompt(local_server) -> None:
    server, base_url = local_server(successful_payload("ok"))

    make_provider(base_url).complete(ModelRequest(prompt="only user"))

    assert server.requests[0]["json"] == {
        "model": "model-name",
        "messages": [{"role": "user", "content": "only user"}],
    }


@pytest.mark.parametrize("status", [401, 403, 408, 429, 500, 503])
def test_http_errors_are_chinese_redacted_and_not_retried(
    local_server,
    status: int,
) -> None:
    server, base_url = local_server({}, status=status)

    with pytest.raises(ProviderError, match=f"HTTP {status}") as caught:
        make_provider(base_url).complete(ModelRequest(prompt="请求"))

    assert server.request_count == 1
    assert "未自动重试" in str(caught.value)
    assert "secret-for-test" not in str(caught.value)


def test_rejects_response_larger_than_256_kib(local_server) -> None:
    server, base_url = local_server(raw_body=b"x" * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(ProviderError, match="256 KiB"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))

    assert server.request_count == 1


def test_rejects_non_utf8_response(local_server) -> None:
    server, base_url = local_server(raw_body=b"\xff\xfe")

    with pytest.raises(ProviderError, match="UTF-8"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))

    assert server.request_count == 1


def test_rejects_malformed_json(local_server) -> None:
    server, base_url = local_server(raw_body=b"{not-json")

    with pytest.raises(ProviderError, match="JSON 结构"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))

    assert server.request_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        successful_payload(""),
        successful_payload("   "),
        successful_payload(["not", "text"]),
    ],
)
def test_rejects_missing_or_empty_content(
    local_server,
    payload: dict[str, Any],
) -> None:
    server, base_url = local_server(payload)

    with pytest.raises(ProviderError, match="模型响应"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))

    assert server.request_count == 1


def test_timeout_is_not_retried(local_server) -> None:
    server, base_url = local_server(successful_payload("late"), delay=0.2)

    with pytest.raises(ProviderError, match="超时") as caught:
        make_provider(base_url, timeout_seconds=0.05).complete(
            ModelRequest(prompt="请求")
        )

    assert server.request_count == 1
    assert "未自动重试" in str(caught.value)
    assert "secret-for-test" not in str(caught.value)


def test_connection_failure_is_provider_error() -> None:
    probe = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    host, port = probe.server_address
    probe.server_close()

    with pytest.raises(ProviderError, match="无法连接") as caught:
        make_provider(f"http://{host}:{port}").complete(ModelRequest(prompt="请求"))

    assert "secret-for-test" not in str(caught.value)
