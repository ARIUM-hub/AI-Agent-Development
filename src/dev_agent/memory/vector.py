from dataclasses import dataclass
from hashlib import sha256
import math
import re

from dev_agent.memory.models import MemoryHit


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_+-]+|[一-鿿]", text.casefold())
    return words or [text.casefold()]


class HashEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        length = math.sqrt(sum(value * value for value in vector))
        if not length:
            return vector
        return [value / length for value in vector]


@dataclass(frozen=True)
class _VectorItem:
    record_id: str
    kind: str
    text: str
    vector: list[float]


class VectorIndex:
    def __init__(self, provider: HashEmbeddingProvider) -> None:
        self.provider = provider
        self._items: list[_VectorItem] = []

    def add(self, record_id: str, kind: str, text: str) -> None:
        self._items.append(
            _VectorItem(
                record_id=record_id,
                kind=kind,
                text=text,
                vector=self.provider.embed(text),
            )
        )

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        query_vector = self.provider.embed(query)
        hits = [
            MemoryHit(
                record_id=item.record_id,
                kind=item.kind,
                text=item.text,
                score=_cosine(query_vector, item.vector),
            )
            for item in self._items
        ]
        return [hit for hit in sorted(hits, key=lambda item: item.score, reverse=True)[:limit] if hit.score > 0]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
