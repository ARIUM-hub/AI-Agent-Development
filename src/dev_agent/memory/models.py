from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    title: str
    status: str
    summary: str = ""
    events: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TaskRecord":
        return cls(
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            status=str(data["status"]),
            summary=str(data.get("summary", "")),
            events=[str(item) for item in data.get("events", [])],
            verification=[str(item) for item in data.get("verification", [])],
            lessons=[str(item) for item in data.get("lessons", [])],
        )


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    source_task_id: str
    text: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ExperienceRecord":
        return cls(
            experience_id=str(data["experience_id"]),
            source_task_id=str(data["source_task_id"]),
            text=str(data["text"]),
            tags=[str(item) for item in data.get("tags", [])],
        )


@dataclass(frozen=True)
class MemoryHit:
    record_id: str
    kind: str
    text: str
    score: float
