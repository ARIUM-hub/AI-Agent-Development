import pytest

from dev_agent.providers.base import FakeProvider
from dev_agent.providers.budget import BudgetConfig, BudgetExceeded, CircuitBreaker, ProtectedProvider
from dev_agent.providers.models import ModelRequest, ProviderError


def test_fake_provider_returns_configured_response() -> None:
    provider = FakeProvider(name="fake-main", responses=["计划：读取文件并运行测试。"])

    response = provider.complete(ModelRequest(prompt="帮我实现登录接口"))

    assert response.provider == "fake-main"
    assert response.text == "计划：读取文件并运行测试。"
    assert response.usage.request_count == 1
    assert response.usage.output_chars == len("计划：读取文件并运行测试。")


def test_fake_provider_raises_when_no_response_left() -> None:
    provider = FakeProvider(name="fake-main", responses=[])

    with pytest.raises(ProviderError, match="没有可用的 fake provider 响应"):
        provider.complete(ModelRequest(prompt="继续"))


def test_protected_provider_blocks_when_request_limit_is_exceeded() -> None:
    provider = FakeProvider(name="fake-main", responses=["第一次", "第二次"])
    breaker = CircuitBreaker(BudgetConfig(max_requests=1, max_output_chars=100))
    protected = ProtectedProvider(provider, breaker)

    first = protected.complete(ModelRequest(prompt="第一次请求"))

    assert first.text == "第一次"
    with pytest.raises(BudgetExceeded, match="模型请求已停止"):
        protected.complete(ModelRequest(prompt="第二次请求"))


def test_protected_provider_blocks_when_output_budget_is_exceeded() -> None:
    provider = FakeProvider(name="fake-main", responses=["这段输出会超过预算"])
    breaker = CircuitBreaker(BudgetConfig(max_requests=3, max_output_chars=3))
    protected = ProtectedProvider(provider, breaker)

    with pytest.raises(BudgetExceeded, match="输出预算"):
        protected.complete(ModelRequest(prompt="生成方案"))


def test_circuit_breaker_opens_after_failures() -> None:
    provider = FakeProvider(name="fake-main", responses=[])
    breaker = CircuitBreaker(BudgetConfig(max_requests=3, max_failures=1))
    protected = ProtectedProvider(provider, breaker)

    with pytest.raises(ProviderError):
        protected.complete(ModelRequest(prompt="会失败"))

    with pytest.raises(BudgetExceeded, match="供应商已进入冷却"):
        protected.complete(ModelRequest(prompt="不要继续请求"))
