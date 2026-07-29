import pytest

from dev_agent.providers.base import FakeProvider
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
