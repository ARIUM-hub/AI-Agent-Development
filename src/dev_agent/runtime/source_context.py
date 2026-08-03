from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from dev_agent.tools.executor import CommandExecutor


MAX_SOURCE_CONTEXT_FILES = 10
MAX_SOURCE_FILE_BYTES = 40 * 1024
MAX_SOURCE_CONTEXT_BYTES = 100 * 1024


class SourceContextError(ValueError):
    pass


@dataclass(frozen=True)
class SourceContextFile:
    path: str
    content: str
    utf8_bytes: int
    sha256: str


@dataclass(frozen=True)
class SourceContextBundle:
    files: tuple[SourceContextFile, ...]
    total_bytes: int

    def to_metadata(self) -> dict[str, object]:
        return {
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "files": [
                {
                    "path": item.path,
                    "utf8_bytes": item.utf8_bytes,
                    "sha256": item.sha256,
                }
                for item in self.files
            ],
        }


def _normalize_paths(repo_root: Path, raw_paths: list[str]) -> list[tuple[str, Path]]:
    normalized: list[tuple[str, Path]] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        relative_path = path.as_posix()
        normalized.append((relative_path, repo_root / path))
    return normalized


def _tracked_regular_files(repo_root: Path, paths: list[str]) -> set[str]:
    command = [
        "git",
        "ls-files",
        "--cached",
        "--stage",
        "-z",
        "--",
        *[f":(literal){path}" for path in paths],
    ]
    result = CommandExecutor(repo_root).run(command)
    if result.exit_code != 0:
        raise SourceContextError("无法使用 Git 校验源码上下文")
    entries: dict[str, list[str]] = {}
    try:
        for record in result.stdout.split("\0"):
            if not record:
                continue
            header, path = record.split("\t", 1)
            mode, _object_id, _stage = header.split(" ", 2)
            entries.setdefault(path, []).append(mode)
    except ValueError:
        raise SourceContextError("无法解析 Git 源码索引") from None
    tracked: set[str] = set()
    for path in paths:
        modes = entries.get(path, [])
        if len(modes) != 1 or not modes[0].startswith("100"):
            raise SourceContextError(f"源码文件不是 Git 已跟踪的普通文件：{path}")
        tracked.add(path)
    return tracked


def build_source_context(
    repo_root: Path,
    raw_paths: list[str],
) -> SourceContextBundle:
    normalized = _normalize_paths(repo_root, raw_paths)
    _tracked_regular_files(repo_root, [path for path, _absolute in normalized])
    files: list[SourceContextFile] = []
    total_bytes = 0
    for relative_path, absolute_path in normalized:
        raw = absolute_path.read_bytes()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SourceContextError(
                f"源码文件不是有效的 UTF-8：{relative_path}"
            ) from None
        total_bytes += len(raw)
        files.append(
            SourceContextFile(
                path=relative_path,
                content=content,
                utf8_bytes=len(raw),
                sha256=f"sha256:{sha256(raw).hexdigest()}",
            )
        )
    return SourceContextBundle(files=tuple(files), total_bytes=total_bytes)
