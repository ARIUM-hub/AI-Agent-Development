from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

from dev_agent.encoding import read_text_utf8


_ALLOWED_FIELDS = {"base_url", "model", "api_key_env", "timeout_seconds"}
_SENSITIVE_FIELDS = {
    "access_token",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}
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
    unsafe_parts = (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    )
    if unsafe_parts:
        raise ProviderConfigError("openai_compatible.base_url 不是安全的 API 根地址")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS
    ):
        raise ProviderConfigError(
            "openai_compatible.base_url 必须使用 HTTPS；仅回环地址可使用 HTTP"
        )
    return value.rstrip("/")


def load_openai_compatible_config(home_dir: Path) -> OpenAICompatibleConfig:
    path = home_dir.resolve() / ".dev-agent" / "provider.yaml"
    if not path.is_file():
        raise ProviderConfigError(f"Provider 配置文件不存在：{path}")
    try:
        document = yaml.safe_load(read_text_utf8(path))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProviderConfigError("无法以 UTF-8 读取 Provider 配置") from exc
    if not isinstance(document, dict) or not isinstance(
        document.get("openai_compatible"), dict
    ):
        raise ProviderConfigError("Provider 配置必须包含 openai_compatible 映射")

    data = document["openai_compatible"]
    sensitive = sorted(
        str(key) for key in data if str(key).lower() in _SENSITIVE_FIELDS
    )
    if sensitive:
        raise ProviderConfigError(
            f"Provider 配置禁止保存敏感字段：{', '.join(sensitive)}"
        )
    unknown = sorted(str(key) for key in data if key not in _ALLOWED_FIELDS)
    if unknown:
        raise ProviderConfigError(f"Provider 配置包含未知字段：{', '.join(unknown)}")

    model = _required_text(data, "model")
    api_key_env = _required_text(data, "api_key_env")
    if not _ENV_NAME.fullmatch(api_key_env):
        raise ProviderConfigError(
            "openai_compatible.api_key_env 不是合法的环境变量名"
        )
    timeout = data.get("timeout_seconds", 60)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 300
    ):
        raise ProviderConfigError(
            "openai_compatible.timeout_seconds 必须是 1 至 300 的整数"
        )
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
        raise ProviderConfigError(
            f"环境变量 {config.api_key_env} 未设置或为空"
        )
    return value
