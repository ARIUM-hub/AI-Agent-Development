from pathlib import Path


UTF8 = "utf-8"


def read_text_utf8(path: Path) -> str:
    return path.read_text(encoding=UTF8)


def write_text_utf8(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=UTF8, newline="\n")


def utf8_environment_hint() -> str:
    return (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8"
    )
