from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    task_id: str | None = None
    system_prompt: str | None = None


@dataclass(frozen=True)
class ProviderUsage:
    request_count: int
    input_chars: int
    output_chars: int


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    text: str
    usage: ProviderUsage


class ProviderError(RuntimeError):
    """Raised when a model provider cannot produce a response."""
