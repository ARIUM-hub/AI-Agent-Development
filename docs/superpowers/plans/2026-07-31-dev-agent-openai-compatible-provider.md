# OpenAI-Compatible Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为研发助手 CLI 增加显式启用、单请求、无重试的 `/v1/chat/completions` Provider，并把严格 JSON 计划安全地接入现有预览和确认执行流程。

**Architecture:** 用户级配置与密钥解析、HTTP 传输、计划准备、任务执行保持四个边界。联网准备阶段只调用一次 Provider 并返回不可变的响应、计划和预览；确认执行阶段把该响应注入现有 `LocalTaskRunner`，不再联网。默认 FakeProvider、计划文件和 Web 流程保持离线兼容。

**Tech Stack:** Python 3.11、标准库 `urllib.request` / `json` / `dataclasses`、现有 PyYAML、pytest、进程内 `HTTPServer`。

---

## File Structure

- Create: `src/dev_agent/config/provider.py`：严格读取 `~/.dev-agent/provider.yaml`，校验 URL 与字段，并从环境映射解析密钥。
- Create: `src/dev_agent/providers/openai_compatible.py`：发送一次同步 Chat Completions 请求、限制响应体并转换协议错误。
- Create: `src/dev_agent/runtime/provider_plan.py`：构造严格计划请求，使用单请求预算，解析并预览计划。
- Modify: `src/dev_agent/providers/models.py`：为请求增加可选 system prompt，为运行时复用保留完整响应对象。
- Modify: `src/dev_agent/runtime/prompts.py`：增加严格 JSON 执行计划的 system/user 提示构造。
- Modify: `src/dev_agent/runtime/models.py`：让任务选项携带已准备响应和模型名，让结果公开非敏感 Provider 元数据。
- Modify: `src/dev_agent/runtime/runner.py`：优先复用已准备响应，禁止 apply 阶段二次调用 Provider。
- Modify: `src/dev_agent/cli.py`：增加 `--provider`、参数冲突校验、真实 Provider 准备与稳定 JSON 输出。
- Test: `tests/test_provider_config.py`：配置结构、安全 URL、密钥环境变量和脱敏。
- Test: `tests/test_openai_compatible_provider.py`：本地 HTTP 协议、UTF-8、上限和错误路径。
- Test: `tests/test_runtime_provider_plan.py`：单请求准备、严格解析、无副作用预览。
- Modify: `tests/test_runtime_runner.py`：准备响应复用和请求次数断言。
- Modify: `tests/test_cli.py`：默认离线兼容、参数冲突、真实模式预览与 apply 端到端。

### Task 1: Provider 配置与密钥边界

**Files:**
- Create: `tests/test_provider_config.py`
- Create: `src/dev_agent/config/provider.py`

- [ ] **Step 1: 写配置加载的失败测试**

```python
from pathlib import Path

import pytest

from dev_agent.config.provider import (
    ProviderConfigError,
    load_openai_compatible_config,
    resolve_openai_compatible_api_key,
)


def write_config(home: Path, text: str) -> None:
    path = home / ".dev-agent" / "provider.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


def test_loads_https_config_and_resolves_key_from_environment(tmp_path: Path) -> None:
    write_config(tmp_path, """openai_compatible:
  base_url: https://example.com/v1/
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
  timeout_seconds: 45
""")
    config = load_openai_compatible_config(tmp_path)
    assert config.base_url == "https://example.com/v1"
    assert config.model == "model-name"
    assert config.timeout_seconds == 45
    assert resolve_openai_compatible_api_key(config, {"DEV_AGENT_API_KEY": "秘密-key"}) == "秘密-key"
    assert "秘密-key" not in repr(config)


@pytest.mark.parametrize("base_url", [
    "http://example.com/v1",
    "https://user:pass@example.com/v1",
    "https://example.com/v1?x=1",
    "https://example.com/v1#fragment",
])
def test_rejects_unsafe_urls(tmp_path: Path, base_url: str) -> None:
    write_config(tmp_path, f"""openai_compatible:
  base_url: {base_url}
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
""")
    with pytest.raises(ProviderConfigError):
        load_openai_compatible_config(tmp_path)


def test_allows_loopback_http(tmp_path: Path) -> None:
    write_config(tmp_path, """openai_compatible:
  base_url: http://127.0.0.1:8080/v1
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
""")
    assert load_openai_compatible_config(tmp_path).base_url == "http://127.0.0.1:8080/v1"


@pytest.mark.parametrize("field", ["api_key", "token", "secret", "password", "authorization"])
def test_rejects_plaintext_secret_fields(tmp_path: Path, field: str) -> None:
    write_config(tmp_path, f"""openai_compatible:
  base_url: https://example.com/v1
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
  {field}: do-not-store
""")
    with pytest.raises(ProviderConfigError) as caught:
        load_openai_compatible_config(tmp_path)
    assert "do-not-store" not in str(caught.value)


def test_missing_environment_key_is_redacted(tmp_path: Path) -> None:
    write_config(tmp_path, """openai_compatible:
  base_url: https://example.com/v1
  model: model-name
  api_key_env: DEV_AGENT_API_KEY
""")
    config = load_openai_compatible_config(tmp_path)
    with pytest.raises(ProviderConfigError, match="环境变量 DEV_AGENT_API_KEY"):
        resolve_openai_compatible_api_key(config, {})
```

```python
def test_missing_config_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigError, match="配置文件不存在"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize("document", ["- item\n", "{}\n", "openai_compatible: []\n"])
def test_requires_openai_compatible_mapping(tmp_path: Path, document: str) -> None:
    write_config(tmp_path, document)
    with pytest.raises(ProviderConfigError, match="openai_compatible 映射"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("unknown: value", "未知字段"),
        ("model: ''", "model 必须是非空字符串"),
        ("api_key_env: BAD-NAME", "环境变量名"),
        ("timeout_seconds: text", "1 至 300"),
        ("timeout_seconds: 0", "1 至 300"),
        ("timeout_seconds: 301", "1 至 300"),
    ],
)
def test_rejects_invalid_fields(tmp_path: Path, extra: str, message: str) -> None:
    values = {
        "base_url": "https://example.com/v1",
        "model": "model-name",
        "api_key_env": "DEV_AGENT_API_KEY",
    }
    key, value = extra.split(":", 1)
    values[key] = value.strip().strip("'")
    if key == "timeout_seconds" and value.strip().isdigit():
        values[key] = int(value.strip())
    body = "openai_compatible:\n" + "".join(f"  {name}: {item}\n" for name, item in values.items())
    write_config(tmp_path, body)
    with pytest.raises(ProviderConfigError, match=message):
        load_openai_compatible_config(tmp_path)
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_provider_config.py -q`

Expected: collection error，提示 `No module named 'dev_agent.config.provider'`。

- [ ] **Step 3: 写最小严格配置实现**

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

from dev_agent.encoding import read_text_utf8


_ALLOWED_FIELDS = {"base_url", "model", "api_key_env", "timeout_seconds"}
_SENSITIVE_FIELDS = {"api_key", "token", "secret", "password", "authorization", "access_token"}
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ProviderConfigError(ValueError):
    """Provider 用户配置无效。"""


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: int = 60


def _required_text(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"openai_compatible.{field} 必须是非空字符串")
    return value.strip()


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderConfigError("openai_compatible.base_url 不是安全的 API 根地址")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS):
        raise ProviderConfigError("openai_compatible.base_url 必须使用 HTTPS；仅回环地址可使用 HTTP")
    return value.rstrip("/")


def load_openai_compatible_config(home_dir: Path) -> OpenAICompatibleConfig:
    path = home_dir.resolve() / ".dev-agent" / "provider.yaml"
    if not path.is_file():
        raise ProviderConfigError(f"Provider 配置文件不存在：{path}")
    try:
        document = yaml.safe_load(read_text_utf8(path))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProviderConfigError("无法以 UTF-8 读取 Provider 配置") from exc
    if not isinstance(document, dict) or not isinstance(document.get("openai_compatible"), dict):
        raise ProviderConfigError("Provider 配置必须包含 openai_compatible 映射")
    data = document["openai_compatible"]
    sensitive = sorted(str(key) for key in data if str(key).lower() in _SENSITIVE_FIELDS)
    if sensitive:
        raise ProviderConfigError(f"Provider 配置禁止保存敏感字段：{', '.join(sensitive)}")
    unknown = sorted(str(key) for key in data if key not in _ALLOWED_FIELDS)
    if unknown:
        raise ProviderConfigError(f"Provider 配置包含未知字段：{', '.join(unknown)}")
    model = _required_text(data, "model")
    api_key_env = _required_text(data, "api_key_env")
    if not _ENV_NAME.fullmatch(api_key_env):
        raise ProviderConfigError("openai_compatible.api_key_env 不是合法的环境变量名")
    timeout = data.get("timeout_seconds", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise ProviderConfigError("openai_compatible.timeout_seconds 必须是 1 至 300 的整数")
    return OpenAICompatibleConfig(
        base_url=_validated_base_url(_required_text(data, "base_url")),
        model=model,
        api_key_env=api_key_env,
        timeout_seconds=timeout,
    )


def resolve_openai_compatible_api_key(
    config: OpenAICompatibleConfig,
    environ: Mapping[str, str],
) -> str:
    value = environ.get(config.api_key_env, "").strip()
    if not value:
        raise ProviderConfigError(f"环境变量 {config.api_key_env} 未设置或为空")
    return value
```

- [ ] **Step 4: 运行配置测试确认 GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_provider_config.py -q`

Expected: all tests passed。

- [ ] **Step 5: 提交配置边界**

```powershell
git add src/dev_agent/config/provider.py tests/test_provider_config.py
git commit -m "feat: validate provider configuration"
```

### Task 2: OpenAI-Compatible HTTP Provider

**Files:**
- Create: `tests/test_openai_compatible_provider.py`
- Create: `src/dev_agent/providers/openai_compatible.py`
- Modify: `src/dev_agent/providers/models.py:4-7`

- [ ] **Step 1: 写本地 HTTPServer 协议测试**

测试文件定义 `RecordingHandler(BaseHTTPRequestHandler)` 和在后台线程启动的上下文管理器；handler 只服务本机随机端口，记录每个 POST 的 path、headers、body，并可返回预设 status/body/delay。核心测试代码：

```python
def test_posts_chat_completions_once_with_utf8_messages(local_server) -> None:
    server, base_url = local_server({
        "choices": [{"message": {"content": "{\"summary\":\"中文计划\",\"operations\":[]}"}}]
    })
    provider = OpenAICompatibleProvider(
        OpenAICompatibleConfig(base_url=f"{base_url}/v1", model="model-name", api_key_env="KEY", timeout_seconds=2),
        api_key="秘密-key",
    )
    response = provider.complete(ModelRequest(prompt="用户中文", system_prompt="系统约束"))
    assert server.request_count == 1
    request = server.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["authorization"] == "Bearer 秘密-key"
    assert request["content_type"] == "application/json; charset=utf-8"
    assert request["json"] == {
        "model": "model-name",
        "messages": [
            {"role": "system", "content": "系统约束"},
            {"role": "user", "content": "用户中文"},
        ],
    }
    assert response.provider == "openai-compatible"
    assert response.text.startswith('{"summary":"中文计划"')
    assert response.usage.request_count == 1
```

```python
@pytest.mark.parametrize("status", [401, 403, 408, 429, 500, 503])
def test_http_errors_are_chinese_redacted_and_not_retried(local_server, status) -> None:
    server, base_url = local_server({}, status=status)
    provider = make_provider(base_url, api_key="secret-for-test")
    with pytest.raises(ProviderError, match=f"HTTP {status}") as caught:
        provider.complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1
    assert "secret-for-test" not in str(caught.value)

def test_rejects_response_larger_than_256_kib(local_raw_server) -> None:
    server, base_url = local_raw_server(b"x" * (256 * 1024 + 1))
    with pytest.raises(ProviderError, match="256 KiB"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1


def test_rejects_non_utf8_response(local_raw_server) -> None:
    server, base_url = local_raw_server(b"\xff\xfe")
    with pytest.raises(ProviderError, match="UTF-8"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1


def test_rejects_malformed_json(local_raw_server) -> None:
    server, base_url = local_raw_server(b"{not-json")
    with pytest.raises(ProviderError, match="JSON 结构"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}])
def test_rejects_missing_or_empty_content(local_server, payload) -> None:
    server, base_url = local_server(payload)
    with pytest.raises(ProviderError, match="响应"):
        make_provider(base_url).complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1


def test_timeout_is_not_retried(local_server) -> None:
    server, base_url = local_server({}, delay=0.2)
    with pytest.raises(ProviderError, match="超时"):
        make_provider(base_url, timeout_seconds=0.05).complete(ModelRequest(prompt="请求"))
    assert server.request_count == 1


def test_connection_failure_is_provider_error(unused_tcp_port) -> None:
    provider = make_provider(f"http://127.0.0.1:{unused_tcp_port}")
    with pytest.raises(ProviderError, match="无法连接"):
        provider.complete(ModelRequest(prompt="请求"))
```

每个失败测试断言 `ProviderError`、服务端 `request_count <= 1`，以及异常文本不含测试密钥。

- [ ] **Step 2: 运行测试确认 RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_openai_compatible_provider.py -q`

Expected: collection error，提示 `No module named 'dev_agent.providers.openai_compatible'` 或 `ModelRequest` 不接受 `system_prompt`。

- [ ] **Step 3: 扩展 ModelRequest 并实现一次请求 Provider**

`src/dev_agent/providers/models.py`：

```python
@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    task_id: str | None = None
    system_prompt: str | None = None
```

`src/dev_agent/providers/openai_compatible.py`：

```python
from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dev_agent.config.provider import OpenAICompatibleConfig
from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderError, ProviderUsage


MAX_RESPONSE_BYTES = 256 * 1024
USER_AGENT = "dev-agent/0.1 openai-compatible"


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, config: OpenAICompatibleConfig, api_key: str) -> None:
        self.config = config
        self._api_key = api_key

    def complete(self, request: ModelRequest) -> ModelResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
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
            with urlopen(http_request, timeout=self.config.timeout_seconds) as http_response:
                raw = http_response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ProviderError(f"模型请求失败：HTTP {exc.code}，未自动重试") from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("模型请求超时，未自动重试") from None
        except (URLError, OSError):
            raise ProviderError("无法连接模型服务，未自动重试") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("模型响应超过 256 KiB 上限")
        try:
            payload = json.loads(raw.decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except UnicodeDecodeError:
            raise ProviderError("模型响应不是有效的 UTF-8") from None
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise ProviderError("模型响应 JSON 结构无效") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("模型响应缺少非空 choices[0].message.content")
        input_chars = len(request.prompt) + len(request.system_prompt or "")
        return ModelResponse(
            provider=self.name,
            text=content,
            usage=ProviderUsage(request_count=1, input_chars=input_chars, output_chars=len(content)),
        )
```

- [ ] **Step 4: 运行 Provider 测试确认 GREEN，并回归预算测试**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_openai_compatible_provider.py tests/test_provider_budget.py -q`

Expected: all tests passed，且每个服务端断言请求次数不超过 1。

- [ ] **Step 5: 提交 HTTP Provider**

```powershell
git add src/dev_agent/providers/models.py src/dev_agent/providers/openai_compatible.py tests/test_openai_compatible_provider.py
git commit -m "feat: add openai-compatible provider"
```

### Task 3: 严格计划提示与单请求准备流程

**Files:**
- Modify: `src/dev_agent/runtime/prompts.py:1-32`
- Create: `src/dev_agent/runtime/provider_plan.py`
- Create: `tests/test_runtime_provider_plan.py`

- [ ] **Step 1: 写准备流程失败测试**

```python
from pathlib import Path

import pytest

from dev_agent.encoding import write_text_utf8
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.providers.models import ModelRequest, ModelResponse, ProviderUsage
from dev_agent.runtime.provider_plan import prepare_provider_execution_plan


class CountingProvider:
    name = "counting"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            provider=self.name,
            text=self.text,
            usage=ProviderUsage(1, len(request.prompt), len(self.text)),
        )


def test_prepares_strict_plan_and_preview_with_one_request(tmp_path: Path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", '[project]\nname = "sample"\n')
    provider = CountingProvider('{"summary":"创建说明","operations":[{"action":"create_text","path":"docs/provider.md","content":"中文内容\\n"}]}')
    prepared = prepare_provider_execution_plan(
        repo_root=tmp_path,
        home_dir=tmp_path,
        user_request="创建说明",
        provider=provider,
        model="model-name",
    )
    assert len(provider.requests) == 1
    assert provider.requests[0].system_prompt is not None
    assert "只能输出一个 JSON 对象" in provider.requests[0].system_prompt
    assert "源码正文" not in provider.requests[0].prompt
    assert prepared.provider_name == "counting"
    assert prepared.model == "model-name"
    assert prepared.execution_plan.summary == "创建说明"
    assert prepared.preview_result.preview_fingerprint.startswith("sha256:")
    assert not (tmp_path / "docs" / "provider.md").exists()
    assert not (tmp_path / ".agent").exists()


def test_invalid_provider_plan_fails_without_history_or_write(tmp_path: Path) -> None:
    provider = CountingProvider("```json\n{}\n```")
    with pytest.raises(ExecutionPlanError, match="无法解析 provider 执行计划"):
        prepare_provider_execution_plan(tmp_path, tmp_path, "坏计划", provider, "model-name")
    assert len(provider.requests) == 1
    assert not (tmp_path / ".agent").exists()


def test_output_budget_failure_does_not_retry(tmp_path: Path) -> None:
    provider = CountingProvider("x" * 20_001)
    with pytest.raises(Exception, match="输出预算"):
        prepare_provider_execution_plan(tmp_path, tmp_path, "超限", provider, "model-name")
    assert len(provider.requests) == 1
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_provider_plan.py -q`

Expected: collection error，提示 `No module named 'dev_agent.runtime.provider_plan'`。

- [ ] **Step 3: 新增严格提示与准备对象**

在 `runtime/prompts.py` 增加：

```python
STRICT_EXECUTION_PLAN_SYSTEM_PROMPT = """你是研发助手的执行计划生成器。
只能输出一个 JSON 对象，不得输出 Markdown fence、解释文字或对象外字符。
顶层必须且只能包含 summary 和 operations；operations 必须是数组。
每个操作必须且只能包含 action、path、content。
action 只能是 create_text、overwrite_text 或 append_text。
path 必须是仓库内相对路径；禁止绝对路径、..、.git、.agent、命令执行和 Git 写操作。
content 必须是 UTF-8 文本。不要声称已经执行、验证或写入任何内容。"""


def build_provider_plan_prompt(context: RuntimeContext) -> str:
    return build_task_prompt(context) + "\n请根据以上上下文返回严格 JSON 执行计划。"
```

创建 `runtime/provider_plan.py`：

```python
from dataclasses import dataclass
from pathlib import Path

from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionPlan, ExecutionResult
from dev_agent.execution.provider_plan import parse_provider_execution_plan
from dev_agent.providers.base import ModelProvider
from dev_agent.providers.budget import BudgetConfig, CircuitBreaker, ProtectedProvider
from dev_agent.providers.models import ModelRequest, ModelResponse
from dev_agent.runtime.context import resolve_runtime_context
from dev_agent.runtime.prompts import STRICT_EXECUTION_PLAN_SYSTEM_PROMPT, build_provider_plan_prompt


@dataclass(frozen=True)
class ProviderPlanPreparation:
    provider_name: str
    model: str
    response: ModelResponse
    execution_plan: ExecutionPlan
    preview_result: ExecutionResult


def prepare_provider_execution_plan(
    repo_root: Path,
    home_dir: Path,
    user_request: str,
    provider: ModelProvider,
    model: str,
) -> ProviderPlanPreparation:
    context = resolve_runtime_context(repo_root, home_dir, user_request)
    prompt = build_provider_plan_prompt(context)
    protected = ProtectedProvider(
        provider,
        CircuitBreaker(BudgetConfig(max_requests=1, max_failures=1, max_output_chars=20_000)),
    )
    response = protected.complete(ModelRequest(prompt=prompt, system_prompt=STRICT_EXECUTION_PLAN_SYSTEM_PROMPT))
    execution_plan = parse_provider_execution_plan(response.text)
    preview_result = ExecutionPlanApplier(repo_root).preview(execution_plan)
    return ProviderPlanPreparation(response.provider, model, response, execution_plan, preview_result)
```

- [ ] **Step 4: 运行准备流程和提示测试确认 GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_provider_plan.py tests/test_runtime_runner.py::test_build_task_prompt_includes_request_context_memory_and_verification -q`

Expected: all tests passed。

- [ ] **Step 5: 提交单请求准备流程**

```powershell
git add src/dev_agent/runtime/prompts.py src/dev_agent/runtime/provider_plan.py tests/test_runtime_provider_plan.py
git commit -m "feat: prepare provider execution plans"
```

### Task 4: 运行时复用已准备响应

**Files:**
- Modify: `src/dev_agent/runtime/models.py:24-47`
- Modify: `src/dev_agent/runtime/runner.py:20-104`
- Modify: `tests/test_runtime_runner.py`

- [ ] **Step 1: 写 apply 不再次调用 Provider 的失败测试**

```python
def test_local_task_runner_reuses_prepared_response_without_provider_call(tmp_path: Path) -> None:
    class FailingProvider:
        name = "must-not-run"
        def complete(self, request):
            raise AssertionError("prepared apply must not call provider")

    response = ModelResponse(
        provider="openai-compatible",
        text='{"summary":"创建说明","operations":[]}',
        usage=ProviderUsage(1, 120, 80),
    )
    plan = ExecutionPlan(
        summary="创建说明",
        operations=[ExecutionOperation("create_text", "docs/reused.md", "复用响应\n")],
    )
    preview = ExecutionPlanApplier(tmp_path).preview(plan)
    runner = LocalTaskRunner(tmp_path, tmp_path, FailingProvider())
    result = runner.run(
        "创建说明",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=preview.preview_fingerprint,
            prepared_response=response,
            provider_model="model-name",
        ),
    )
    assert (tmp_path / "docs" / "reused.md").read_text(encoding="utf-8") == "复用响应\n"
    assert result.provider == "openai-compatible"
    assert result.model == "model-name"
    assert result.provider_usage.request_count == 1
```

```python
def test_prepared_response_keeps_stale_preview_protection(tmp_path: Path) -> None:
    class FailingProvider:
        name = "must-not-run"
        def complete(self, request):
            raise AssertionError("stale apply must not call provider")

    write_text_utf8(tmp_path / "README.md", "before\n")
    plan = ExecutionPlan("覆盖", [ExecutionOperation("overwrite_text", "README.md", "after\n")])
    fingerprint = ExecutionPlanApplier(tmp_path).preview(plan).preview_fingerprint
    write_text_utf8(tmp_path / "README.md", "changed after preview\n")
    response = ModelResponse("openai-compatible", "{\"summary\":\"覆盖\",\"operations\":[]}", ProviderUsage(1, 10, 10))
    result = LocalTaskRunner(tmp_path, tmp_path, FailingProvider()).run(
        "覆盖 README",
        TaskRunOptions(
            apply_changes=True,
            execution_plan=plan,
            expected_preview_fingerprint=fingerprint,
            prepared_response=response,
            provider_model="model-name",
        ),
    )
    assert "文件状态已变化" in (result.execution_error or "")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "changed after preview\n"
    assert MemoryStore(tmp_path).list_tasks()[-1].status == "failed"
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_runner.py::test_local_task_runner_reuses_prepared_response_without_provider_call -q`

Expected: FAIL，`TaskRunOptions` 不接受 `prepared_response`。

- [ ] **Step 3: 扩展运行时模型并分流响应来源**

`runtime/models.py` 增加导入和字段：

```python
from dev_agent.providers.models import ModelResponse, ProviderUsage

class TaskRunOptions:
    # 保留原有字段
    prepared_response: ModelResponse | None = None
    provider_model: str | None = None

class TaskRunResult:
    # 保留原有字段
    provider: str = ""
    model: str | None = None
    provider_usage: ProviderUsage = field(default_factory=lambda: ProviderUsage(0, 0, 0))
```

`runner.py` 将第 30-32 行替换为：

```python
if options.prepared_response is None:
    prompt = build_task_prompt(context)
    response = self.provider.complete(ModelRequest(prompt=prompt, task_id=task.task_id))
else:
    response = options.prepared_response
task = update_task_status(self.repo_root, task.task_id, TaskStatus.RUNNING, "provider_completed")
```

在成功和失败两个 `TaskRunResult` 构造中都加入：

```python
provider=response.provider,
model=options.provider_model,
provider_usage=response.usage,
```

- [ ] **Step 4: 运行运行时测试确认 GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_runner.py tests/test_provider_budget.py -q`

Expected: all tests passed；FakeProvider 直接路径仍只调用一次。

- [ ] **Step 5: 提交响应复用**

```powershell
git add src/dev_agent/runtime/models.py src/dev_agent/runtime/runner.py tests/test_runtime_runner.py
git commit -m "feat: reuse prepared provider responses"
```

### Task 5: CLI 显式联网接线与稳定输出

**Files:**
- Modify: `src/dev_agent/cli.py:1-208,256-266`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 写 CLI 参数和本地端到端失败测试**

保持现有 `run_cli()`，为它增加可选 `home` 与 `env` 参数，显式设置 `HOME`/`USERPROFILE` 以隔离用户配置。新增测试：

```python
def test_run_defaults_to_fake_and_requires_fake_response(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "run", "离线请求")
    assert result.returncode == 2
    assert "fake 模式必须传入 --fake-response" in result.stderr


def test_openai_compatible_rejects_fake_inputs_before_network(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path, "run", "冲突", "--provider", "openai-compatible",
        "--fake-response", "{}",
    )
    assert result.returncode == 2
    assert "不能与" in result.stderr


def test_openai_compatible_preview_requests_once_and_does_not_write(tmp_path, provider_server) -> None:
    home, env = configured_home(provider_server.base_url, tmp_path)
    result = run_cli(tmp_path, "run", "创建说明", "--provider", "openai-compatible", home=home, env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["provider"] == "openai-compatible"
    assert payload["model"] == "model-name"
    assert payload["provider_usage"]["request_count"] == 1
    assert payload["preview_changes"][0]["path"] == "docs/cli-provider.md"
    assert provider_server.request_count == 1
    assert not (tmp_path / "docs" / "cli-provider.md").exists()
    assert not (tmp_path / ".agent").exists()


def test_openai_compatible_apply_yes_reuses_one_response(tmp_path, provider_server) -> None:
    home, env = configured_home(provider_server.base_url, tmp_path)
    result = run_cli(
        tmp_path, "run", "创建说明", "--provider", "openai-compatible", "--apply", "--yes",
        home=home, env=env,
    )
    assert result.returncode == 0
    assert provider_server.request_count == 1
    assert (tmp_path / "docs" / "cli-provider.md").read_text(encoding="utf-8") == "CLI 中文\n"
```

```python
def test_openai_compatible_missing_config_fails_before_network(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "run", "请求", "--provider", "openai-compatible", home=tmp_path)
    assert result.returncode == 2
    assert "Provider 配置文件不存在" in result.stderr


def test_openai_compatible_missing_key_fails_before_network(tmp_path: Path, provider_server) -> None:
    home, env = configured_home(provider_server.base_url, tmp_path)
    env.pop("DEV_AGENT_API_KEY")
    result = run_cli(tmp_path, "run", "请求", "--provider", "openai-compatible", home=home, env=env)
    assert result.returncode == 2
    assert "环境变量 DEV_AGENT_API_KEY" in result.stderr
    assert provider_server.request_count == 0


def test_openai_compatible_429_is_not_retried_or_leaked(tmp_path: Path, provider_429_server) -> None:
    home, env = configured_home(provider_429_server.base_url, tmp_path)
    result = run_cli(tmp_path, "run", "请求", "--provider", "openai-compatible", home=home, env=env)
    assert result.returncode == 2
    assert "HTTP 429" in result.stderr
    assert env["DEV_AGENT_API_KEY"] not in result.stderr
    assert provider_429_server.request_count == 1


def test_openai_compatible_malformed_plan_does_not_write(tmp_path: Path, malformed_plan_server) -> None:
    home, env = configured_home(malformed_plan_server.base_url, tmp_path)
    result = run_cli(tmp_path, "run", "请求", "--provider", "openai-compatible", home=home, env=env)
    assert result.returncode == 2
    assert "无法解析 provider 执行计划" in result.stderr
    assert malformed_plan_server.request_count == 1
    assert not (tmp_path / ".agent").exists()


def assert_provider_metadata(payload: dict[str, object]) -> None:
    assert set(("provider", "model", "provider_usage")) <= payload.keys()
```

在每个既有 fake 成功测试中调用 `assert_provider_metadata(payload)`；不发请求的计划预览使用 `provider="fake"`、`model=None`、`provider_usage=None`，实际 FakeProvider 调用输出一次请求的 usage。

- [ ] **Step 2: 运行新增 CLI 测试确认 RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py -q`

Expected: 新测试 FAIL，parser 不识别 `--provider`，或 `--fake-response` 仍由 argparse 强制要求。

- [ ] **Step 3: 实现 CLI 参数预检、准备与输出 helper**

新增导入：

```python
from dataclasses import asdict
import os

from dev_agent.config.provider import ProviderConfigError, load_openai_compatible_config, resolve_openai_compatible_api_key
from dev_agent.providers.models import ProviderError, ProviderUsage
from dev_agent.providers.openai_compatible import OpenAICompatibleProvider
from dev_agent.runtime.provider_plan import ProviderPlanPreparation, prepare_provider_execution_plan
```

新增 helper：

```python
def _provider_metadata(provider: str, model: str | None, usage: ProviderUsage | None) -> dict[str, object]:
    return {
        "provider": provider,
        "model": model,
        "provider_usage": None if usage is None else asdict(usage),
    }


def _validate_run_arguments(args: Namespace) -> None:
    if args.provider == "fake":
        if args.fake_response is None:
            raise ValueError("fake 模式必须传入 --fake-response")
        if args.apply and args.plan_file is None and not args.use_provider_plan:
            raise ValueError("--plan-file or --use-provider-plan is required when --apply is used")
        return
    conflicts = []
    if args.fake_response is not None:
        conflicts.append("--fake-response")
    if args.use_provider_plan:
        conflicts.append("--use-provider-plan")
    if args.plan_file is not None:
        conflicts.append("--plan-file")
    if conflicts:
        raise ValueError(f"openai-compatible 不能与 {', '.join(conflicts)} 同时使用")
```

真实分支核心逻辑：

```python
config = load_openai_compatible_config(Path.home())
api_key = resolve_openai_compatible_api_key(config, os.environ)
provider = OpenAICompatibleProvider(config, api_key)
prepared = prepare_provider_execution_plan(Path.cwd(), Path.home(), args.request, provider, config.model)
if not args.apply:
    payload = _preview_payload_from_preparation(prepared)
    sys.stdout.write(_json(payload))
    return 0
if not _confirm_apply(args):
    sys.stderr.write("应用执行计划需要确认；请传入 --yes 或在交互式终端输入 yes。\n")
    return 2
result = LocalTaskRunner(Path.cwd(), Path.home(), provider).run(
    args.request,
    TaskRunOptions(
        dry_run=True,
        run_verification=args.verify,
        apply_changes=True,
        execution_plan=prepared.execution_plan,
        expected_preview_fingerprint=prepared.preview_result.preview_fingerprint,
        prepared_response=prepared.response,
        provider_model=prepared.model,
    ),
)
```

捕获 `(ProviderConfigError, ProviderError, BudgetExceeded, ExecutionPlanError)`，中文写入 stderr 并返回 2；预览失败加“执行计划预览失败”上下文。Fake 和真实 payload 均合并 `_provider_metadata(...)`。parser 改为：

```python
run_parser.add_argument("--provider", choices=["fake", "openai-compatible"], default="fake")
run_parser.add_argument("--fake-response")
```

- [ ] **Step 4: 运行 CLI 测试确认 GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py -q`

Expected: all tests passed；本地服务端预览和 apply 场景请求计数分别为 1。

- [ ] **Step 5: 运行 Web 回归并提交 CLI 接线**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_web_api.py tests/test_web_server.py -q`

Expected: all tests passed，Web 仍只使用 fake 流程。

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: connect cli provider workflow"
```

### Task 6: 完整验证、安全检查与文档同步

**Files:**
- Modify if needed: `README.md`
- Modify if needed: `docs/superpowers/specs/2026-07-31-dev-agent-openai-compatible-provider-design.md`

- [ ] **Step 1: 运行完整 Python 测试**

Run: `$env:PYTHONPATH='src'; python -m pytest -q`

Expected: 原 127 项测试和本功能新增测试全部通过，无真实网络请求。

- [ ] **Step 2: 验证本地 Web 启动检查不回归**

Run: `$env:PYTHONPATH='src'; python -m dev_agent.cli serve --port 0 --check`

Expected: 返回 JSON，`ok` 为 true，URL 使用 `127.0.0.1` 随机端口。

- [ ] **Step 3: 运行本地 HTTPServer 端到端验收**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py -k 'openai_compatible_preview_requests_once or openai_compatible_apply_yes_reuses_one_response' -vv`

Expected: 2 passed；两个独立 CLI 场景各只有 1 次本地 POST，不请求真实供应商。

- [ ] **Step 4: 检查 UTF-8、敏感信息和变更范围**

Run: `git diff --check`

Expected: 无输出，退出码 0。

Run: `rg -n "api_key:|Bearer .*秘密|DEV_AGENT_API_KEY=.*" src tests docs README.md`

Expected: 不存在硬编码真实密钥；测试中的假密钥仅位于断言和本地服务端数据中。

Run: `git status --short; git diff --stat HEAD~5..HEAD`

Expected: 仅包含本计划列出的 Provider、runtime、CLI、测试和必要文档文件。

- [ ] **Step 5: 如 README 尚无真实 Provider 用法，则补充配置与安全说明并测试**

添加准确示例：

```markdown
### OpenAI-compatible Provider

默认 `dev-agent run` 使用离线 FakeProvider。只有显式传入 `--provider openai-compatible` 才会读取 `~/.dev-agent/provider.yaml` 并发出一次 `/v1/chat/completions` 请求。API Key 必须由 `api_key_env` 指向的环境变量提供；工具不会探测模型、自动重试或并发请求。
```

Run: `$env:PYTHONPATH='src'; python -m pytest -q`

Expected: all tests passed。

- [ ] **Step 6: 提交验证文档（仅有文档变化时）**

```powershell
git add README.md docs/superpowers/specs/2026-07-31-dev-agent-openai-compatible-provider-design.md
git commit -m "docs: explain provider safety boundary"
```

## Self-Review

- Spec coverage: 配置、密钥环境变量、HTTPS/回环 HTTP、单次 Chat Completions、256 KiB、严格 JSON、无副作用预览、指纹审批、响应复用、CLI 显式启用、Fake/Web 兼容、稳定元数据和本地测试均映射到 Task 1-6。
- Placeholder scan: 计划无 TODO、TBD、“类似前项”或未定义的生产接口；参数化测试场景均列出具体输入、异常和次数断言。
- Type consistency: `ModelRequest.system_prompt`、`ProviderPlanPreparation`、`TaskRunOptions.prepared_response/provider_model` 与 `TaskRunResult.provider/model/provider_usage` 在创建、消费和 CLI 输出处名称一致。
- Supplier protection: 自动测试只调用进程内回环 HTTPServer；没有重试、循环、并发、模型探测、故障转移或后台请求。
