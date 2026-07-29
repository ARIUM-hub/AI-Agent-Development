from dataclasses import dataclass

from dev_agent.providers.base import ModelProvider
from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderError


@dataclass(frozen=True)
class BudgetConfig:
    max_requests: int = 8
    max_output_chars: int = 12000
    max_failures: int = 2


class BudgetExceeded(RuntimeError):
    """Raised when model safety controls stop further provider calls."""


@dataclass
class BudgetState:
    requests: int = 0
    output_chars: int = 0
    failures: int = 0
    open: bool = False


class CircuitBreaker:
    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self.state = BudgetState()

    def before_request(self) -> None:
        if self.state.open:
            raise BudgetExceeded("模型请求已停止：供应商已进入冷却。")
        if self.state.requests >= self.config.max_requests:
            raise BudgetExceeded("模型请求已停止：单任务请求次数超过预算。")

    def after_success(self, response: ModelResponse) -> None:
        self.state.requests += response.usage.request_count
        self.state.output_chars += response.usage.output_chars
        if self.state.output_chars > self.config.max_output_chars:
            self.state.open = True
            raise BudgetExceeded("模型请求已停止：输出预算已超过限制。")

    def after_failure(self) -> None:
        self.state.failures += 1
        if self.state.failures >= self.config.max_failures:
            self.state.open = True


class ProtectedProvider:
    def __init__(self, provider: ModelProvider, breaker: CircuitBreaker) -> None:
        self.provider = provider
        self.breaker = breaker
        self.name = provider.name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.breaker.before_request()
        try:
            response = self.provider.complete(request)
        except ProviderError:
            self.breaker.after_failure()
            raise
        self.breaker.after_success(response)
        return response
