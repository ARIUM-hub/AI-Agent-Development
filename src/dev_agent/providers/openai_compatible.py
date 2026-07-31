import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dev_agent.config.provider import OpenAICompatibleConfig
from dev_agent.providers.models import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderUsage,
)


MAX_RESPONSE_BYTES = 256 * 1024
USER_AGENT = "dev-agent/0.1 openai-compatible"


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, config: OpenAICompatibleConfig, api_key: str) -> None:
        self.config = config
        self._api_key = api_key

    def complete(self, request: ModelRequest) -> ModelResponse:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append(
                {"role": "system", "content": request.system_prompt}
            )
        messages.append({"role": "user", "content": request.prompt})
        body = json.dumps(
            {"model": self.config.model, "messages": messages},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        http_request = Request(
            f"{self.config.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(
                http_request,
                timeout=self.config.timeout_seconds,
            ) as http_response:
                raw = http_response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ProviderError(
                f"模型请求失败：HTTP {exc.code}，未自动重试"
            ) from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("模型请求超时，未自动重试") from None
        except ValueError:
            raise ProviderError("无法发送模型请求，认证信息格式无效") from None
        except (URLError, OSError):
            raise ProviderError("无法连接模型服务，未自动重试") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("模型响应超过 256 KiB 上限")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            raise ProviderError("模型响应不是有效的 UTF-8") from None
        except json.JSONDecodeError:
            raise ProviderError("模型响应 JSON 结构无效") from None
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("模型响应 JSON 结构无效") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(
                "模型响应缺少非空 choices[0].message.content"
            )

        input_chars = len(request.prompt) + len(request.system_prompt or "")
        return ModelResponse(
            provider=self.name,
            text=content,
            usage=ProviderUsage(
                request_count=1,
                input_chars=input_chars,
                output_chars=len(content),
            ),
        )
