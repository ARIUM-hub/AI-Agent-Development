from hashlib import sha256
from pathlib import Path
import subprocess

import pytest

from dev_agent.runtime.source_context import (
    SourceContextError,
    build_source_context,
)


def git(repo: Path, *args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def init_repo(repo: Path) -> None:
    git(repo, "init")
    git(repo, "config", "user.name", "tester")
    git(repo, "config", "user.email", "tester@example.com")


def track_bytes(repo: Path, relative_path: str, content: bytes) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    git(repo, "add", "--", relative_path)
    return path


def test_builds_ordered_utf8_snapshot_and_safe_metadata(tmp_path: Path) -> None:
    init_repo(tmp_path)
    first = "第一行\n".encode("utf-8")
    second = b'print("ok")\n'
    track_bytes(tmp_path, "src/first.py", first)
    track_bytes(tmp_path, "scripts/run", second)

    bundle = build_source_context(
        tmp_path,
        ["scripts/run", "src/first.py"],
    )

    assert [item.path for item in bundle.files] == ["scripts/run", "src/first.py"]
    assert [item.content for item in bundle.files] == ['print("ok")\n', "第一行\n"]
    assert bundle.total_bytes == len(first) + len(second)
    assert bundle.files[0].sha256 == f"sha256:{sha256(second).hexdigest()}"
    assert bundle.files[1].sha256 == f"sha256:{sha256(first).hexdigest()}"
    metadata = bundle.to_metadata()
    assert metadata == {
        "file_count": 2,
        "total_bytes": len(first) + len(second),
        "files": [
            {
                "path": "scripts/run",
                "utf8_bytes": len(second),
                "sha256": f"sha256:{sha256(second).hexdigest()}",
            },
            {
                "path": "src/first.py",
                "utf8_bytes": len(first),
                "sha256": f"sha256:{sha256(first).hexdigest()}",
            },
        ],
    }
    assert "content" not in repr(metadata)
    assert str(tmp_path.resolve()) not in repr(metadata)


def test_accepts_utf8_bom_but_hashes_and_counts_original_bytes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    raw = b"\xef\xbb\xbf" + "中文\n".encode("utf-8")
    track_bytes(tmp_path, "src/bom.py", raw)

    bundle = build_source_context(tmp_path, ["src/bom.py"])

    assert bundle.files[0].content == "中文\n"
    assert bundle.files[0].utf8_bytes == len(raw)
    assert bundle.files[0].sha256 == f"sha256:{sha256(raw).hexdigest()}"


def test_rejects_untracked_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    path = tmp_path / "src" / "new.py"
    path.parent.mkdir(parents=True)
    path.write_text("print('new')\n", encoding="utf-8")

    with pytest.raises(
        SourceContextError,
        match="源码文件不是 Git 已跟踪的普通文件：src/new.py",
    ):
        build_source_context(tmp_path, ["src/new.py"])
