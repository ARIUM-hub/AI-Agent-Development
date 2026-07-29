from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
import json

from dev_agent.encoding import read_text_utf8, write_text_utf8


class TaskStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    BLOCKED = "blocked"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskState:
    task_id: str
    title: str
    status: TaskStatus
    created_at: str
    updated_at: str
    events: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_dir(repo_root: Path) -> Path:
    return repo_root / ".agent" / "tasks"


def _task_path(repo_root: Path, task_id: str) -> Path:
    return _task_dir(repo_root) / f"{task_id}.json"


def _dump(task: TaskState) -> str:
    data = asdict(task)
    data["status"] = task.status.value
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _parse(data: dict[str, object]) -> TaskState:
    return TaskState(
        task_id=str(data["task_id"]),
        title=str(data["title"]),
        status=TaskStatus(str(data["status"])),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
        events=[str(item) for item in data.get("events", [])],
    )


def create_task(repo_root: Path, title: str) -> TaskState:
    now = _now()
    task = TaskState(
        task_id=uuid4().hex,
        title=title,
        status=TaskStatus.PLANNED,
        created_at=now,
        updated_at=now,
        events=["task_created"],
    )
    write_text_utf8(_task_path(repo_root, task.task_id), _dump(task))
    return task


def load_task(repo_root: Path, task_id: str) -> TaskState:
    return _parse(json.loads(read_text_utf8(_task_path(repo_root, task_id))))


def update_task_status(repo_root: Path, task_id: str, status: TaskStatus, event: str) -> TaskState:
    current = load_task(repo_root, task_id)
    updated = TaskState(
        task_id=current.task_id,
        title=current.title,
        status=status,
        created_at=current.created_at,
        updated_at=_now(),
        events=[*current.events, event],
    )
    write_text_utf8(_task_path(repo_root, task_id), _dump(updated))
    return updated
