from pathlib import Path

import pytest

from dev_agent.config.provider import (
    ProviderConfigError,
    load_openai_compatible_config,
    resolve_openai_compatible_api_key,
)


def write_config(home: Path, text: str) -> Path:
    path = home / ".dev-agent" / "provider.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def valid_config(**overrides: object) -> str:
    values: dict[str, object] = {
        "base_url": "https://example.com/v1/",
        "model": "model-name",
        "api_key_env": "DEV_AGENT_API_KEY",
        "timeout_seconds": 45,
    }
    values.update(overrides)
    lines = ["openai_compatible:"]
    for key, value in values.items():
        if isinstance(value, str):
            rendered = f'"{value}"'
        else:
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"  {key}: {rendered}")
    return "\n".join(lines) + "\n"


def test_loads_https_config_and_resolves_key_from_environment(tmp_path: Path) -> None:
    write_config(tmp_path, valid_config())

    config = load_openai_compatible_config(tmp_path)

    assert config.base_url == "https://example.com/v1"
    assert config.model == "model-name"
    assert config.api_key_env == "DEV_AGENT_API_KEY"
    assert config.timeout_seconds == 45
    assert resolve_openai_compatible_api_key(config, {"DEV_AGENT_API_KEY": "秘密-key"}) == "秘密-key"
    assert "秘密-key" not in repr(config)


def test_timeout_defaults_to_sixty_seconds(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        valid_config().replace('  timeout_seconds: 45\n', ''),
    )

    assert load_openai_compatible_config(tmp_path).timeout_seconds == 60


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?x=1",
        "https://example.com/v1#fragment",
        "ftp://example.com/v1",
        "https:///v1",
    ],
)
def test_rejects_unsafe_urls(tmp_path: Path, base_url: str) -> None:
    write_config(tmp_path, valid_config(base_url=base_url))

    with pytest.raises(ProviderConfigError, match="base_url"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8080/v1/",
        "http://127.0.0.1:8080/v1/",
        "http://[::1]:8080/v1/",
    ],
)
def test_allows_loopback_http(tmp_path: Path, base_url: str) -> None:
    write_config(tmp_path, valid_config(base_url=base_url))

    assert load_openai_compatible_config(tmp_path).base_url == base_url.rstrip("/")


@pytest.mark.parametrize(
    "field",
    ["api_key", "token", "secret", "password", "authorization", "access_token"],
)
def test_rejects_plaintext_secret_fields_without_leaking_value(tmp_path: Path, field: str) -> None:
    write_config(tmp_path, valid_config(**{field: "do-not-store"}))

    with pytest.raises(ProviderConfigError) as caught:
        load_openai_compatible_config(tmp_path)

    assert "敏感字段" in str(caught.value)
    assert "do-not-store" not in str(caught.value)


def test_rejects_unknown_non_sensitive_field(tmp_path: Path) -> None:
    write_config(tmp_path, valid_config(extra_option="value"))

    with pytest.raises(ProviderConfigError, match="未知字段"):
        load_openai_compatible_config(tmp_path)


def test_missing_config_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigError, match="配置文件不存在"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        "- item\n",
        "{}\n",
        "openai_compatible: []\n",
        "openai_compatible:\n",
    ],
)
def test_requires_openai_compatible_mapping(tmp_path: Path, document: str) -> None:
    write_config(tmp_path, document)

    with pytest.raises(ProviderConfigError, match="openai_compatible 映射"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize("field", ["base_url", "model", "api_key_env"])
def test_requires_non_empty_text_fields(tmp_path: Path, field: str) -> None:
    write_config(tmp_path, valid_config(**{field: "   "}))

    with pytest.raises(ProviderConfigError, match=field):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize("api_key_env", ["BAD-NAME", "9START", "HAS SPACE", "含中文"])
def test_rejects_invalid_environment_variable_name(tmp_path: Path, api_key_env: str) -> None:
    write_config(tmp_path, valid_config(api_key_env=api_key_env))

    with pytest.raises(ProviderConfigError, match="环境变量名"):
        load_openai_compatible_config(tmp_path)


@pytest.mark.parametrize("timeout", [0, 301, -1, "60", 1.5, True])
def test_rejects_invalid_timeout(tmp_path: Path, timeout: object) -> None:
    write_config(tmp_path, valid_config(timeout_seconds=timeout))

    with pytest.raises(ProviderConfigError, match="1 至 300"):
        load_openai_compatible_config(tmp_path)


def test_rejects_non_utf8_configuration(tmp_path: Path) -> None:
    path = write_config(tmp_path, valid_config())
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(ProviderConfigError, match="UTF-8"):
        load_openai_compatible_config(tmp_path)


def test_missing_environment_key_is_redacted(tmp_path: Path) -> None:
    write_config(tmp_path, valid_config())
    config = load_openai_compatible_config(tmp_path)

    with pytest.raises(ProviderConfigError, match="环境变量 DEV_AGENT_API_KEY"):
        resolve_openai_compatible_api_key(config, {})


def test_blank_environment_key_is_rejected(tmp_path: Path) -> None:
    write_config(tmp_path, valid_config())
    config = load_openai_compatible_config(tmp_path)

    with pytest.raises(ProviderConfigError, match="未设置或为空"):
        resolve_openai_compatible_api_key(config, {"DEV_AGENT_API_KEY": "  "})
