from dataclasses import asdict, dataclass, field


SUPPORTED_ACTIONS = {"create_text", "overwrite_text", "append_text"}


@dataclass(frozen=True)
class ExecutionOperation:
    action: str
    path: str
    content: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    summary: str
    operations: list[ExecutionOperation] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "operations": [operation.to_dict() for operation in self.operations],
        }


@dataclass(frozen=True)
class ExecutionChange:
    action: str
    path: str
    before_exists: bool
    after_exists: bool
    bytes_written: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPreviewChange:
    action: str
    path: str
    exists: bool
    content_bytes: int
    risk: str
    content_preview: str
    content_preview_truncated: bool
    content_preview_line_count: int
    content_preview_char_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionResult:
    applied: bool
    planned_changes: list[dict[str, object]]
    preview_changes: list[ExecutionPreviewChange] = field(default_factory=list)
    changes: list[ExecutionChange] = field(default_factory=list)
    diff_stat: str = ""
    error: str | None = None

    def preview_changes_as_dicts(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.preview_changes]

    def changes_as_dicts(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.changes]
