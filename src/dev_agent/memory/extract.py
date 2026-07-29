from hashlib import sha256

from dev_agent.memory.models import ExperienceRecord, TaskRecord


def extract_experiences(record: TaskRecord) -> list[ExperienceRecord]:
    experiences: list[ExperienceRecord] = []
    for lesson in record.lessons:
        text = lesson.strip()
        if not text:
            continue
        digest = sha256(f"{record.task_id}:{text}".encode("utf-8")).hexdigest()[:16]
        experiences.append(
            ExperienceRecord(
                experience_id=f"exp-{digest}",
                source_task_id=record.task_id,
                text=text,
                tags=[record.title, record.status],
            )
        )
    return experiences
