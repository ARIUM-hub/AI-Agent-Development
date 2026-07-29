from pathlib import Path
import json

from dev_agent.encoding import UTF8
from dev_agent.memory.models import ExperienceRecord, TaskRecord


class MemoryStore:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.history_dir = repo_root / ".agent" / "history"
        self.tasks_path = self.history_dir / "tasks.jsonl"
        self.experiences_path = self.history_dir / "experiences.jsonl"

    def append_task(self, record: TaskRecord) -> None:
        self._append_jsonl(self.tasks_path, record.to_dict())

    def list_tasks(self) -> list[TaskRecord]:
        return [TaskRecord.from_dict(item) for item in self._read_jsonl(self.tasks_path)]

    def get_task(self, task_id: str) -> TaskRecord | None:
        for record in self.list_tasks():
            if record.task_id == task_id:
                return record
        return None

    def append_experience(self, record: ExperienceRecord) -> None:
        self._append_jsonl(self.experiences_path, record.to_dict())

    def list_experiences(self) -> list[ExperienceRecord]:
        return [ExperienceRecord.from_dict(item) for item in self._read_jsonl(self.experiences_path)]

    def _append_jsonl(self, path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding=UTF8, newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        with path.open("r", encoding=UTF8) as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
