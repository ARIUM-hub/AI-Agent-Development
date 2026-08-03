from hashlib import sha256
from pathlib import Path
import subprocess

import pytest

from dev_agent.runtime.source_context import (
    SourceContextError,
    build_source_context,
)
from dev_agent.tools.executor import CommandResult


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


@pytest.mark.parametrize(
    "raw_path",
    [
        "",
        ".",
        "../outside.py",
        "src/../outside.py",
        "C:/outside.py",
        "C:outside.py",
        "//server/share.py",
    ],
)
def test_rejects_non_relative_or_parent_paths(tmp_path: Path, raw_path: str) -> None:
    init_repo(tmp_path)

    with pytest.raises(SourceContextError, match="源码文件路径不允许"):
        build_source_context(tmp_path, [raw_path])


def test_absolute_path_error_does_not_leak_repo_root(tmp_path: Path) -> None:
    init_repo(tmp_path)
    absolute_path = str((tmp_path / "src" / "code.py").resolve())

    with pytest.raises(SourceContextError) as captured:
        build_source_context(tmp_path, [absolute_path])

    assert str(tmp_path.resolve()) not in str(captured.value)


@pytest.mark.parametrize(
    "raw_path",
    [
        ".git/config",
        "nested/.AGENT/rules.md",
        "nested/.worktrees/file.py",
        "nested/.SuperPowers/plan.md",
    ],
)
def test_rejects_forbidden_directory_at_any_depth(
    tmp_path: Path,
    raw_path: str,
) -> None:
    init_repo(tmp_path)

    with pytest.raises(SourceContextError, match="源码文件路径不允许"):
        build_source_context(tmp_path, [raw_path])


@pytest.mark.parametrize(
    "basename",
    [
        ".env",
        ".ENV.local",
        "credentials.json",
        "CredentialsBackup",
        "secrets.yaml",
        "SecretsOld",
        "id_rsa",
        "ID_ED25519",
        "certificate.PEM",
        "private.key",
        "bundle.p12",
        "bundle.PFX",
    ],
)
def test_rejects_sensitive_basenames(tmp_path: Path, basename: str) -> None:
    init_repo(tmp_path)

    with pytest.raises(SourceContextError, match="源码文件路径不允许"):
        build_source_context(tmp_path, [f"config/{basename}"])


def test_rejects_casefold_duplicate_before_file_access(tmp_path: Path) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/code.py", b"print('ok')\n")

    with pytest.raises(SourceContextError, match="源码文件路径重复"):
        build_source_context(tmp_path, ["src/code.py", "SRC/CODE.PY"])


@pytest.mark.parametrize("raw_path", ["missing.py", "src"])
def test_rejects_missing_file_or_directory(tmp_path: Path, raw_path: str) -> None:
    init_repo(tmp_path)
    (tmp_path / "src").mkdir()

    with pytest.raises(SourceContextError, match="源码文件不是普通文件"):
        build_source_context(tmp_path, [raw_path])


def test_rejects_symlink_in_parent_chain(tmp_path: Path) -> None:
    init_repo(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    (real / "code.py").write_text("print('ok')\n", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("当前 Windows 账户没有创建符号链接的权限")

    with pytest.raises(SourceContextError, match="源码文件路径不允许"):
        build_source_context(tmp_path, ["linked/code.py"])


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_rejects_symlink_and_submodule_index_modes(
    tmp_path: Path,
    mode: str,
) -> None:
    init_repo(tmp_path)
    path = tmp_path / "special"
    path.write_text("index payload\n", encoding="utf-8")
    object_id = git(
        tmp_path,
        "hash-object",
        "-w",
        "--stdin",
        input_text="index payload\n",
    )
    if mode == "160000":
        track_bytes(tmp_path, "seed.txt", b"seed\n")
        git(tmp_path, "commit", "-m", "seed")
        object_id = git(tmp_path, "rev-parse", "HEAD")
    git(
        tmp_path,
        "update-index",
        "--add",
        "--cacheinfo",
        f"{mode},{object_id},special",
    )

    with pytest.raises(
        SourceContextError,
        match="源码文件不是 Git 已跟踪的普通文件：special",
    ):
        build_source_context(tmp_path, ["special"])


def test_accepts_exact_file_count_and_byte_limits(tmp_path: Path) -> None:
    init_repo(tmp_path)
    paths: list[str] = []
    for index in range(10):
        relative_path = f"src/file-{index}.txt"
        track_bytes(tmp_path, relative_path, b"x" * (10 * 1024))
        paths.append(relative_path)

    bundle = build_source_context(tmp_path, paths)

    assert len(bundle.files) == 10
    assert bundle.total_bytes == 100 * 1024


def test_accepts_exact_single_file_limit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/exact.txt", b"x" * (40 * 1024))

    bundle = build_source_context(tmp_path, ["src/exact.txt"])

    assert bundle.total_bytes == 40 * 1024


def test_rejects_eleventh_file_before_git_or_content_read(tmp_path: Path) -> None:
    init_repo(tmp_path)

    with pytest.raises(SourceContextError, match="源码上下文最多允许 10 个文件"):
        build_source_context(tmp_path, [f"src/{index}.py" for index in range(11)])


def test_rejects_single_file_one_byte_over_limit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/large.txt", b"x" * (40 * 1024 + 1))

    with pytest.raises(
        SourceContextError,
        match="源码文件超过 40960 字节：src/large.txt",
    ):
        build_source_context(tmp_path, ["src/large.txt"])


def test_rejects_total_one_byte_over_limit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/first.txt", b"x" * (40 * 1024))
    track_bytes(tmp_path, "src/second.txt", b"y" * (40 * 1024))
    track_bytes(tmp_path, "src/third.txt", b"z" * (20 * 1024 + 1))

    with pytest.raises(SourceContextError, match="源码上下文超过 102400 字节"):
        build_source_context(
            tmp_path,
            ["src/first.txt", "src/second.txt", "src/third.txt"],
        )


def test_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/data.bin", b"\xff\xfe\x00")

    with pytest.raises(
        SourceContextError,
        match="源码文件不是有效的 UTF-8：src/data.bin",
    ):
        build_source_context(tmp_path, ["src/data.bin"])


def test_git_failure_happens_before_content_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "src" / "code.py"
    path.parent.mkdir(parents=True)
    path.write_text("must not be read\n", encoding="utf-8")
    read_calls = 0
    original_read_bytes = Path.read_bytes

    def fail_git(*_args: object, **_kwargs: object) -> CommandResult:
        return CommandResult(
            command=["git"],
            cwd=tmp_path,
            exit_code=128,
            stdout="",
            stderr="not a repository",
            duration_ms=1,
        )

    def count_read_bytes(self: Path) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return original_read_bytes(self)

    monkeypatch.setattr("dev_agent.runtime.source_context.CommandExecutor.run", fail_git)
    monkeypatch.setattr(Path, "read_bytes", count_read_bytes)

    with pytest.raises(SourceContextError, match="无法使用 Git 校验源码上下文"):
        build_source_context(tmp_path, ["src/code.py"])

    assert read_calls == 0


def test_git_utf8_decode_failure_is_reported_as_source_context_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_repo(tmp_path)
    track_bytes(tmp_path, "src/code.py", b"print('ok')\n")

    def fail_decode(*_args: object, **_kwargs: object) -> CommandResult:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(
        "dev_agent.runtime.source_context.CommandExecutor.run",
        fail_decode,
    )

    with pytest.raises(SourceContextError, match="无法使用 Git 校验源码上下文"):
        build_source_context(tmp_path, ["src/code.py"])
