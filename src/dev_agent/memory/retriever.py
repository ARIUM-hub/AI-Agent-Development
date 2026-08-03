from dev_agent.memory.keyword import KeywordRetriever
from dev_agent.memory.models import ExperienceRecord, MemoryHit, TaskRecord
from dev_agent.memory.vector import HashEmbeddingProvider, VectorIndex


class MemoryRetriever:
    def __init__(self, tasks: list[TaskRecord], experiences: list[ExperienceRecord]) -> None:
        self.tasks = tasks
        self.experiences = experiences

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        keyword_hits = KeywordRetriever(self.tasks, self.experiences).search(query, limit=limit)
        vector_index = VectorIndex(HashEmbeddingProvider())
        for task in self.tasks:
            vector_index.add(task.task_id, "task", " ".join([task.title, task.summary, *task.lessons]))
        for experience in self.experiences:
            vector_index.add(experience.experience_id, "experience", " ".join([experience.text, *experience.tags]))
        vector_hits = vector_index.search(query, limit=limit)

        merged: dict[tuple[str, str], MemoryHit] = {}
        for hit in [*keyword_hits, *vector_hits]:
            key = (hit.kind, hit.record_id)
            previous = merged.get(key)
            score = hit.score if previous is None else previous.score + hit.score
            merged[key] = MemoryHit(record_id=hit.record_id, kind=hit.kind, text=hit.text, score=score)
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:limit]
