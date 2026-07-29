from pathlib import Path

from dev_agent.encoding import read_text_utf8, utf8_environment_hint, write_text_utf8


def test_write_and_read_utf8_chinese(tmp_path: Path) -> None:
    target = tmp_path / "规则.md"

    write_text_utf8(target, "中文规则：不要使用 unicode 转义。")

    assert read_text_utf8(target) == "中文规则：不要使用 unicode 转义。"
    assert target.read_bytes().startswith("中文".encode("utf-8"))


def test_utf8_environment_hint_mentions_powershell() -> None:
    hint = utf8_environment_hint()

    assert "[Console]::OutputEncoding" in hint
    assert "UTF8" in hint
