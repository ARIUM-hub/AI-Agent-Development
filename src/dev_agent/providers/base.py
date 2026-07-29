from typing import Protocol

from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderError, ProviderUsage


class ModelProvider(Protocol):
    name: str

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class FakeProvider:
    def __init__(self, name: str, responses: list[str]) -> None:
        self.name = name
        self._responses = list(responses)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not self._responses:
            raise ProviderError("没有可用的 fake provider 响应")
        text = self._responses.pop(0)
        return ModelResponse(
            provider=self.name,
            text=text,
            usage=ProviderUsage(
                request_count=1,
                input_chars=len(request.prompt),
                output_chars=len(text),
            ),
        )
