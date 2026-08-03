from dataclasses import dataclass
from fnmatch import fnmatchcase
from hashlib import sha256
from pathlib import Path, PureWindowsPath
import stat

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


FORBIDDEN_SOURCE_DIRECTORIES = frozenset(
    {".git", ".agent", ".worktrees", ".superpowers"}
)
SENSITIVE_SOURCE_BASENAME_PATTERNS = (
    ".env",
    ".env.*",
    "credentials*",
    "secrets*",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
)


@dataclass(frozen=True)
class _NormalizedSourcePath:
    path: str
    absolute_path: Path


def _path_error(raw_path: str) -> SourceContextError:
    return SourceContextError(f"源码文件路径不允许：{raw_path}")


def _normalize_paths(
    repo_root: Path,
    raw_paths: list[str],
) -> list[_NormalizedSourcePath]:
    if len(raw_paths) > MAX_SOURCE_CONTEXT_FILES:
        raise SourceContextError(
            f"源码上下文最多允许 {MAX_SOURCE_CONTEXT_FILES} 个文件"
        )
    root = repo_root.resolve()
    normalized: list[_NormalizedSourcePath] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        windows_path = PureWindowsPath(raw_path)
        if not raw_path.strip() or windows_path.anchor or windows_path.drive:
            raise _path_error(raw_path)
        if any(part == ".." for part in windows_path.parts):
            raise _path_error(raw_path)
        parts = tuple(part for part in windows_path.parts if part not in {"", "."})
        if not parts:
            raise _path_error(raw_path)
        folded_parts = tuple(part.casefold() for part in parts)
        if any(part in FORBIDDEN_SOURCE_DIRECTORIES for part in folded_parts):
            raise _path_error(raw_path)
        basename = folded_parts[-1]
        if any(
            fnmatchcase(basename, pattern)
            for pattern in SENSITIVE_SOURCE_BASENAME_PATTERNS
        ):
            raise _path_error(raw_path)
        relative_path = "/".join(parts)
        duplicate_key = relative_path.casefold()
        if duplicate_key in seen:
            raise SourceContextError(f"源码文件路径重复：{relative_path}")
        seen.add(duplicate_key)
        absolute_path = root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise _path_error(relative_path)
        resolved = absolute_path.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError:
            raise _path_error(relative_path) from None
        if not absolute_path.exists() or not absolute_path.is_file():
            raise SourceContextError(f"源码文件不是普通文件：{relative_path}")
        try:
            mode = absolute_path.stat().st_mode
        except OSError:
            raise SourceContextError(
                f"无法读取源码文件状态：{relative_path}"
            ) from None
        if not stat.S_ISREG(mode):
            raise SourceContextError(f"源码文件不是普通文件：{relative_path}")
        normalized.append(
            _NormalizedSourcePath(
                path=relative_path,
                absolute_path=absolute_path,
            )
        )
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
    _tracked_regular_files(repo_root, [item.path for item in normalized])
    files: list[SourceContextFile] = []
    total_bytes = 0
    for item in normalized:
        try:
            raw = item.absolute_path.read_bytes()
        except OSError:
            raise SourceContextError(f"无法读取源码文件：{item.path}") from None
        file_bytes = len(raw)
        if file_bytes > MAX_SOURCE_FILE_BYTES:
            raise SourceContextError(
                f"源码文件超过 {MAX_SOURCE_FILE_BYTES} 字节：{item.path}"
            )
        total_bytes += file_bytes
        if total_bytes > MAX_SOURCE_CONTEXT_BYTES:
            raise SourceContextError(
                f"源码上下文超过 {MAX_SOURCE_CONTEXT_BYTES} 字节"
            )
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SourceContextError(
                f"源码文件不是有效的 UTF-8：{item.path}"
            ) from None
        files.append(
            SourceContextFile(
                path=item.path,
                content=content,
                utf8_bytes=file_bytes,
                sha256=f"sha256:{sha256(raw).hexdigest()}",
            )
        )
    return SourceContextBundle(files=tuple(files), total_bytes=total_bytes)
