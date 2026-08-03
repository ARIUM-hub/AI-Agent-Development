from dev_agent.memory.models import ExperienceRecord, MemoryHit, TaskRecord


def _terms(text: str) -> list[str]:
    return [part.casefold() for part in text.split() if part.strip()]


class KeywordRetriever:
    def __init__(self, tasks: list[TaskRecord], experiences: list[ExperienceRecord]) -> None:
        self.tasks = tasks
        self.experiences = experiences

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        query_terms = _terms(query)
        hits: list[MemoryHit] = []
        for task in self.tasks:
            text = " ".join([task.title, task.summary, *task.events, *task.lessons])
            score = self._score(query_terms, text)
            if score:
                hits.append(MemoryHit(record_id=task.task_id, kind="task", text=text, score=score))
        for experience in self.experiences:
            text = " ".join([experience.text, *experience.tags])
            score = self._score(query_terms, text)
            if score:
                hits.append(
                    MemoryHit(
                        record_id=experience.experience_id,
                        kind="experience",
                        text=text,
                        score=score,
                    )
                )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]

    def _score(self, query_terms: list[str], text: str) -> float:
        haystack = text.casefold()
        return float(sum(1 for term in query_terms if term in haystack))
